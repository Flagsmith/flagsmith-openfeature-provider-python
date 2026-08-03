import json
import typing
from json import JSONDecodeError

from flagsmith.exceptions import FlagsmithClientError
from flagsmith.flagsmith import Flagsmith
from flagsmith.models import Flag
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import (
    ErrorCode,
    FlagNotFoundError,
    ParseError,
    TypeMismatchError,
)
from openfeature.flag_evaluation import FlagResolutionDetails, FlagType, Reason
from openfeature.provider import AbstractProvider, Metadata
from openfeature.track import TrackingEventDetails

from openfeature_flagsmith.exceptions import FlagsmithProviderError

_BASIC_FLAG_TYPE_MAPPINGS = {
    FlagType.BOOLEAN: bool,
    FlagType.INTEGER: int,
    FlagType.FLOAT: float,
    FlagType.STRING: str,
}


class TrackingMetadata(typing.TypedDict, total=False):
    """
    Shape of the metadata dict forwarded to ``Flagsmith.track_event``.

    ``value`` holds the numeric value from ``TrackingEventDetails.value`` when
    set. All other keys pass through from ``TrackingEventDetails.attributes``.
    """

    value: float


class FlagsmithProvider(AbstractProvider):
    def __init__(
        self,
        client: Flagsmith,
        use_boolean_config_value: bool = False,
        return_value_for_disabled_flags: bool = False,
        use_flagsmith_defaults: bool = False,
    ):
        self._client = client
        self.return_value_for_disabled_flags = return_value_for_disabled_flags
        self.use_flagsmith_defaults = use_flagsmith_defaults
        self.use_boolean_config_value = use_boolean_config_value

    def track(
        self,
        tracking_event_name: str,
        evaluation_context: typing.Optional[EvaluationContext] = None,
        tracking_event_details: typing.Optional[TrackingEventDetails] = None,
    ) -> None:
        """
        Records a custom event via the Flagsmith client's pipeline analytics.

        No-ops if the client lacks pipeline analytics support or configuration.
        An explicit ``tracking_event_details.value`` overrides any same-named
        key in ``attributes``.
        """
        # Guard against older flagsmith versions or duck-typed clients
        # that don't have track_event.
        if not hasattr(self._client, "track_event"):
            return

        identifier = evaluation_context.targeting_key if evaluation_context else None
        traits = self._extract_traits(evaluation_context)

        metadata: typing.Optional[TrackingMetadata] = None
        if tracking_event_details is not None:
            metadata = typing.cast(
                TrackingMetadata, dict(tracking_event_details.attributes)
            )
            if tracking_event_details.value is not None:
                metadata["value"] = tracking_event_details.value
            if not metadata:
                metadata = None

        try:
            self._client.track_event(
                tracking_event_name,
                identity_identifier=identifier,
                traits=traits,
                metadata=metadata,
            )
        except ValueError:
            # Flagsmith raises ValueError when pipeline analytics is not
            # configured; OpenFeature spec requires track() to no-op.
            return

    def get_metadata(self) -> Metadata:
        return Metadata(name="FlagsmithProvider")

    def resolve_boolean_details(
        self,
        flag_key: str,
        default_value: bool,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[bool]:
        return self._resolve(
            flag_key, FlagType.BOOLEAN, default_value, evaluation_context
        )

    def resolve_string_details(
        self,
        flag_key: str,
        default_value: str,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[str]:
        return self._resolve(
            flag_key, FlagType.STRING, default_value, evaluation_context
        )

    def resolve_integer_details(
        self,
        flag_key: str,
        default_value: int,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[int]:
        return self._resolve(
            flag_key, FlagType.INTEGER, default_value, evaluation_context
        )

    def resolve_float_details(
        self,
        flag_key: str,
        default_value: float,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[float]:
        return self._resolve(
            flag_key, FlagType.FLOAT, default_value, evaluation_context
        )

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: typing.Union[dict, list],
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[typing.Union[dict, list]]:
        return self._resolve(
            flag_key, FlagType.OBJECT, default_value, evaluation_context
        )

    def _resolve(
        self,
        flag_key: str,
        flag_type: FlagType,
        default_value: typing.Any,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails:
        try:
            flag = self._get_flags(evaluation_context).get_flag(flag_key)
        except FlagsmithClientError as e:
            raise FlagsmithProviderError(
                error_code=ErrorCode.GENERAL,
                error_message="An error occurred retrieving flags from Flagsmith client.",
            ) from e

        if flag.is_default and not self.use_flagsmith_defaults:
            raise FlagNotFoundError(error_message="Flag '%s' was not found." % flag_key)

        if flag_type == FlagType.BOOLEAN and not self.use_boolean_config_value:
            return self._build_details(flag, flag.enabled, evaluation_context)

        if not (self.return_value_for_disabled_flags or flag.enabled):
            raise FlagsmithProviderError(
                error_code=ErrorCode.GENERAL,
                error_message="Flag '%s' is not enabled." % flag_key,
            )

        required_type = _BASIC_FLAG_TYPE_MAPPINGS.get(flag_type)
        if required_type and isinstance(flag.value, required_type):
            return self._build_details(flag, flag.value, evaluation_context)
        elif flag_type is FlagType.OBJECT and isinstance(flag.value, str):
            try:
                return self._build_details(
                    flag, json.loads(flag.value), evaluation_context
                )
            except JSONDecodeError as e:
                msg = "Unable to parse object from value for flag '%s'" % flag_key
                raise ParseError(error_message=msg) from e

        raise TypeMismatchError(
            error_message="Value for flag '%s' is not of type '%s'"
            % (flag_key, flag_type.value)
        )

    def _build_details(
        self,
        flag: typing.Any,
        value: typing.Any,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails:
        return FlagResolutionDetails(
            value=value,
            reason=self._parse_reason(flag, evaluation_context),
            # DefaultFlag has no `variant` attribute; never use bare access.
            variant=getattr(flag, "variant", None),
            flag_metadata=self._build_flag_metadata(flag),
        )

    def _parse_reason(
        self, flag: typing.Any, evaluation_context: EvaluationContext
    ) -> Reason:
        if flag.is_default:
            return Reason.DEFAULT
        if not flag.enabled:
            return Reason.DISABLED
        # Offline documents may be arbitrarily old; the exposure hook treats
        # anything but TARGETING_MATCH as not fresh enough to record.
        if getattr(self._client, "offline_mode", False):
            return Reason.STALE
        if evaluation_context.targeting_key:
            return Reason.TARGETING_MATCH
        return Reason.STATIC

    def _build_flag_metadata(
        self, flag: typing.Any
    ) -> typing.Dict[str, typing.Union[bool, int, str]]:
        # Keys are byte-identical with the JS provider (vendor-council aligned).
        metadata: typing.Dict[str, typing.Union[bool, int, str]] = {
            "enabled": flag.enabled
        }
        if isinstance(flag, Flag):
            metadata["featureId"] = flag.feature_id
        variant = getattr(flag, "variant", None)
        if variant is not None:
            metadata["experiment.arm"] = variant
            metadata["experiment.active"] = flag.enabled
            metadata["experiment.unit"] = "user"
        return metadata

    @staticmethod
    def _extract_traits(
        evaluation_context: typing.Optional[EvaluationContext],
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if not evaluation_context or not evaluation_context.attributes:
            return None
        nested = evaluation_context.attributes.get("traits", {})
        # `traits` is unpacked below; the flat `transient` key is an
        # evaluation directive (see _is_transient), not a trait.
        flat = {
            k: v
            for k, v in evaluation_context.attributes.items()
            if k not in ("traits", "transient")
        }
        merged = {**flat, **nested}
        return merged or None

    @staticmethod
    def _is_transient(
        evaluation_context: typing.Optional[EvaluationContext],
    ) -> bool:
        return bool(
            evaluation_context
            and evaluation_context.attributes
            and evaluation_context.attributes.get("transient") is True
        )

    def _get_flags(self, evaluation_context: EvaluationContext = EvaluationContext()):
        if targeting_key := evaluation_context.targeting_key:
            return self._client.get_identity_flags(
                identifier=targeting_key,
                traits=self._extract_traits(evaluation_context) or {},
                transient=self._is_transient(evaluation_context),
            )
        return self._client.get_environment_flags()
