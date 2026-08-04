from unittest.mock import MagicMock, create_autospec

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
from openfeature.flag_evaluation import Reason
from openfeature.track import TrackingEventDetails

from openfeature_flagsmith.exceptions import FlagsmithProviderError
from openfeature_flagsmith.provider import FlagsmithProvider
from openfeature_flagsmith.tracking import EXPOSURE_TRACKING_EVENT


@pytest.fixture()
def mock_flagsmith_client() -> MagicMock:
    return create_autospec(Flagsmith, instance=True)


@pytest.fixture()
def tracking_flagsmith_client(mock_flagsmith_client: MagicMock) -> MagicMock:
    mock_flagsmith_client._event_processor = MagicMock()
    return mock_flagsmith_client


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
    assert result.reason == Reason.DISABLED
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
    assert result.reason == Reason.DEFAULT
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
    assert result.reason == Reason.TARGETING_MATCH

    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier=targeting_key, traits=traits, transient=False
    )


def test_identity_flags_are_used_with_flat_attributes(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    targeting_key = "targeting_key"
    traits = {"foo": "bar", "age": 25}
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
            targeting_key=targeting_key, attributes=traits
        ),
    )

    # Then
    assert result.value == value
    assert result.error_code is None
    assert result.reason == Reason.TARGETING_MATCH

    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier=targeting_key, traits=traits, transient=False
    )


def test_identity_flags_flat_attributes_and_nested_traits_are_merged(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    targeting_key = "targeting_key"
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
            targeting_key=targeting_key,
            attributes={
                "flat_trait": "flat_value",
                "traits": {"nested_trait": "nested_value"},
            },
        ),
    )

    # Then
    assert result.value == value
    assert result.error_code is None
    assert result.reason == Reason.TARGETING_MATCH

    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier=targeting_key,
        traits={"flat_trait": "flat_value", "nested_trait": "nested_value"},
        transient=False,
    )


def test_identity_flags_nested_traits_take_precedence_over_flat_attributes(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    targeting_key = "targeting_key"
    value = "foo"
    default_value = "default"

    provider = FlagsmithProvider(mock_flagsmith_client)

    mock_flagsmith_client.get_environment_flags.side_effect = NotImplementedError()
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value=value)}
    )

    # When
    provider.resolve_string_details(
        flag_key=key,
        default_value=default_value,
        evaluation_context=EvaluationContext(
            targeting_key=targeting_key,
            attributes={
                "shared_key": "flat_value",
                "traits": {"shared_key": "nested_value"},
            },
        ),
    )

    # Then
    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier=targeting_key,
        traits={"shared_key": "nested_value"},
        transient=False,
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
    assert result.reason == Reason.STATIC


# ---------------------------------------------------------------------------
# Tracking: custom events
# ---------------------------------------------------------------------------


def test_track_is_noop_when_events_disabled(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    provider.track("purchase")

    # Then
    mock_flagsmith_client.track_event.assert_not_called()


def test_track_swallows_value_error_from_sdk(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    tracking_flagsmith_client.track_event.side_effect = ValueError("events disabled")
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When / Then
    provider.track("purchase")


def test_track_swallows_unexpected_exceptions(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    tracking_flagsmith_client.track_event.side_effect = RuntimeError("boom")
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When / Then
    provider.track("purchase")


def test_track_delegates_to_client(tracking_flagsmith_client: MagicMock) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        "purchase",
        evaluation_context=EvaluationContext(
            targeting_key="user-123",
            attributes={"plan": "premium"},
        ),
        tracking_event_details=TrackingEventDetails(
            value=99.77,
            attributes={"currency": "USD"},
        ),
    )

    # Then
    tracking_flagsmith_client.track_event.assert_called_once_with(
        "purchase",
        identifier="user-123",
        value=99.77,
        traits={"plan": "premium"},
        metadata={"currency": "USD"},
    )


def test_track_with_minimal_args(tracking_flagsmith_client: MagicMock) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track("signup")

    # Then
    tracking_flagsmith_client.track_event.assert_called_once_with(
        "signup",
        identifier=None,
        value=None,
        traits=None,
        metadata=None,
    )


def test_track_attributes_pass_through_as_metadata(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        "checkout",
        tracking_event_details=TrackingEventDetails(
            value=99.77,
            attributes={"value": "a-metadata-key", "other": "kept"},
        ),
    )

    # Then
    tracking_flagsmith_client.track_event.assert_called_once_with(
        "checkout",
        identifier=None,
        value=99.77,
        traits=None,
        metadata={"value": "a-metadata-key", "other": "kept"},
    )


def test_track_non_numeric_value_is_dropped_with_warning(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        "checkout",
        tracking_event_details=TrackingEventDetails(value="99.77"),  # type: ignore[arg-type]
    )

    # Then
    tracking_flagsmith_client.track_event.assert_called_once_with(
        "checkout",
        identifier=None,
        value=None,
        traits=None,
        metadata=None,
    )


def test_track_extracts_traits_from_context(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        "page_view",
        evaluation_context=EvaluationContext(
            targeting_key="user-123",
            attributes={
                "shared_key": "flat_value",
                "other": "kept",
                "traits": {"shared_key": "nested_value"},
            },
        ),
    )

    # Then
    tracking_flagsmith_client.track_event.assert_called_once_with(
        "page_view",
        identifier="user-123",
        traits={"shared_key": "nested_value", "other": "kept"},
        value=None,
        metadata=None,
    )


def test_track_drops_reserved_dollar_names(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track("$flag_exposure")
    provider.track("$anything")

    # Then
    tracking_flagsmith_client.track_event.assert_not_called()
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


# ---------------------------------------------------------------------------
# Reasons / variant / flag_metadata
# ---------------------------------------------------------------------------


def test_resolve_environment_flag_has_static_reason_and_metadata(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=42, feature_name=key, enabled=True, value="foo")}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    result = provider.resolve_string_details(key, default_value="default")

    # Then
    assert result.reason == Reason.STATIC
    assert result.variant is None
    assert result.flag_metadata == {"enabled": True, "featureId": 42}


def test_resolve_identity_flag_with_variant_has_experiment_metadata(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_experiment"
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {
            key: Flag(
                feature_id=7,
                feature_name=key,
                enabled=True,
                value="treatment-value",
                variant="treatment",
            )
        }
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    result = provider.resolve_string_details(
        key,
        default_value="control",
        evaluation_context=EvaluationContext(targeting_key="user-1"),
    )

    # Then
    assert result.reason == Reason.SPLIT
    assert result.variant == "treatment"
    assert result.flag_metadata == {
        "enabled": True,
        "featureId": 7,
        "experiment.arm": "treatment",
        "experiment.active": True,
        "experiment.unit": "user",
    }


def test_resolve_boolean_details_disabled_flag_has_disabled_reason(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=False, value=None)}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    result = provider.resolve_boolean_details(key, default_value=True)

    # Then
    assert result.value is False
    assert result.reason == Reason.DISABLED


def test_resolve_flagsmith_default_flag_metadata_has_no_feature_id(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: DefaultFlag(enabled=True, value="foo")}
    )
    provider = FlagsmithProvider(mock_flagsmith_client, use_flagsmith_defaults=True)

    # When
    result = provider.resolve_string_details(key, default_value="default")

    # Then
    assert result.reason == Reason.DEFAULT
    assert result.variant is None
    assert result.flag_metadata == {"enabled": True}


def test_resolve_in_offline_mode_has_stale_reason(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    mock_flagsmith_client.offline_mode = True
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    result = provider.resolve_string_details(
        key,
        default_value="default",
        evaluation_context=EvaluationContext(targeting_key="user-1"),
    )

    # Then
    assert result.reason == Reason.STALE


def test_resolve_object_details_parsed_json_carries_reason_and_metadata(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "my_feature"
    mock_flagsmith_client.get_environment_flags.return_value = Flags(
        {key: Flag(feature_id=3, feature_name=key, enabled=True, value='{"a": 1}')}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    result = provider.resolve_object_details(key, default_value={})

    # Then
    assert result.value == {"a": 1}
    assert result.reason == Reason.STATIC
    assert result.flag_metadata == {"enabled": True, "featureId": 3}


# ---------------------------------------------------------------------------
# Transient identities
# ---------------------------------------------------------------------------


def test_transient_attribute_maps_to_transient_identity(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    provider.resolve_string_details(
        flag_key=key,
        default_value="default",
        evaluation_context=EvaluationContext(
            targeting_key="user-1",
            attributes={"transient": True, "plan": "pro"},
        ),
    )

    # Then
    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier="user-1", traits={"plan": "pro"}, transient=True
    )


def test_nested_trait_named_transient_is_kept(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    key = "key"
    mock_flagsmith_client.get_identity_flags.return_value = Flags(
        {key: Flag(feature_id=1, feature_name=key, enabled=True, value="foo")}
    )
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    provider.resolve_string_details(
        flag_key=key,
        default_value="default",
        evaluation_context=EvaluationContext(
            targeting_key="user-1",
            attributes={"traits": {"transient": "a-real-trait"}},
        ),
    )

    # Then
    mock_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier="user-1", traits={"transient": "a-real-trait"}, transient=False
    )


# ---------------------------------------------------------------------------
# Tracking: exposures
# ---------------------------------------------------------------------------


def test_exposure_with_explicit_variant_sends_as_rendered(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(
            targeting_key="user-1", attributes={"plan": "pro"}
        ),
        tracking_event_details=TrackingEventDetails(
            attributes={"flag_key": "my_exp", "variant": "treatment", "page": "home"}
        ),
    )

    # Then
    tracking_flagsmith_client.track_exposure_event.assert_called_once_with(
        feature_name="my_exp",
        identifier="user-1",
        value="treatment",
        traits={"plan": "pro"},
        metadata={"page": "home"},
    )
    tracking_flagsmith_client.get_identity_flags.assert_not_called()


def test_exposure_without_flag_key_is_dropped(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(attributes={"variant": "t"}),
    )

    # Then
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


def test_exposure_without_targeting_key_is_skipped(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        tracking_event_details=TrackingEventDetails(
            attributes={"flag_key": "my_exp", "variant": "t"}
        ),
    )

    # Then
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


def test_variantless_exposure_resolves_flag_and_sends_variant(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    tracking_flagsmith_client.get_identity_flags.return_value = Flags(
        {
            "my_exp": Flag(
                feature_id=1,
                feature_name="my_exp",
                enabled=True,
                value="v",
                variant="treatment",
            )
        }
    )
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(
            targeting_key="user-1", attributes={"transient": True}
        ),
        tracking_event_details=TrackingEventDetails(attributes={"flag_key": "my_exp"}),
    )

    # Then
    tracking_flagsmith_client.get_identity_flags.assert_called_once_with(
        identifier="user-1", traits={}, transient=True
    )
    tracking_flagsmith_client.track_exposure_event.assert_called_once_with(
        feature_name="my_exp",
        identifier="user-1",
        value="treatment",
        traits=None,
        metadata=None,
    )


@pytest.mark.parametrize(
    "flag",
    [
        pytest.param(DefaultFlag(enabled=True, value="v"), id="default-flag"),
        pytest.param(
            Flag(feature_id=1, feature_name="my_exp", enabled=False, value="v"),
            id="disabled",
        ),
        pytest.param(
            Flag(
                feature_id=1,
                feature_name="my_exp",
                enabled=True,
                value="v",
                variant=None,
            ),
            id="no-variant",
        ),
    ],
)
def test_variantless_exposure_guard_chain_skips(
    tracking_flagsmith_client: MagicMock, flag
) -> None:
    # Given
    tracking_flagsmith_client.get_identity_flags.return_value = Flags({"my_exp": flag})
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(attributes={"flag_key": "my_exp"}),
    )

    # Then
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


def test_variantless_exposure_missing_flag_is_skipped(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    tracking_flagsmith_client.get_identity_flags.return_value = Flags({})
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When / Then
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(attributes={"flag_key": "nope"}),
    )
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


def test_variantless_exposure_client_error_is_swallowed(
    tracking_flagsmith_client: MagicMock,
) -> None:
    # Given
    tracking_flagsmith_client.get_identity_flags.side_effect = FlagsmithClientError("")
    provider = FlagsmithProvider(tracking_flagsmith_client)

    # When / Then
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(attributes={"flag_key": "my_exp"}),
    )
    tracking_flagsmith_client.track_exposure_event.assert_not_called()


def test_exposure_is_noop_when_events_disabled(
    mock_flagsmith_client: MagicMock,
) -> None:
    # Given
    provider = FlagsmithProvider(mock_flagsmith_client)

    # When
    provider.track(
        EXPOSURE_TRACKING_EVENT,
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(attributes={"flag_key": "my_exp"}),
    )

    # Then
    mock_flagsmith_client.get_identity_flags.assert_not_called()
    mock_flagsmith_client.track_exposure_event.assert_not_called()


def test_package_root_reexports() -> None:
    import openfeature_flagsmith

    assert openfeature_flagsmith.FlagsmithProvider is FlagsmithProvider
    assert openfeature_flagsmith.EXPOSURE_TRACKING_EVENT == "feature_flag.exposure"
    assert openfeature_flagsmith.FlagsmithExposureHook is not None
