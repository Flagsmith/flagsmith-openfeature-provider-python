from unittest.mock import MagicMock

import pytest
from flagsmith import Flagsmith
from flagsmith.exceptions import FlagsmithClientError
from flagsmith.models import DefaultFlag, Flag, Flags
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import (
    ErrorCode,
    TypeMismatchError,
    ParseError,
    FlagNotFoundError,
)

from openfeature_flagsmith.exceptions import FlagsmithProviderError
from openfeature_flagsmith.provider import FlagsmithProvider


@pytest.fixture()
def mock_flagsmith_client() -> MagicMock():
    return MagicMock(spec=Flagsmith)


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

    provider = FlagsmithProvider(mock_flagsmith_client, use_boolean_config_value=True)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )

    # When
    with pytest.raises(TypeMismatchError) as e:
        provider.resolve_boolean_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.TYPE_MISMATCH
    assert e.value.error_message == f"Value for flag '{key}' is not of type 'BOOLEAN'"


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
    with pytest.raises(TypeMismatchError) as e:
        provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.TYPE_MISMATCH
    assert e.value.error_message == f"Value for flag '{key}' is not of type 'STRING'"


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
    with pytest.raises(TypeMismatchError) as e:
        provider.resolve_integer_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.TYPE_MISMATCH
    assert e.value.error_message == f"Value for flag '{key}' is not of type 'INTEGER'"


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
    with pytest.raises(TypeMismatchError) as e:
        provider.resolve_float_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.TYPE_MISMATCH
    assert e.value.error_message == f"Value for flag '{key}' is not of type 'FLOAT'"


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
    with pytest.raises(TypeMismatchError) as e:
        provider.resolve_object_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.TYPE_MISMATCH
    assert e.value.error_message == f"Value for flag '{key}' is not of type 'OBJECT'"


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
    with pytest.raises(ParseError) as e:
        provider.resolve_object_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.PARSE_ERROR
    assert (
        e.value.error_message == f"Unable to parse object from value for flag '{key}'"
    )


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
    with pytest.raises(FlagsmithProviderError) as e:
        provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.GENERAL
    assert e.value.error_message == f"Flag '{key}' is not enabled."


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
    with pytest.raises(FlagNotFoundError) as e:
        provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.FLAG_NOT_FOUND
    assert e.value.error_message == f"Flag '{key}' was not found."


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
    with pytest.raises(FlagsmithProviderError) as e:
        provider.resolve_string_details(key, default_value=default_value)

    # Then
    assert e.value.error_code == ErrorCode.GENERAL
    assert (
        e.value.error_message
        == "An error occurred retrieving flags from Flagsmith client."
    )


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
        flag_key=key,
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


def test_resolve_boolean_details_uses_enabled_when_use_boolean_config_value_is_false(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"

    provider = FlagsmithProvider(mock_flagsmith_client, use_boolean_config_value=False)

    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value=None)}
    )

    # When
    result = provider.resolve_boolean_details(flag_key=key, default_value=False)

    # Then
    assert result.value is True
    assert result.error_code is None
    assert result.reason is None
