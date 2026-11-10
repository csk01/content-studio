"""Normalized error taxonomy. Adapters translate platform errors into these."""

from __future__ import annotations

from dataclasses import dataclass


class StudioError(Exception):
    """Base class for all engine errors."""


class PlatformError(StudioError):
    """An error from a platform. `retryable` says whether trying again may help."""

    retryable: bool = False


class RetryableError(PlatformError):
    retryable = True


class AuthExpiredError(PlatformError):
    """Credential is missing, expired or revoked; the creator must re-authorize."""


class QuotaExceededError(PlatformError):
    """Platform quota or rate limit reached."""


class PolicyRejectedError(PlatformError):
    """Platform refused the content/account (permissions, eligibility, policy)."""


class PermanentError(PlatformError):
    """Request is invalid or failed in a way retrying will not fix."""


class PlatformNotConfiguredError(StudioError):
    """The platform's app credentials are not configured on this machine."""


class NotAuthorizedError(StudioError):
    """No stored credential for the platform."""


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    message: str


class ValidationFailedError(StudioError):
    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues if i.severity == "error"))


class InvalidTransitionError(StudioError):
    pass
