from openfeature.exception import ErrorCode, OpenFeatureError, GeneralError


class FlagsmithProviderError(OpenFeatureError):
    pass


class FlagsmithConfigurationError(OpenFeatureError):
    """
    This exception should be raised when the Flagsmith provider has not been set up correctly

    TODO: this should inherit from ProviderFatalError when available in openfeature.
    """

    def __init__(self, error_message: str = None):
        """
        Constructor for the FlagsmithConfigurationError.  The error code for
        this type of exception is ErrorCode.PROVIDER_NOT_READY.
        @param error_message: a string message representing why the error has been
        raised
        @return: a FlagsmithConfigurationError exception
        """
        super().__init__(ErrorCode.PROVIDER_NOT_READY, error_message)
