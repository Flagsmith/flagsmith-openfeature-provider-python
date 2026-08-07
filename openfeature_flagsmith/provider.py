import json
import logging
import typing
from json import JSONDecodeError

from flagsmith.exceptions import (
    FlagsmithClientError,
    FlagsmithFeatureDoesNotExistError,
)
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
from openfeature_flagsmith.tracking import EXPOSURE_TRACKING_EVENT

logger = logging.getLogger(__name__)

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
        Route OpenFeature tracking events to Flagsmith.

        ``EXPOSURE_TRACKING_EVENT`` records a flag/variant exposure; any other
        name becomes a plain Flagsmith event. No-ops unless the client was
        initialized with ``enable_events``. Never raises: errors are logged.
        """
        try:
            self._track(tracking_event_name, evaluation_context, tracking_event_details)
        except Exception:
            logger.warning(
                'Failed to process tracking event "%s".',
                tracking_event_name,
                exc_info=True,
            )

    def _track(
        self,
        tracking_event_name: str,
        evaluation_context: typing.Optional[EvaluationContext],
        tracking_event_details: typing.Optional[TrackingEventDetails],
    ) -> None:
        # The SDK has no public events-enabled signal; check first so
        # disabled events cause no network side effects.
        if getattr(self._client, "_event_processor", None) is None:
            logger.debug(
                'Flagsmith events are disabled; dropping tracking event "%s".',
                tracking_event_name,
            )
            return

        identifier = evaluation_context.targeting_key if evaluation_context else None
        traits = self._extract_traits(evaluation_context)

        if tracking_event_name == EXPOSURE_TRACKING_EVENT:
            self._track_exposure(
                identifier, traits, evaluation_context, tracking_event_details
            )
            return

        if tracking_event_name.startswith("$"):
            logger.warning(
                '"%s" is a reserved Flagsmith event name; use "%s" to record'
                " exposures.",
                tracking_event_name,
                EXPOSURE_TRACKING_EVENT,
            )
            return

        value = tracking_event_details.value if tracking_event_details else None
        attributes = (
            dict(tracking_event_details.attributes) if tracking_event_details else {}
        )
        if value is not None and not isinstance(value, (int, float)):
            logger.warning(
                'Tracking event "%s" details.value must be numeric;'
                " sending without it.",
                tracking_event_name,
            )
            value = None

        try:
            self._client.track_event(
                tracking_event_name,
                identifier=identifier,
                value=value,
                traits=traits,
                metadata=attributes or None,
            )
        except ValueError:
            # Events disabled (racing the check above) or name rejected.
            logger.debug(
                'Flagsmith rejected tracking event "%s"; dropping it.',
                tracking_event_name,
                exc_info=True,
            )

    def _track_exposure(
        self,
        identifier: typing.Optional[str],
        traits: typing.Optional[typing.Dict[str, typing.Any]],
        evaluation_context: typing.Optional[EvaluationContext],
        tracking_event_details: typing.Optional[TrackingEventDetails],
    ) -> None:
        attributes = (
            dict(tracking_event_details.attributes) if tracking_event_details else {}
        )
        flag_key = attributes.pop("flag_key", None)
        variant = attributes.pop("variant", None)
        metadata = attributes or None

        if not isinstance(flag_key, str):
            logger.warning(
                '"%s" requires a string "flag_key" attribute; dropping exposure'
                " event.",
                EXPOSURE_TRACKING_EVENT,
            )
            return
        if variant is not None and not isinstance(variant, str):
            logger.warning(
                '"%s" requires a string "variant" attribute when provided;'
                " dropping exposure event.",
                EXPOSURE_TRACKING_EVENT,
            )
            return
        if not identifier:
            logger.info(
                'Exposure for "%s" skipped: no targeting_key in the evaluation'
                " context.",
                flag_key,
            )
            return

        if isinstance(variant, str):
            self._client.track_exposure_event(
                feature_name=flag_key,
                identifier=identifier,
                value=variant,
                traits=traits,
                metadata=metadata,
            )
            return

        # Mirrors the SDK's get_experiment_flag guards, attributed to the
        # context's targeting key rather than any ambient identity.
        try:
            flag = self._client.get_identity_flags(
                identifier=identifier,
                traits=traits or {},
                transient=self._is_transient(evaluation_context),
            ).get_flag(flag_key)
        except FlagsmithFeatureDoesNotExistError:
            logger.info('Exposure for "%s" skipped: flag does not exist.', flag_key)
            return
        except FlagsmithClientError:
            logger.warning(
                'Exposure for "%s" skipped: failed to resolve the flag.',
                flag_key,
                exc_info=True,
            )
            return

        if not isinstance(flag, Flag):
            logger.info('Exposure for "%s" skipped: flag does not exist.', flag_key)
            return
        if not flag.enabled:
            logger.info('Exposure for "%s" skipped: flag is disabled.', flag_key)
            return
        if flag.variant is None:
            logger.info(
                'Exposure for "%s" skipped: experiments require an enabled'
                " multivariate flag.",
                flag_key,
            )
            return

        self._client.track_exposure_event(
            feature_name=flag_key,
            identifier=identifier,
            value=flag.variant,
            traits=traits,
            metadata=metadata,
        )

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
        except FlagsmithFeatureDoesNotExistError as e:
            raise FlagNotFoundError(
                error_message="Flag '%s' was not found." % flag_key
            ) from e
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
            # DefaultFlag has no `variant` attribute.
            variant=getattr(flag, "variant", None),
            flag_metadata=self._build_flag_metadata(flag),
        )

    def _parse_reason(
        self, flag: typing.Any, evaluation_context: EvaluationContext
    ) -> typing.Union[str, Reason]:
        if flag.is_default:
            return Reason.DEFAULT
        if not flag.enabled:
            return Reason.DISABLED
        # Offline documents may be arbitrarily old.
        if getattr(self._client, "offline_mode", False):
            return Reason.STALE
        client_reason = getattr(flag, "reason", None)
        if client_reason is not None:
            # The Flagsmith client's DEFAULT means the environment default
            # state was served; OpenFeature reserves DEFAULT for the code
            # default.
            # TODO remove when https://github.com/Flagsmith/flagsmith-engine/issues/341 is addressed
            if str(client_reason).split(";", 1)[0].strip() == "DEFAULT":
                return Reason.STATIC
            return client_reason
        if evaluation_context.targeting_key:
            # A variant means a percentage-split assignment (SPLIT);
            # TARGETING_MATCH is reserved for segment matches.
            if getattr(flag, "variant", None) is not None:
                return Reason.SPLIT
            return Reason.TARGETING_MATCH
        return Reason.STATIC

    def _build_flag_metadata(
        self, flag: typing.Any
    ) -> typing.Dict[str, typing.Union[bool, int, str]]:
        # Keys are byte-identical with the JS provider.
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
        # The flat `transient` key is an evaluation directive, not a trait.
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
