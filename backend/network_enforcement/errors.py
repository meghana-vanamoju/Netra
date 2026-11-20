"""Errors raised by the network-enforcement foundation."""


class NetworkEnforcementError(Exception):
    """Base error with a stable machine-readable code."""

    code = "network_enforcement_error"

    def __init__(self, message, *, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.details = details or {}

    def to_dict(self):
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigurationError(NetworkEnforcementError):
    code = "configuration_error"


class IdentityError(NetworkEnforcementError):
    code = "identity_error"


class CommandError(NetworkEnforcementError):
    code = "command_error"


class PlanError(NetworkEnforcementError):
    code = "plan_error"


class NftablesError(NetworkEnforcementError):
    code = "nftables_error"


class HelperError(NftablesError):
    """The privileged helper rejected or could not complete a request."""

    code = "helper_error"


class HelperUnavailableError(HelperError):
    code = "helper_unavailable"


class HelperPermissionError(HelperError):
    code = "helper_permission_denied"


class HelperTimeoutError(HelperError):
    code = "helper_timeout"


class HelperProtocolError(HelperError):
    code = "helper_protocol_error"


class HelperRejectedError(HelperError):
    code = "helper_request_rejected"
