from unittest.mock import MagicMock

import pytest
from flagsmith.exceptions import FlagsmithClientError
from flagsmith.models import DefaultFlag, Flag, Flags
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import Reason

from openfeature_flagsmith.provider import FlagsmithProvider


@pytest.fixture()
def mock_flagsmith_client() -> MagicMock():
    return MagicMock()


def test_get_metadata(mock_flagsmith_client: MagicMock) -> None:
    assert (
        FlagsmithProvider(mock_flagsmith_client).get_metadata().name
        == "FlagsmithProvider"
    )


def test_resolve_boolean_details_when_type_mismatch(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = True

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )

    # When
    result = provider.resolve_boolean_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.TYPE_MISMATCH


def test_resolve_string_details_when_type_mismatch(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "foo"

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value=12)}
    )

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.TYPE_MISMATCH


def test_resolve_integer_details_when_type_mismatch(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = 12

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )

    # When
    result = provider.resolve_integer_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.TYPE_MISMATCH


def test_resolve_float_details_when_type_mismatch(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = 1.2

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )

    # When
    result = provider.resolve_float_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.TYPE_MISMATCH


def test_resolve_object_details_when_type_mismatch(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = {"foo": "bar"}

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value=12)}
    )

    # When
    result = provider.resolve_object_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.TYPE_MISMATCH


def test_resolve_object_details_when_parse_error(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = {"foo": "bar"}

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {
            key: Flag(
                feature_id=1, feature_name=key, enabled=True, value="not valid json"
            )
        }
    )

    # When
    result = provider.resolve_object_details(key, default_value=default_value)

    # Then
    assert result.value is default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.PARSE_ERROR


def test_resolve_string_details_when_not_enabled(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "foo"

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=False, value="foo")}
    )

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value == default_value
    assert result.reason == Reason.DISABLED
    assert result.error_code == ErrorCode.GENERAL


def test_resolve_string_details_when_not_enabled_and_return_value_for_disabled_flags(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "default"
    value = "foo"

    provider = FlagsmithProvider(
        mock_flagsmith_client, return_value_for_disabled_flags=True
    )

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=False, value=value)}
    )

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value == value
    assert result.reason is None
    assert result.error_code is None


def test_resolve_string_details_for_flagsmith_default_flag(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "default"

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: DefaultFlag(enabled=True, value="foo")}
    )

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value == default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.FLAG_NOT_FOUND


def test_resolve_string_details_for_flagsmith_default_flag_when_use_flagsmith_defaults(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "default"
    value = "foo"

    provider = FlagsmithProvider(
        mock_flagsmith_client,
        use_flagsmith_defaults=True,
    )

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: DefaultFlag(enabled=True, value=value)}
    )

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value == value
    assert result.reason is None
    assert result.error_code is None


def test_resolve_string_details_when_flagsmith_error(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    default_value = "default"

    provider = FlagsmithProvider(mock_flagsmith_client)
    mock_flagsmith_client.get_environment_flags.side_effect = FlagsmithClientError("")

    # When
    result = provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert result.value == default_value
    assert result.reason == Reason.ERROR
    assert result.error_code == ErrorCode.GENERAL


def test_identity_flags_are_used_if_targeting_key_provided(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    targeting_key = "targeting_key"
    traits = {"foo": "bar"}
    value = "foo"
    default_value = "default"

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.side_effect = NotImplementedError()
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value=value)}
    )

    # When
    result = provider.resolve_string_details(
        key=key,
        default_value=default_value,
        evaluation_context=EvaluationContext(
            targeting_key=targeting_key, attributes={"traits": traits}
        ),
    )

    # Then
    assert result.value == value
    assert result.error_code is None
    assert result.reason is None

    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier=targeting_key, traits=traits
    )
