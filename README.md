# flagsmith-openfeature-provider-python

The Flagsmith provider allows you to connect to your Flagsmith instance through the OpenFeature SDK

## Python SDK usage

### Install dependencies

First, you'll need to install the OpenFeature SDK and the Flagsmith Provider.  

```bash
pip install openfeature-sdk openfeature-provider-flagsmith
```

### Using the Flagsmith Provider with the OpenFeature SDK

To create a Flagsmith provider you will need to provide a number of arguments. These are shown and described 
below. See the [Flagsmith docs](https://docs.flagsmith.com/clients/server-side) for further information on the 
configuration options available for the Flagsmith python client.

```python
from flagsmith import Flagsmith
from openfeature_flagsmith.provider import FlagsmithProvider

provider = FlagsmithProvider(
    # Provide an instance of the Flagsmith python client.
    # Required: True
    client=Flagsmith(...),
    
    # By enabling the use_flagsmith_defaults setting, you can instruct the OpenFeature SDK to use
    # the default logic included in the Flagsmith client as per the docs here: 
    # https://docs.flagsmith.com/clients/server-side#managing-default-flags. This will override the 
    # default provided at evaluation time in the OpenFeature SDK in most cases (excluding those where 
    # an unexpected exception happens in the Flagsmith client itself).
    # Required: False
    # Default: False
    use_flagsmith_defaults=False,
    
    # By default, when evaluating the boolean value of a feature in the OpenFeature SDK, the Flagsmith 
    # OpenFeature Provider will use the 'Enabled' state of the feature as defined in Flagsmith. This 
    # behaviour can be changed to use the 'value' field defined in the Flagsmith feature instead by 
    # enabling the use_boolean_config_value setting. 
    # Note: this relies on the value being defined as a Boolean in Flagsmith. If the value is not a 
    # Boolean, an error will occur and the default value provided as part of the evaluation will be 
    # returned instead.  
    # Required: False
    # Default: False
    use_boolean_config_value=False,
    
    # By default, the Flagsmith OpenFeature Provider will raise an exception (triggering the 
    # OpenFeature SDK to return the provided default value) if the flag is disabled. This behaviour
    # can be configured by enabling this flag so that the Flagsmith OpenFeature provider ignores
    # the enabled state of a flag when returning a value.
    # Required: False
    # Default: False
    return_value_for_disabled_flags=False,
)
```

The provider can then be used with the OpenFeature client as per
[the documentation](https://openfeature.dev/docs/reference/concepts/evaluation-api#setting-a-provider).

### Tracking and experimentation

The provider supports the [OpenFeature tracking API](https://openfeature.dev/specification/sections/tracking/) (an experimental OpenFeature capability), which lets you record custom events and flag **exposures** for experimentation.

Tracking requires events to be enabled on the **Flagsmith client** (`flagsmith` ≥5.5). The provider acts as a thin delegate — all buffering and flushing is managed by the client.

```python
from flagsmith import Flagsmith
from openfeature import api
from openfeature_flagsmith import FlagsmithProvider

client = Flagsmith(
    environment_key="your-environment-key",
    enable_events=True,
)

provider = FlagsmithProvider(client=client)
api.set_provider(provider)
of_client = api.get_client()
```

If events are not enabled on the Flagsmith client, all tracking calls are silently dropped.

#### Recording exposures

An **exposure** marks an identity as having experienced an experiment variant. Exposures are never recorded automatically: evaluating a flag does not expose anyone. There are three ways to record them, from most to least recommended.

**1. The exposure hook (recommended).** Attach `FlagsmithExposureHook` to the evaluations that *are* your experiment — attaching the hook is the experiment declaration:

```python
from openfeature.evaluation_context import EvaluationContext
from openfeature.flag_evaluation import FlagEvaluationOptions
from openfeature_flagsmith import FlagsmithExposureHook

hook = FlagsmithExposureHook(provider)

details = of_client.get_string_details(
    "my_experiment_flag",
    "control",
    EvaluationContext(targeting_key="user-123"),
    FlagEvaluationOptions(hooks=[hook]),
)
```

The hook records an exposure only when the flag resolved with a variant and reason `SPLIT` — a multivariate percentage-split assignment (enabled, identified, not offline). With `flagsmith` ≥6.2 resolution reasons come from the Flagsmith engine (e.g. `SPLIT; weight=30`; the engine's `DEFAULT` maps to `STATIC`); on older SDKs or APIs the provider infers them. Repeated evaluations are safe: duplicate exposures are deduplicated downstream.

**2. Explicit `track()`.** Use the reserved `feature_flag.exposure` event name when you need to record an exposure decoupled from evaluation:

```python
from openfeature.track import TrackingEventDetails
from openfeature_flagsmith import EXPOSURE_TRACKING_EVENT

# With an explicit variant: sent as rendered.
of_client.track(
    EXPOSURE_TRACKING_EVENT,
    evaluation_context=EvaluationContext(targeting_key="user-123"),
    tracking_event_details=TrackingEventDetails(
        attributes={"flag_key": "my_experiment_flag", "variant": "treatment"}
    ),
)

# Without a variant: the provider resolves the flag for the targeting key and
# records the exposure only if the flag exists, is enabled and has a variant.
of_client.track(
    EXPOSURE_TRACKING_EVENT,
    evaluation_context=EvaluationContext(targeting_key="user-123"),
    tracking_event_details=TrackingEventDetails(
        attributes={"flag_key": "my_experiment_flag"}
    ),
)
```

**3. The native Flagsmith client.** `client.get_experiment_flag(...)` / `client.track_exposure_event(...)` work as documented in the [Flagsmith docs](https://docs.flagsmith.com/) and share the same event pipeline.

#### Custom events

Any other event name is forwarded as a plain Flagsmith event. `TrackingEventDetails.value` must be numeric and is sent as the event value; `attributes` become event metadata; context traits are attached to the event.

```python
of_client.track(
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
```

#### Caveats

- **Anonymous contexts**: exposures require a `targeting_key`; without one they are skipped (logged at info).
- **Reserved names**: event names starting with `$` are reserved for Flagsmith system events and are dropped with a warning — use `EXPOSURE_TRACKING_EVENT` to record exposures.
- **Transient identities** (Python provider only, remote evaluation only): set the context attribute `"transient": True` to evaluate an identity without persisting it. The variant-less exposure path honors it too.

### Evaluation Context

The evaluation context supports traits in two ways:
1. Flat top-level attributes
2. A nested traits object

The two forms are merged and sent to Flagsmith, with the traits object taking precedence if keys conflict.

```python
context = EvaluationContext( # Traits are: {"abc":"def", "foo": "bar2"}
    targeting_key="user",
    attributes={
        "foo": "bar", 
        "abc": "def", 
        "traits": {"foo": "bar2"}
    },
)

```

