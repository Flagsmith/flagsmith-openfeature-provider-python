from openfeature.exception import OpenFeatureError, ProviderFatalError


class FlagsmithProviderError(OpenFeatureError):
    pass


class FlagsmithConfigurationError(ProviderFatalError):
    """
    This exception should be raised when the Flagsmith provider has not been set up correctly
    """

    pass
