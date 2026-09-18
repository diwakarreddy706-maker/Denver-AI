"""Exception hierarchy for Denver Desktop Automation Subsystem."""

from __future__ import annotations


class AutomationError(Exception):
    """Base exception for all automation failures."""


class ApplicationNotFoundError(AutomationError):
    """Raised when an unallowlisted or missing application is requested."""


class ApplicationLaunchError(AutomationError):
    """Raised when an application fails to start."""


class ApplicationCloseError(AutomationError):
    """Raised when an application cannot be closed cleanly."""


class WindowNotFoundError(AutomationError):
    """Raised when a specified window cannot be identified."""


class WindowOperationError(AutomationError):
    """Raised when a window manipulation fails."""


class URLSecurityError(AutomationError):
    """Raised when a URL violates safety policies."""


class VolumeControlError(AutomationError):
    """Raised when system audio levels cannot be queried or adjusted."""


class ScreenshotError(AutomationError):
    """Raised when screen capture fails."""


class PathTraversalError(AutomationError):
    """Raised when a target file path attempts to escape approved boundaries."""


class ConfirmationRequiredError(AutomationError):
    """Raised when an action requires explicit user confirmation before execution."""

    def __init__(self, token: str, action_name: str, message: str) -> None:
        super().__init__(message)
        self.token = token
        self.action_name = action_name


class ConfirmationInvalidError(AutomationError):
    """Raised when a confirmation token is expired, invalid, or already consumed."""


class PrivilegeError(AutomationError):
    """Raised when an action requires elevated permissions that are denied."""
