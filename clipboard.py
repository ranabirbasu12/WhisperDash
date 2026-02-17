import time

import pyperclip
import Quartz
from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventSetFlags,
    CGEventPost,
    CGEventSourceCreate,
    kCGHIDEventTap,
    kCGEventFlagMaskCommand,
    kCGEventSourceStateCombinedSessionState,
)

# macOS keycode for 'V'
_KC_V = 9


def copy_to_clipboard(text: str) -> None:
    pyperclip.copy(text)


def paste_clipboard() -> None:
    """Simulate Cmd+V to paste into the currently focused input field."""
    # Small delay to ensure clipboard is updated
    time.sleep(0.05)

    # Create a proper event source so macOS treats the events as legitimate
    source = CGEventSourceCreate(kCGEventSourceStateCombinedSessionState)

    # Key down: V with Command modifier
    event_down = CGEventCreateKeyboardEvent(source, _KC_V, True)
    CGEventSetFlags(event_down, kCGEventFlagMaskCommand)

    # Key up: V with Command modifier
    event_up = CGEventCreateKeyboardEvent(source, _KC_V, False)
    CGEventSetFlags(event_up, kCGEventFlagMaskCommand)

    # Post at HID level so events go through the full macOS event pipeline
    CGEventPost(kCGHIDEventTap, event_down)
    time.sleep(0.01)
    CGEventPost(kCGHIDEventTap, event_up)
