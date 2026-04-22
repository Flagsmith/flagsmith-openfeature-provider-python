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

### Tracking

The provider supports the [OpenFeature tracking API](https://openfeature.dev/specification/sections/tracking/), which lets you associate user actions with feature flag evaluations for experimentation.

Tracking requires pipeline analytics to be enabled on the **Flagsmith client** (available from `flagsmith` version 5.2.0). The provider acts as a thin delegate — all buffering and flushing is managed by the client.

```python
from flagsmith import Flagsmith, PipelineAnalyticsConfig
from openfeature import api
from openfeature.evaluation_context import EvaluationContext
from openfeature.track import TrackingEventDetails
from openfeature_flagsmith.provider import FlagsmithProvider

# Enable pipeline analytics on the Flagsmith client
client = Flagsmith(
    environment_key="your-environment-key",
    pipeline_analytics_config=PipelineAnalyticsConfig(
        analytics_server_url="https://analytics-collector.flagsmith.com/",
        max_buffer_items=1000,      # optional, default 1000
        flush_interval_seconds=10,  # optional, default 10s
    ),
)

api.set_provider(FlagsmithProvider(client=client))
of_client = api.get_client()

# Flag evaluations are tracked automatically — no extra code needed
variant = of_client.get_string_value(
    "checkout-variant",
    "control",
    evaluation_context=EvaluationContext(targeting_key="user-123"),
)

# Track a custom event explicitly
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

If `pipeline_analytics_config` is not set on the Flagsmith client, calls to `track()` are silently ignored.

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

