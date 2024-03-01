import json
import typing
from json import JSONDecodeError
from numbers import Number

from flagsmith.exceptions import FlagsmithClientError
from flagsmith.flagsmith import Flagsmith
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, FlagType, Reason
from openfeature.provider import Metadata
from openfeature.provider.provider import AbstractProvider

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

    def get_metadata(self) -> Metadata:
        return Metadata(name="FlagsmithProvider")

    def resolve_boolean_details(
        self,
        key: str,
        default_value: bool,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[bool]:
        return self._resolve(key, FlagType.BOOLEAN, default_value, evaluation_context)

    def resolve_string_details(
        self,
        key: str,
        default_value: str,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[str]:
        return self._resolve(key, FlagType.STRING, default_value, evaluation_context)

    def resolve_integer_details(
        self,
        key: str,
        default_value: Number,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[int]:
        return self._resolve(key, FlagType.INTEGER, default_value, evaluation_context)

    def resolve_float_details(
        self,
        key: str,
        default_value: Number,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[float]:
        return self._resolve(key, FlagType.FLOAT, default_value, evaluation_context)

    def resolve_object_details(
        self,
        key: str,
        default_value: dict,
        evaluation_context: EvaluationContext = EvaluationContext(),
    ) -> FlagResolutionDetails[typing.Union[dict, list]]:
        return self._resolve(key, FlagType.OBJECT, default_value, evaluation_context)

    def _resolve(
        self,
        key: str,
        flag_type: FlagType,
        default_value: typing.Any,
        evaluation_context: EvaluationContext,
    ) -> FlagResolutionDetails:
        try:
            flag = self._get_flags(evaluation_context).get_flag(key)
        except FlagsmithClientError:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.GENERAL,
                reason=Reason.ERROR,
            )

        if flag.is_default and not self.use_flagsmith_defaults:
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.FLAG_NOT_FOUND,
                reason=Reason.ERROR,
            )

        if flag_type == FlagType.BOOLEAN and not self.use_boolean_config_value:
            return FlagResolutionDetails(value=flag.enabled)

        if not (self.return_value_for_disabled_flags or flag.enabled):
            return FlagResolutionDetails(
                value=default_value,
                error_code=ErrorCode.GENERAL,
                reason=Reason.DISABLED,
            )

        required_type = _BASIC_FLAG_TYPE_MAPPINGS.get(flag_type)
        if required_type and isinstance(flag.value, required_type):
            return FlagResolutionDetails(value=flag.value)
        elif flag_type is FlagType.OBJECT and isinstance(flag.value, str):
            try:
                return FlagResolutionDetails(value=json.loads(flag.value))
            except JSONDecodeError:
                return FlagResolutionDetails(
                    value=default_value,
                    error_code=ErrorCode.PARSE_ERROR,
                    reason=Reason.ERROR,
                )

        return FlagResolutionDetails(
            value=default_value, error_code=ErrorCode.TYPE_MISMATCH, reason=Reason.ERROR
        )

    def _get_flags(self, evaluation_context: EvaluationContext = EvaluationContext()):
        if targeting_key := evaluation_context.targeting_key:
            return self._client.get_identity_flags(
                identifier=targeting_key,
                traits=evaluation_context.attributes.get("traits", {}),
            )
        return self._client.get_environment_flags()
