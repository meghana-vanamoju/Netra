"""Safe, user-facing DNS provider error states.

Exception messages never contain credentials or raw provider response bodies.
"""


class ProviderError(Exception):
    state = "error"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.state.replace("_", " "))


class ProviderNotConfigured(ProviderError):
    state = "not_configured"


class ProviderUnreachable(ProviderError):
    state = "unreachable"


class ProviderTimeout(ProviderError):
    state = "timeout"


class ProviderUnauthorized(ProviderError):
    state = "unauthorized"


class ProviderUnsupported(ProviderError):
    state = "unsupported_api"


class ProviderMalformedResponse(ProviderError):
    state = "malformed_response"


class ProviderUnavailable(ProviderError):
    state = "provider_unavailable"


STATE_MESSAGES = {
    "healthy": "Provider is reachable and responding.",
    "not_configured": "No DNS provider is configured.",
    "unreachable": "The DNS provider could not be reached.",
    "unauthorized": "The DNS provider rejected the configured credentials.",
    "timeout": "The DNS provider did not respond before the timeout.",
    "unsupported_api": "The DNS provider does not support the requested API.",
    "malformed_response": "The DNS provider returned an unexpected response.",
    "provider_unavailable": "The DNS provider is temporarily unavailable.",
}
