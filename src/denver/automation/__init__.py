"""Denver Desktop Automation and System Control Subsystem."""

from denver.automation.applications import ApplicationController
from denver.automation.browser import BrowserController, validate_and_normalize_url
from denver.automation.confirmation import ConfirmationManager
from denver.automation.errors import (
    ApplicationCloseError,
    ApplicationLaunchError,
    ApplicationNotFoundError,
    AutomationError,
    ConfirmationInvalidError,
    ConfirmationRequiredError,
    PathTraversalError,
    PrivilegeError,
    ScreenshotError,
    URLSecurityError,
    VolumeControlError,
    WindowNotFoundError,
    WindowOperationError,
)
from denver.automation.executor import AutomationExecutor
from denver.automation.fake import (
    FakeApplicationController,
    FakeBrowserController,
    FakeScreenshotController,
    FakeSystemController,
    FakeVolumeController,
    FakeWindowController,
)
from denver.automation.models import (
    ApplicationTarget,
    AutomationAction,
    AutomationRequest,
    AutomationResult,
    AutomationRisk,
    BrowserTarget,
    ConfirmationRequirement,
    ScreenshotResult,
    VolumeCommand,
    WindowInfo,
    WindowTarget,
)
from denver.automation.registry import AutomationRegistry
from denver.automation.screenshot import ScreenshotController
from denver.automation.system import SystemController
from denver.automation.vision import VisionAnalysisResult, VisionEngine
from denver.automation.volume import VolumeController
from denver.automation.web_agent import WebActionResult, WebAgent, WebSearchResult
from denver.automation.windows import WindowsNativeAPI
from denver.automation.windows_manager import WindowManager

__all__ = [
    "ApplicationCloseError",
    "ApplicationController",
    "ApplicationLaunchError",
    "ApplicationNotFoundError",
    "ApplicationTarget",
    "AutomationAction",
    "AutomationError",
    "AutomationExecutor",
    "AutomationRegistry",
    "AutomationRequest",
    "AutomationResult",
    "AutomationRisk",
    "BrowserController",
    "BrowserTarget",
    "ConfirmationInvalidError",
    "ConfirmationManager",
    "ConfirmationRequiredError",
    "ConfirmationRequirement",
    "FakeApplicationController",
    "FakeBrowserController",
    "FakeScreenshotController",
    "FakeSystemController",
    "FakeVolumeController",
    "FakeWindowController",
    "PathTraversalError",
    "PrivilegeError",
    "ScreenshotController",
    "ScreenshotError",
    "SystemController",
    "URLSecurityError",
    "VisionAnalysisResult",
    "VisionEngine",
    "VolumeCommand",
    "VolumeControlError",
    "VolumeController",
    "WebActionResult",
    "WebAgent",
    "WebSearchResult",
    "WindowInfo",
    "WindowManager",
    "WindowNotFoundError",
    "WindowOperationError",
    "WindowsNativeAPI",
    "WindowTarget",
    "validate_and_normalize_url",
]
