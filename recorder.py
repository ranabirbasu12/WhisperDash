# recorder.py
import tempfile
import numpy as np
import sounddevice as sd
from scipy.io import wavfile

SAMPLE_RATE = 16000


class AudioRecorder:
    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.channels = 1
        self.is_recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None

    def _audio_callback(self, indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            self._chunks.append(indata.copy())

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.float32,
            callback=self._audio_callback,
        )
        self._stream.start()
        self.is_recording = True

    def stop(self) -> str:
        self.is_recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._chunks:
            return ""

        audio = np.concatenate(self._chunks, axis=0)
        audio_int16 = np.int16(audio * 32767)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wavfile.write(tmp.name, self.sample_rate, audio_int16)
        tmp.close()
        return tmp.name
