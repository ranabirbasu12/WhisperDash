# hotkey.py
import os
import subprocess
import time
import threading
from pynput import keyboard

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard


def _paste():
    """Simulate Cmd+V using AppleScript (more reliable than pynput Controller)."""
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using command down'],
        capture_output=True,
    )


class GlobalHotkey:
    """Listens for Right Option key to trigger push-to-talk recording."""

    TRIGGER_KEY = keyboard.Key.alt_r

    def __init__(self, recorder: AudioRecorder, transcriber: WhisperTranscriber):
        self.recorder = recorder
        self.transcriber = transcriber
        self.is_recording = False
        self._listener = None
        self._processing = False

    def _on_press(self, key):
        if key != self.TRIGGER_KEY:
            return
        if self.is_recording or self._processing:
            return
        if not self.transcriber.is_ready:
            return
        self.is_recording = True
        self.recorder.start()

    def _on_release(self, key):
        if key != self.TRIGGER_KEY:
            return
        if not self.is_recording:
            return
        self.is_recording = False
        threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self):
        """Stop recording, transcribe, copy to clipboard, and paste."""
        self._processing = True
        try:
            wav_path = self.recorder.stop()
            if not wav_path:
                return
            text = self.transcriber.transcribe(wav_path)
            if text:
                copy_to_clipboard(text)
                time.sleep(0.05)
                _paste()
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
