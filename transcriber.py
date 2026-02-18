# transcriber.py
import tempfile
import os

import numpy as np
from scipy.io import wavfile
import mlx_whisper

MODEL_REPO = "mlx-community/whisper-large-v3-turbo"


def _model_is_cached(model_repo: str) -> bool:
    """Check if the model is already in the HuggingFace cache."""
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    safe_name = "models--" + model_repo.replace("/", "--")
    model_dir = os.path.join(cache_dir, safe_name, "snapshots")
    return os.path.isdir(model_dir) and len(os.listdir(model_dir)) > 0


class WhisperTranscriber:
    def __init__(self, model_repo: str = MODEL_REPO):
        self.model_repo = model_repo
        self.is_ready = False
        self.status = "not_started"  # not_started, downloading, loading, ready, error
        self.status_message = "Initializing..."

    def warmup(self):
        """Run a tiny transcription to pre-load the model into memory."""
        cached = _model_is_cached(self.model_repo)
        if cached:
            self.status = "loading"
            self.status_message = "Loading model into memory..."
        else:
            self.status = "downloading"
            self.status_message = "Downloading model (~1.5 GB)..."

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        silence = np.zeros(16000, dtype=np.int16)
        wavfile.write(tmp.name, 16000, silence)
        tmp.close()
        try:
            if not cached:
                # After download completes, status switches to loading
                # (mlx_whisper.transcribe handles download + load in one call)
                pass
            self.transcribe(tmp.name)
            # If we were downloading, the model is now also loaded
            self.status = "ready"
            self.status_message = "Ready"
            self.is_ready = True
        except Exception as e:
            self.status = "error"
            self.status_message = f"Error: {e}"
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def transcribe(self, audio_path: str) -> str:
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=self.model_repo,
            language="en",
            condition_on_previous_text=False,
        )
        self.is_ready = True
        return result["text"].strip()

    def transcribe_array(self, audio: np.ndarray) -> str:
        """Transcribe a numpy float32 audio array directly (no WAV file).

        Uses anti-hallucination parameters tuned for segmented audio.
        """
        result = mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.model_repo,
            language="en",
            condition_on_previous_text=False,
            hallucination_silence_threshold=2.0,
            compression_ratio_threshold=2.4,
        )
        self.is_ready = True
        return result["text"].strip()
