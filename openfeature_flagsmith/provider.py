import json
import typing
from json import JSONDecodeError

from flagsmith.exceptions import FlagsmithClientError
from flagsmith.flagsmith import Flagsmith
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import (
    ErrorCode,
    FlagNotFoundError,
    ParseError,
    TypeMismatchError,
)
from openfeature.flag_evaluation import FlagResolutionDetails, FlagType
from openfeature.provider import AbstractProvider, Metadata
from openfeature.track import TrackingEventDetails

from openfeature_flagsmith.exceptions import FlagsmithProviderError

_BASIC_FLAG_TYPE_MAPPINGS = {
    FlagType.BOOLEAN: bool,
    FlagType.INTEGER: int,
    FlagType.FLOAT: float,
    FlagType.STRING: str,
}


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

        metadata: typing.Optional[typing.Dict[str, typing.Any]] = None
        if tracking_event_details is not None:
            metadata = dict(tracking_event_details.attributes)
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
            return FlagResolutionDetails(value=flag.enabled)

        if not (self.return_value_for_disabled_flags or flag.enabled):
            raise FlagsmithProviderError(
                error_code=ErrorCode.GENERAL,
                error_message="Flag '%s' is not enabled." % flag_key,
            )

        required_type = _BASIC_FLAG_TYPE_MAPPINGS.get(flag_type)
        if required_type and isinstance(flag.value, required_type):
            return FlagResolutionDetails(value=flag.value)
        elif flag_type is FlagType.OBJECT and isinstance(flag.value, str):
            try:
                return FlagResolutionDetails(value=json.loads(flag.value))
            except JSONDecodeError as e:
                msg = "Unable to parse object from value for flag '%s'" % flag_key
                raise ParseError(error_message=msg) from e

        raise TypeMismatchError(
            error_message="Value for flag '%s' is not of type '%s'"
            % (flag_key, flag_type.value)
        )

    @staticmethod
    def _extract_traits(
        evaluation_context: typing.Optional[EvaluationContext],
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if not evaluation_context or not evaluation_context.attributes:
            return None
        nested = evaluation_context.attributes.get("traits", {})
        flat = {k: v for k, v in evaluation_context.attributes.items() if k != "traits"}
        merged = {**flat, **nested}
        return merged or None

    def _get_flags(self, evaluation_context: EvaluationContext = EvaluationContext()):
        if targeting_key := evaluation_context.targeting_key:
            nested_traits = evaluation_context.attributes.pop("traits", {})
            flattened_traits = {**evaluation_context.attributes, **nested_traits}
            return self._client.get_identity_flags(
                identifier=targeting_key,
                traits=flattened_traits,
            )
        return self._client.get_environment_flags()
