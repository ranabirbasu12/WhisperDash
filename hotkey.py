# hotkey.py
import os
import time
import threading

import Quartz
from Quartz import (
    CGEventTapCreate,
    CGEventTapEnable,
    CGEventGetIntegerValueField,
    CFMachPortCreateRunLoopSource,
    CFRunLoopGetCurrent,
    CFRunLoopAddSource,
    CFRunLoopRun,
    CFRunLoopStop,
    kCGHIDEventTap,
    kCGHeadInsertEventTap,
    kCGEventTapOptionDefault,
    kCGEventKeyDown,
    kCGEventKeyUp,
    kCGEventFlagsChanged,
    kCGEventTapDisabledByTimeout,
    kCGKeyboardEventKeycode,
    kCGKeyboardEventAutorepeat,
    kCFAllocatorDefault,
    kCFRunLoopCommonModes,
)

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard, paste_clipboard
from state import AppState, AppStateManager

# NX_SYSDEFINED event type for media/special function keys
NX_SYSDEFINED = 14
NX_SUBTYPE_AUX_CONTROL_BUTTONS = 8

# NX key types → serialized key names (for media keys in default MacBook mode)
NX_KEYTYPE_TO_NAME = {
    0: "f12",   # NX_KEYTYPE_SOUND_UP → Volume Up (F12 on MacBook)
    1: "f11",   # NX_KEYTYPE_SOUND_DOWN → Volume Down (F11 on MacBook)
    7: "f10",   # NX_KEYTYPE_MUTE → Mute (F10 on MacBook)
    16: "f8",   # NX_KEYTYPE_PLAY → Play/Pause (F8 on MacBook)
    17: "f9",   # NX_KEYTYPE_NEXT → Next Track (F9 on MacBook)
    18: "f7",   # NX_KEYTYPE_PREVIOUS → Previous Track (F7 on MacBook)
    2: "f2",    # NX_KEYTYPE_BRIGHTNESS_UP (F2 on MacBook)
    3: "f1",    # NX_KEYTYPE_BRIGHTNESS_DOWN (F1 on MacBook)
    21: "f6",   # NX_KEYTYPE_ILLUMINATION_UP (F6 on some MacBooks)
    22: "f6",   # NX_KEYTYPE_ILLUMINATION_DOWN (F6 on some MacBooks)
}


class GlobalHotkey:
    """Listens for a configurable key via HID-level CGEventTap.

    Uses kCGHIDEventTap to intercept keys BEFORE macOS processes them,
    allowing capture of system function keys (F5/dictation, brightness, etc.)
    that pynput's kCGSessionEventTap cannot see.
    """

    # Timing constants
    HOLD_THRESHOLD = 0.4       # seconds — above this = hold-to-talk
    DOUBLE_TAP_WINDOW = 0.5    # seconds — max gap between taps
    MAX_RECORD_SECONDS = 600   # 10 minutes
    WARNING_SECONDS = 540      # 9 minutes

    def __init__(
        self,
        recorder: AudioRecorder,
        transcriber: WhisperTranscriber,
        state_manager: AppStateManager,
        history=None,
        settings=None,
    ):
        self.recorder = recorder
        self.transcriber = transcriber
        self.state_manager = state_manager
        self.history = history
        self.is_recording = False
        self._processing = False

        # Configurable trigger key(s) — frozenset of macOS keycodes
        # Multiple keycodes for the same key (e.g. F5 = {96, 176} on MacBooks)
        if settings:
            self.trigger_keys = settings.hotkey_key
            settings.on_hotkey_change(self._on_hotkey_changed)
        else:
            self.trigger_keys = frozenset({61})  # Right Option

        # Whether the event tap has full (active) or listen-only access
        self.has_active_tap = False

        # Key capture mode (for settings UI)
        self._capture_mode = False
        self._captured_key: str | None = None

        # Double-tap state machine
        self.toggle_mode = False
        self.last_tap_time: float | None = None
        self.press_start_time: float = 0.0
        self._orphan_timer: threading.Timer | None = None
        self._warning_timer: threading.Timer | None = None
        self._max_timer: threading.Timer | None = None

        # CGEventTap state
        self._tap = None
        self._run_loop_ref = None
        self._held_modifiers: set[int] = set()

    # --- Key capture for settings UI ---

    def start_key_capture(self):
        """Enter capture mode — next key press will be captured for settings."""
        self._captured_key = None
        self._capture_mode = True

    def poll_key_capture(self) -> dict:
        """Return captured key if available."""
        if self._captured_key is not None:
            return {"captured": True, "key": self._captured_key}
        return {"captured": False}

    def cancel_key_capture(self):
        """Exit capture mode without saving."""
        self._capture_mode = False
        self._captured_key = None

    # --- CGEventTap callback ---

    def _event_callback(self, proxy, event_type, event, refcon):
        """CGEventTap callback — runs on the event tap thread."""
        if event_type == kCGEventTapDisabledByTimeout:
            if self._tap:
                CGEventTapEnable(self._tap, True)
            return event

        keycode = None
        is_press = None

        if event_type in (kCGEventKeyDown, kCGEventKeyUp):
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            is_press = (event_type == kCGEventKeyDown)
            is_repeat = bool(CGEventGetIntegerValueField(event, kCGKeyboardEventAutorepeat))
            if is_repeat:
                # Suppress repeats of trigger key, pass through others
                if self._capture_mode or keycode in self.trigger_keys:
                    return None
                return event

        elif event_type == kCGEventFlagsChanged:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            # Determine press vs release by tracking held modifiers
            if keycode in self._held_modifiers:
                is_press = False
                self._held_modifiers.discard(keycode)
            else:
                is_press = True
                self._held_modifiers.add(keycode)

        elif event_type == NX_SYSDEFINED:
            return self._handle_nx_event(event)

        else:
            return event

        if keycode is None:
            return event

        # Remember capture state before _on_press might change it
        was_capture = self._capture_mode

        if is_press:
            self._on_press(keycode)
        else:
            self._on_release(keycode)

        # Suppress trigger key and capture-mode keys
        if was_capture or keycode in self.trigger_keys:
            return None
        return event

    def _handle_nx_event(self, event):
        """Handle NX_SYSDEFINED events (media/special function keys on MacBooks)."""
        try:
            ns_event = Quartz.NSEvent.eventWithCGEvent_(event)
            if ns_event is None:
                return event
            if ns_event.subtype() != NX_SUBTYPE_AUX_CONTROL_BUTTONS:
                return event

            data1 = ns_event.data1()
            nx_key_type = (data1 & 0xFFFF0000) >> 16
            key_flags = data1 & 0x0000FFFF
            key_state = (key_flags & 0xFF00) >> 8
            is_press = (key_state == 0x0A)
            is_release = (key_state == 0x0B)

            if not (is_press or is_release):
                return event

            # Map NX key type to our serialized name
            name = NX_KEYTYPE_TO_NAME.get(nx_key_type)
            if not name:
                return event

            from config import NAME_TO_KEYCODE
            keycode = NAME_TO_KEYCODE.get(name)
            if keycode is None:
                return event

            was_capture = self._capture_mode

            if is_press:
                self._on_press(keycode)
            elif is_release:
                self._on_release(keycode)

            if was_capture or keycode in self.trigger_keys:
                return None
            return event

        except Exception:
            return event

    # --- Press/release handlers (also called directly by tests) ---

    def _on_press(self, keycode):
        # Capture mode: intercept any key for settings UI
        if self._capture_mode:
            from config import key_to_string
            serialized = key_to_string(keycode)
            if serialized:
                self._captured_key = serialized
                self._capture_mode = False
            return

        if keycode not in self.trigger_keys:
            return
        if self._processing:
            return
        if not self.transcriber.is_ready:
            return

        if self.toggle_mode and self.is_recording:
            # Already in toggle-recording mode — this press is a potential stop-tap
            self.press_start_time = time.time()
        elif not self.is_recording:
            # Start recording immediately (responsive for hold-to-talk)
            self._cancel_orphan_timer()
            self.is_recording = True
            self.recorder.start()
            self.state_manager.set_state(AppState.RECORDING)
            self.press_start_time = time.time()
            self._start_duration_timers()

    def _on_release(self, keycode):
        if keycode not in self.trigger_keys:
            return
        if not self.is_recording:
            return

        hold_duration = time.time() - self.press_start_time

        if self.toggle_mode:
            # In toggle mode — check for double-tap to stop
            if hold_duration < self.HOLD_THRESHOLD:
                if (self.last_tap_time is not None
                        and (time.time() - self.last_tap_time) < self.DOUBLE_TAP_WINDOW):
                    # Second tap within window → stop & transcribe
                    self.last_tap_time = None
                    self.toggle_mode = False
                    self.is_recording = False
                    self._cancel_duration_timers()
                    threading.Thread(target=self._process_recording, daemon=True).start()
                else:
                    # First tap in toggle mode — wait for potential second tap
                    self.last_tap_time = time.time()
            # Hold in toggle mode — ignore (user just held the key briefly)
        else:
            # Not in toggle mode
            if hold_duration >= self.HOLD_THRESHOLD:
                # Hold-to-talk: stop & transcribe
                self.is_recording = False
                self._cancel_duration_timers()
                threading.Thread(target=self._process_recording, daemon=True).start()
            else:
                # Short tap — check for double-tap to enter toggle mode
                if (self.last_tap_time is not None
                        and (time.time() - self.last_tap_time) < self.DOUBLE_TAP_WINDOW):
                    # Second tap within window → enter toggle mode, keep recording
                    self.last_tap_time = None
                    self.toggle_mode = True
                    self._cancel_orphan_timer()
                else:
                    # First tap — set orphan timer to cancel if no second tap
                    self.last_tap_time = time.time()
                    self._cancel_orphan_timer()
                    self._orphan_timer = threading.Timer(
                        self.DOUBLE_TAP_WINDOW, self._on_orphan_tap
                    )
                    self._orphan_timer.daemon = True
                    self._orphan_timer.start()

    # --- Orphan tap / timer handlers ---

    def _on_orphan_tap(self):
        """Single tap with no follow-up — cancel recording."""
        self.last_tap_time = None
        if self.is_recording and not self.toggle_mode:
            self.is_recording = False
            self._cancel_duration_timers()
            if self.recorder.is_recording:
                self.recorder.stop()  # discard audio
            self.state_manager.set_state(AppState.IDLE)

    def _cancel_orphan_timer(self):
        if self._orphan_timer is not None:
            self._orphan_timer.cancel()
            self._orphan_timer = None

    def _on_hotkey_changed(self, serialized: str):
        """Called when user changes the hotkey in settings."""
        from config import string_to_keycodes
        new_keycodes = string_to_keycodes(serialized)

        # If currently recording, cancel it cleanly
        if self.is_recording:
            self.toggle_mode = False
            self.is_recording = False
            self.last_tap_time = None
            self._cancel_orphan_timer()
            self._cancel_duration_timers()
            if self.recorder.is_recording:
                self.recorder.stop()
            self.state_manager.set_state(AppState.IDLE)

        self.trigger_keys = new_keycodes

    def _start_duration_timers(self):
        self._cancel_duration_timers()
        self._warning_timer = threading.Timer(
            self.WARNING_SECONDS, self._on_warning
        )
        self._warning_timer.daemon = True
        self._warning_timer.start()

        self._max_timer = threading.Timer(
            self.MAX_RECORD_SECONDS, self._on_max_duration
        )
        self._max_timer.daemon = True
        self._max_timer.start()

    def _cancel_duration_timers(self):
        if self._warning_timer is not None:
            self._warning_timer.cancel()
            self._warning_timer = None
        if self._max_timer is not None:
            self._max_timer.cancel()
            self._max_timer = None

    def _on_warning(self):
        self.state_manager.push_warning("Recording ends in 1 minute")

    def _on_max_duration(self):
        """Force stop recording after max duration."""
        if self.is_recording:
            self.toggle_mode = False
            self.is_recording = False
            self.last_tap_time = None
            self._cancel_duration_timers()
            threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self):
        """Stop recording, transcribe, copy to clipboard."""
        self._processing = True
        self.state_manager.set_state(AppState.PROCESSING)
        try:
            wav_path = self.recorder.stop()
            if not wav_path:
                self.state_manager.set_state(AppState.IDLE)
                return
            start_time = time.time()
            text = self.transcriber.transcribe(wav_path)
            elapsed = round(time.time() - start_time, 2)
            if text:
                copy_to_clipboard(text)
                paste_clipboard()
                if self.history:
                    self.history.add(text, latency=elapsed)
            try:
                os.unlink(wav_path)
            except OSError:
                pass
            self.state_manager.set_state(AppState.IDLE)
        except Exception as e:
            print(f"Hotkey transcription error: {e}")
            self.state_manager.set_state(AppState.ERROR)
            threading.Timer(1.0, lambda: self.state_manager.set_state(AppState.IDLE)).start()
        finally:
            self._processing = False

    # --- Lifecycle ---

    def start(self):
        """Start HID-level event tap in a background thread.

        Tries active tap first (can suppress system key actions like dictation).
        Falls back to listen-only tap if Accessibility permission is missing.
        """
        event_mask = (
            (1 << kCGEventKeyDown)
            | (1 << kCGEventKeyUp)
            | (1 << kCGEventFlagsChanged)
            | (1 << NX_SYSDEFINED)
        )

        # Try active tap first (requires Accessibility permission)
        self._tap = CGEventTapCreate(
            kCGHIDEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            event_mask,
            self._event_callback,
            None,
        )

        if self._tap is not None:
            self.has_active_tap = True
            print("HID event tap: active mode (can suppress system key actions)")
        else:
            # Fall back to listen-only (requires Input Monitoring permission)
            self._tap = CGEventTapCreate(
                kCGHIDEventTap,
                kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionListenOnly,
                event_mask,
                self._event_callback,
                None,
            )
            if self._tap is not None:
                print(
                    "HID event tap: listen-only mode (system key actions still fire).\n"
                    "For full suppression, grant Accessibility permission in:\n"
                    "  System Settings > Privacy & Security > Accessibility"
                )
            else:
                print(
                    "ERROR: Failed to create any event tap.\n"
                    "Grant Input Monitoring permission in:\n"
                    "  System Settings > Privacy & Security > Input Monitoring"
                )
                return

        source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, self._tap, 0)
        thread = threading.Thread(target=self._run_tap, args=(source,), daemon=True)
        thread.start()

    def _run_tap(self, source):
        """Run the event tap's CFRunLoop (blocks until stopped)."""
        self._run_loop_ref = CFRunLoopGetCurrent()
        CFRunLoopAddSource(self._run_loop_ref, source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        CFRunLoopRun()

    def stop(self):
        if self._tap:
            CGEventTapEnable(self._tap, False)
            self._tap = None
        if self._run_loop_ref:
            CFRunLoopStop(self._run_loop_ref)
            self._run_loop_ref = None
        self._cancel_orphan_timer()
        self._cancel_duration_timers()
