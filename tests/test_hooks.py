import threading
from unittest.mock import MagicMock, create_autospec

import pytest
from flagsmith import Flagsmith
from flagsmith.models import Flag, Flags
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
    flag_key="my_exp", variant="treatment", reason=Reason.TARGETING_MATCH
) -> FlagEvaluationDetails:
    return FlagEvaluationDetails(
        flag_key=flag_key, value="v", variant=variant, reason=reason
    )


def test_hook_records_exposure_on_targeting_match(mock_provider: MagicMock) -> None:
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
    [Reason.STATIC, Reason.DEFAULT, Reason.DISABLED, Reason.STALE, Reason.CACHED],
)
def test_hook_skips_on_non_targeting_match_reason(
    mock_provider: MagicMock, reason: Reason
) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    # When
    hook.after(hook_context=_hook_context(), details=_details(reason=reason), hints={})

    # Then
    mock_provider.track.assert_not_called()


def test_hook_dedupes_per_identity_flag_variant(mock_provider: MagicMock) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    # When - same triple twice, then each dimension varied
    hook.after(hook_context=_hook_context(), details=_details(), hints={})
    hook.after(hook_context=_hook_context(), details=_details(), hints={})
    hook.after(
        hook_context=_hook_context(targeting_key="user-2"),
        details=_details(),
        hints={},
    )
    hook.after(
        hook_context=_hook_context(), details=_details(variant="control"), hints={}
    )

    # Then - 3 distinct exposures, 1 dedupe hit
    assert mock_provider.track.call_count == 3


def test_hook_dedupe_is_bounded_lru(mock_provider: MagicMock) -> None:
    # Given a tiny bound
    hook = FlagsmithExposureHook(mock_provider, max_dedupe_entries=2)

    # When - third key evicts the first, which then fires again
    hook.after(hook_context=_hook_context("u1"), details=_details(), hints={})
    hook.after(hook_context=_hook_context("u2"), details=_details(), hints={})
    hook.after(hook_context=_hook_context("u3"), details=_details(), hints={})
    hook.after(hook_context=_hook_context("u1"), details=_details(), hints={})

    # Then
    assert mock_provider.track.call_count == 4


def test_hook_dedupe_key_is_collision_safe(mock_provider: MagicMock) -> None:
    # Given - a naive join would collide these two identity/flag pairs
    hook = FlagsmithExposureHook(mock_provider)

    # When
    hook.after(
        hook_context=_hook_context('user"1'),
        details=_details(flag_key="exp"),
        hints={},
    )
    hook.after(
        hook_context=_hook_context("user"),
        details=_details(flag_key='1", "exp'),
        hints={},
    )

    # Then - two distinct exposures
    assert mock_provider.track.call_count == 2


def test_hook_swallows_provider_errors(mock_provider: MagicMock) -> None:
    # Given - an uncaught after-hook error flips the evaluation to ERROR
    mock_provider.track.side_effect = RuntimeError("boom")
    hook = FlagsmithExposureHook(mock_provider)

    # When / Then - no error raised
    hook.after(hook_context=_hook_context(), details=_details(), hints={})


def test_hook_is_thread_safe(mock_provider: MagicMock) -> None:
    # Given
    hook = FlagsmithExposureHook(mock_provider)

    def fire(i: int) -> None:
        hook.after(
            hook_context=_hook_context(f"user-{i % 10}"),
            details=_details(),
            hints={},
        )

    # When - 100 concurrent evaluations over 10 identities
    threads = [threading.Thread(target=fire, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Then - exactly one exposure per identity
    assert mock_provider.track.call_count == 10


def test_hook_end_to_end_records_exposure_through_openfeature() -> None:
    # Given - real OF SDK wiring: provider + per-invocation hook
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

        # Then - evaluation resolved AND the exposure reached the SDK
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
