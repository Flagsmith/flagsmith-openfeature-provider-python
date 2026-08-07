from unittest.mock import MagicMock, create_autospec

import pytest
from flagsmith import Flagsmith
from flagsmith.models import Flag, Flags
from flagsmith.version import __version__ as flagsmith_version
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import (
    FlagEvaluationDetails,
    FlagEvaluationOptions,
    FlagType,
    Reason,
)
from openfeature.hook import HookContext

from openfeature_flagsmith.hooks import FlagsmithExposureHook
from openfeature_flagsmith.provider import FlagsmithProvider
from openfeature_flagsmith.tracking import EXPOSURE_TRACKING_EVENT


@pytest.fixture()
def mock_provider() -> MagicMock:
    return create_autospec(FlagsmithProvider, instance=True)


def _hook_context(targeting_key="user-1") -> HookContext:
    return HookContext(
        flag_key="my_exp",
        flag_type=FlagType.STRING,
        default_value="control",
        evaluation_context=EvaluationContext(targeting_key=targeting_key),
    )


def _details(
    flag_key="my_exp", variant="treatment", reason=Reason.SPLIT
) -> FlagEvaluationDetails:
    return FlagEvaluationDetails(
        flag_key=flag_key, value="v", variant=variant, reason=reason
    )


def test_hook_records_exposure_on_split(mock_provider: MagicMock) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)
    context = _hook_context()

    # When
    hook.after(hook_context=context, details=_details(), hints={})

    # Then
    mock_provider.track.assert_called_once()
    name, of_context, details = mock_provider.track.call_args.args
    assert name == EXPOSURE_TRACKING_EVENT
    assert of_context is context.evaluation_context
    assert details.attributes == {"flag_key": "my_exp", "variant": "treatment"}


def test_hook_skips_without_variant(mock_provider: MagicMock) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    # When
    hook.after(hook_context=_hook_context(), details=_details(variant=None), hints={})

    # Then
    mock_provider.track.assert_not_called()


@pytest.mark.parametrize(
    "reason",
    [
        Reason.STATIC,
        Reason.DEFAULT,
        Reason.DISABLED,
        Reason.STALE,
        Reason.CACHED,
        Reason.TARGETING_MATCH,
        None,
        "SPLITTER; weight=30",
    ],
)
def test_hook_skips_on_non_split_reason(mock_provider: MagicMock, reason) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    # When
    hook.after(hook_context=_hook_context(), details=_details(reason=reason), hints={})

    # Then
    mock_provider.track.assert_not_called()


@pytest.mark.parametrize("reason", ["SPLIT", "SPLIT; weight=30", "SPLIT ; seed=abc"])
def test_hook_accepts_engine_annotated_split_reasons(
    mock_provider: MagicMock, reason: str
) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    # When
    hook.after(hook_context=_hook_context(), details=_details(reason=reason), hints={})

    # Then
    mock_provider.track.assert_called_once()


def test_hook_swallows_provider_errors(mock_provider: MagicMock) -> None:
    # Given
    mock_provider.track.side_effect = RuntimeError("boom")
    hook = FlagsmithExposureHook(mock_provider)

    # When / Then
    hook.after(hook_context=_hook_context(), details=_details(), hints={})


@pytest.mark.skipif(
    tuple(int(p) for p in flagsmith_version.split(".")[:2]) < (6, 2),
    reason="flagsmith >=6.2 surfaces engine reasons",
)
def test_hook_end_to_end_fires_on_engine_annotated_reason() -> None:
    # Given
    client = create_autospec(Flagsmith, instance=True)
    client._event_processor = MagicMock()
    client.get_identity_flags.return_value = Flags(
        {
            "my_exp": Flag(
                feature_id=1,
                feature_name="my_exp",
                enabled=True,
                value="treatment-value",
                variant="treatment",
                reason="SPLIT; weight=30",
            )
        }
    )
    provider = FlagsmithProvider(client)
    api.set_provider(provider)
    try:
        of_client = api.get_client()
        hook = FlagsmithExposureHook(provider)

        # When
        details = of_client.get_string_details(
            "my_exp",
            "control",
            EvaluationContext(targeting_key="user-1"),
            FlagEvaluationOptions(hooks=[hook]),
        )

        # Then
        assert details.reason == "SPLIT; weight=30"
        client.track_exposure_event.assert_called_once_with(
            feature_name="my_exp",
            identifier="user-1",
            value="treatment",
            traits=None,
            metadata=None,
        )
    finally:
        api.clear_providers()


def test_hook_end_to_end_records_exposure_through_openfeature() -> None:
    # Given
    client = create_autospec(Flagsmith, instance=True)
    client._event_processor = MagicMock()
    client.get_identity_flags.return_value = Flags(
        {
            "my_exp": Flag(
                feature_id=1,
                feature_name="my_exp",
                enabled=True,
                value="treatment-value",
                variant="treatment",
            )
        }
    )
    provider = FlagsmithProvider(client)
    api.set_provider(provider)
    try:
        of_client = api.get_client()
        hook = FlagsmithExposureHook(provider)

        # When
        details = of_client.get_string_details(
            "my_exp",
            "control",
            EvaluationContext(targeting_key="user-1"),
            FlagEvaluationOptions(hooks=[hook]),
        )

        # Then
        assert details.value == "treatment-value"
        assert details.variant == "treatment"
        client.track_exposure_event.assert_called_once_with(
            feature_name="my_exp",
            identifier="user-1",
            value="treatment",
            traits=None,
            metadata=None,
        )
    finally:
        api.clear_providers()
