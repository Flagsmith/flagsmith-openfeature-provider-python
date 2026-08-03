import json
import logging
import threading
import typing
from collections import OrderedDict

from openfeature.flag_evaluation import FlagEvaluationDetails, Reason
from openfeature.hook import Hook, HookContext, HookHints
from openfeature.track import TrackingEventDetails

from openfeature_flagsmith.tracking import EXPOSURE_TRACKING_EVENT

if typing.TYPE_CHECKING:
    from openfeature_flagsmith.provider import FlagsmithProvider

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEDUPE_ENTRIES = 10_000


class FlagsmithExposureHook(Hook):
    """
    Records a Flagsmith exposure as a side effect of a flag evaluation, so one
    call both resolves the flag and marks the identity as exposed to its
    variant — the OpenFeature equivalent of Flagsmith's ``get_experiment_flag``::

        hook = FlagsmithExposureHook(provider)
        client.get_string_details(
            "my_experiment_flag",
            "control",
            context,
            FlagEvaluationOptions(hooks=[hook]),
        )

    Attaching the hook at a call site is the experiment declaration:
    evaluations without it never record exposures. Exposures only fire for
    multivariate flags resolved with reason ``TARGETING_MATCH`` (enabled,
    identified, not offline), and are deduped per identity/flag/variant in a
    bounded, thread-safe LRU for the hook instance's lifetime.

    Tracking is an experimental OpenFeature capability (spec section 6).
    """

    def __init__(
        self,
        provider: "FlagsmithProvider",
        max_dedupe_entries: int = DEFAULT_MAX_DEDUPE_ENTRIES,
    ) -> None:
        self._provider = provider
        self._max_dedupe_entries = max_dedupe_entries
        self._seen: "OrderedDict[str, None]" = OrderedDict()
        self._lock = threading.Lock()

    def after(
        self,
        hook_context: HookContext,
        details: FlagEvaluationDetails,
        hints: HookHints,
    ) -> None:
        # Fully error-contained: an uncaught after-hook error flips the
        # evaluation itself to ERROR in the OpenFeature SDK.
        try:
            variant = details.variant
            if not isinstance(variant, str):
                return
            if details.reason != Reason.TARGETING_MATCH:
                logger.debug(
                    'Exposure for "%s" skipped: resolution reason is %s, not'
                    " TARGETING_MATCH.",
                    details.flag_key,
                    details.reason,
                )
                return
            targeting_key = hook_context.evaluation_context.targeting_key
            # json.dumps of the list avoids delimiter-collision false dedupes.
            dedupe_key = json.dumps([targeting_key, details.flag_key, variant])
            with self._lock:
                if dedupe_key in self._seen:
                    self._seen.move_to_end(dedupe_key)
                    return
                self._seen[dedupe_key] = None
                while len(self._seen) > self._max_dedupe_entries:
                    self._seen.popitem(last=False)
            self._provider.track(
                EXPOSURE_TRACKING_EVENT,
                hook_context.evaluation_context,
                TrackingEventDetails(
                    attributes={"flag_key": details.flag_key, "variant": variant}
                ),
            )
        except Exception:
            logger.warning(
                'Failed to record the exposure for "%s".',
                details.flag_key,
                exc_info=True,
            )
