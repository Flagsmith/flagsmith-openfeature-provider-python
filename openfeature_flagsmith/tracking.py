import typing

EXPOSURE_TRACKING_EVENT: typing.Final[str] = "feature_flag.exposure"
"""
Reserved tracking-event name for recording flag/variant exposures.

OpenFeature-facing name, identical across Flagsmith providers; on the wire
the SDK emits the ``$flag_exposure`` system event.
"""
