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


def _is_split_reason(reason: typing.Union[str, Reason, None]) -> bool:
    # The engine annotates reasons ("SPLIT; weight=30"); compare the
    # leading token.
    if reason is None:
        return False
    return str(reason).split(";", 1)[0].strip() == Reason.SPLIT.value


class FlagsmithExposureHook(Hook):
    """
    Records a Flagsmith exposure as a side effect of a flag evaluation::

        hook = FlagsmithExposureHook(provider)
        client.get_string_details(
            "my_experiment_flag",
            "control",
            context,
            FlagEvaluationOptions(hooks=[hook]),
        )

    Attaching the hook at a call site is the experiment declaration:
    evaluations without it never record exposures. Exposures only fire for
    flags resolved with a variant and reason ``SPLIT``, deduped per
    identity/flag/variant in a bounded, thread-safe LRU.
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
        # An uncaught after-hook error would flip the evaluation to ERROR.
        try:
            variant = details.variant
            if not isinstance(variant, str):
                return
            if not _is_split_reason(details.reason):
                logger.debug(
                    'Exposure for "%s" skipped: resolution reason is %s, not' " SPLIT.",
                    details.flag_key,
                    details.reason,
                )
                return
            targeting_key = hook_context.evaluation_context.targeting_key
            # json.dumps avoids delimiter collisions in the key.
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
