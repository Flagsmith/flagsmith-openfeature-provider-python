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

