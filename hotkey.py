# hotkey.py
import threading
from pynput import keyboard

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard


class GlobalHotkey:
    """Listens for Cmd+Shift+Space to trigger push-to-talk recording."""

    def __init__(self, recorder: AudioRecorder, transcriber: WhisperTranscriber):
        self.recorder = recorder
        self.transcriber = transcriber
        self.is_recording = False
        self._pressed_keys = set()
        self._listener = None
        self._processing = False

    def _should_activate(self) -> bool:
        """Check if the hotkey combo (Cmd+Shift+Space) is active."""
        has_cmd = (
            keyboard.Key.cmd in self._pressed_keys
            or keyboard.Key.cmd_l in self._pressed_keys
            or keyboard.Key.cmd_r in self._pressed_keys
        )
        has_shift = (
            keyboard.Key.shift in self._pressed_keys
            or keyboard.Key.shift_l in self._pressed_keys
            or keyboard.Key.shift_r in self._pressed_keys
        )
        has_space = keyboard.Key.space in self._pressed_keys
        return has_cmd and has_shift and has_space

    def _on_press(self, key):
        self._pressed_keys.add(key)
        if self._should_activate() and not self.is_recording and not self._processing:
            if not self.transcriber.is_ready:
                return
            self.is_recording = True
            self.recorder.start()

    def _on_release(self, key):
        was_active = self._should_activate()
        self._pressed_keys.discard(key)

        if was_active and self.is_recording and not self._should_activate():
            self.is_recording = False
            threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self):
        """Stop recording, transcribe, copy to clipboard."""
        self._processing = True
        try:
            wav_path = self.recorder.stop()
            if not wav_path:
                return
            text = self.transcriber.transcribe(wav_path)
            if text:
                copy_to_clipboard(text)
            import os
            try:
                os.unlink(wav_path)
            except OSError:
                pass
        except Exception as e:
            print(f"Hotkey transcription error: {e}")
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
