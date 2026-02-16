# transcriber.py
import tempfile
import os

import numpy as np
from scipy.io import wavfile
import mlx_whisper

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"


class WhisperTranscriber:
    def __init__(self, model_repo: str = MODEL_REPO):
        self.model_repo = model_repo
        self.is_ready = False

    def load_model(self):
        """Warm up the model by running a dummy transcription."""
        # mlx_whisper loads the model lazily on first transcribe call.
        # We mark ready after the first successful call in the app.
        self.is_ready = True

    def warmup(self):
        """Run a tiny transcription to pre-load the model into memory."""
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        silence = np.zeros(16000, dtype=np.int16)  # 1 second of silence
        wavfile.write(tmp.name, 16000, silence)
        tmp.close()
        try:
            self.transcribe(tmp.name)
        except Exception:
            pass
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        self.is_ready = True

    def transcribe(self, audio_path: str) -> str:
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_repo,
            language="en",
        )
        self.is_ready = True
        return result["text"].strip()
