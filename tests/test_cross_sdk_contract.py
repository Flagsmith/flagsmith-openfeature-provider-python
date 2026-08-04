"""Cross-SDK wire contract: these literals are shared with the JS provider
and the analytics pipeline — changing them here means changing them there."""

from unittest.mock import MagicMock, create_autospec

from flagsmith import Flagsmith
from flagsmith.models import Flag, Flags
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagEvaluationDetails, FlagType, Reason
from openfeature.hook import HookContext
from openfeature.track import TrackingEventDetails

from openfeature_flagsmith.hooks import FlagsmithExposureHook
from openfeature_flagsmith.provider import FlagsmithProvider
from openfeature_flagsmith.tracking import EXPOSURE_TRACKING_EVENT


def test_exposure_tracking_event_name() -> None:
    assert EXPOSURE_TRACKING_EVENT == "feature_flag.exposure"


def test_track_reads_snake_case_exposure_attribute_keys() -> None:
    # Given
    client = create_autospec(Flagsmith, instance=True)
    client._event_processor = MagicMock()
    provider = FlagsmithProvider(client)

    # When
    provider.track(
        "feature_flag.exposure",
        evaluation_context=EvaluationContext(targeting_key="user-1"),
        tracking_event_details=TrackingEventDetails(
            attributes={"flag_key": "exp", "variant": "arm-a"}
        ),
    )

    # Then
    client.track_exposure_event.assert_called_once_with(
        feature_name="exp",
        identifier="user-1",
        value="arm-a",
        traits=None,
        metadata=None,
    )


def test_hook_emits_contract_attribute_keys() -> None:
    # Given
    provider = create_autospec(FlagsmithProvider, instance=True)
    hook = FlagsmithExposureHook(provider)

    # When
    hook.after(
        hook_context=HookContext(
            flag_key="exp",
            flag_type=FlagType.STRING,
            default_value="control",
            evaluation_context=EvaluationContext(targeting_key="user-1"),
        ),
        details=FlagEvaluationDetails(
            flag_key="exp", value="v", variant="arm-a", reason=Reason.SPLIT
        ),
        hints={},
    )

    # Then
    event_name, _, details = provider.track.call_args.args
    assert event_name == "feature_flag.exposure"
    assert details.attributes == {"flag_key": "exp", "variant": "arm-a"}


def test_experiment_flag_metadata_keys() -> None:
    # Given
    client = create_autospec(Flagsmith, instance=True)
    client.get_identity_flags.return_value = Flags(
        {
            "exp": Flag(
                feature_id=1,
                feature_name="exp",
                enabled=True,
                value="v",
                variant="arm-a",
            )
        }
    )
    provider = FlagsmithProvider(client)

    # When
    result = provider.resolve_string_details(
        "exp", "control", EvaluationContext(targeting_key="user-1")
    )

    # Then
    assert result.flag_metadata == {
        "enabled": True,
        "featureId": 1,
        "experiment.arm": "arm-a",
        "experiment.active": True,
        "experiment.unit": "user",
    }
