import typing

EXPOSURE_TRACKING_EVENT: typing.Final[str] = "feature_flag.exposure"
"""
Reserved tracking-event name for recording flag/variant exposures.

``client.track(EXPOSURE_TRACKING_EVENT, context, details)`` routes to
Flagsmith's exposure tracking instead of a plain analytics event. This is the
OpenFeature-facing name (identical across Flagsmith OpenFeature providers); on
the wire the Flagsmith SDK emits the ``$flag_exposure`` system event.

Tracking is an experimental OpenFeature capability (spec section 6).
"""
