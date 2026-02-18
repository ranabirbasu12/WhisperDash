# recorder.py
import tempfile
import wave
import numpy as np
import sounddevice as sd
from scipy.io import wavfile

SAMPLE_RATE = 16000


def get_wav_duration(path: str) -> float:
    """Return duration of a WAV file in seconds."""
    with wave.open(path, "r") as wf:
        return wf.getnframes() / wf.getframerate()


class AudioRecorder:
    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.channels = 1
        self.is_recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._sys_capture = None
        self.on_amplitude = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            self._chunks.append(indata.copy())
            if self.on_amplitude is not None:
                rms = float(np.sqrt(np.mean(indata ** 2)))
                self.on_amplitude(rms)

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.float32,
            callback=self._audio_callback,
        )

        # Start system audio capture for echo cancellation
        try:
            from system_audio import SystemAudioCapture
            self._sys_capture = SystemAudioCapture(sample_rate=self.sample_rate)
            self._sys_capture.start()
        except Exception as e:
            print(f"System audio capture unavailable: {e}")
            self._sys_capture = None

        self._stream.start()
        self.is_recording = True

    def stop(self) -> str:
        self.is_recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        # Get system audio reference
        sys_audio = None
        if self._sys_capture is not None:
            try:
                sys_audio = self._sys_capture.stop()
            except Exception:
                pass
            self._sys_capture = None

        if not self._chunks:
            return ""

        chunks = self._chunks
        self._chunks = []

        audio = np.concatenate(chunks, axis=0).flatten()
        del chunks

        # Apply echo cancellation if we have system audio
        if sys_audio is not None and len(sys_audio) > 0:
            try:
                from aec import nlms_echo_cancel, noise_gate
                audio = nlms_echo_cancel(audio, sys_audio)
                audio = noise_gate(audio, sample_rate=self.sample_rate)
            except Exception as e:
                print(f"AEC failed, using raw audio: {e}")
        del sys_audio

        audio_int16 = np.int16(np.clip(audio, -1.0, 1.0) * 32767)
        del audio

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wavfile.write(tmp.name, self.sample_rate, audio_int16)
        tmp.close()
        del audio_int16
        return tmp.name
