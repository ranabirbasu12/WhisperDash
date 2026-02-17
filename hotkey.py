# hotkey.py
import os
import time
import threading
from pynput import keyboard

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard
from state import AppState, AppStateManager


class GlobalHotkey:
    """Listens for Right Option key to trigger push-to-talk or double-tap toggle recording."""

    TRIGGER_KEY = keyboard.Key.alt_r

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
    ):
        self.recorder = recorder
        self.transcriber = transcriber
        self.state_manager = state_manager
        self.history = history
        self.is_recording = False
        self._listener = None
        self._processing = False

        # Double-tap state machine
        self.toggle_mode = False
        self.last_tap_time: float | None = None
        self.press_start_time: float = 0.0
        self._orphan_timer: threading.Timer | None = None
        self._warning_timer: threading.Timer | None = None
        self._max_timer: threading.Timer | None = None

    def _on_press(self, key):
        if key != self.TRIGGER_KEY:
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

    def _on_release(self, key):
        if key != self.TRIGGER_KEY:
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

    def start(self):
        """Start listening for the global hotkey in a background thread."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()
        self._cancel_orphan_timer()
        self._cancel_duration_timers()
