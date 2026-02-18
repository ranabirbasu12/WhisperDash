# tests/test_transcriber.py
import numpy as np
from unittest.mock import patch
from transcriber import WhisperTranscriber


def test_transcriber_initializes_with_model_name():
    t = WhisperTranscriber()
    assert t.model_repo == "mlx-community/whisper-large-v3-turbo"
    assert t.is_ready is False
    assert t.status == "not_started"


@patch("transcriber.mlx_whisper.transcribe")
def test_transcribe_returns_text(mock_transcribe):
    mock_transcribe.return_value = {"text": " Hello world."}
    t = WhisperTranscriber()
    t.is_ready = True
    result = t.transcribe("/tmp/test.wav")
    assert result == "Hello world."
    mock_transcribe.assert_called_once_with(
        "/tmp/test.wav",
        path_or_hf_repo="mlx-community/whisper-large-v3-turbo",
        language="en",
        condition_on_previous_text=False,
    )


@patch("transcriber.mlx_whisper.transcribe")
def test_transcribe_strips_whitespace(mock_transcribe):
    mock_transcribe.return_value = {"text": "  Some text  "}
    t = WhisperTranscriber()
    t.is_ready = True
    result = t.transcribe("/tmp/test.wav")
    assert result == "Some text"


@patch("transcriber.mlx_whisper.transcribe")
def test_transcribe_array_passes_numpy(mock_transcribe):
    """transcribe_array() passes numpy array with anti-hallucination params."""
    mock_transcribe.return_value = {"text": " Hello from array."}
    t = WhisperTranscriber()
    t.is_ready = True
    audio = np.zeros(16000, dtype=np.float32)
    result = t.transcribe_array(audio)
    assert result == "Hello from array."
    call_kwargs = mock_transcribe.call_args[1]
    assert call_kwargs["condition_on_previous_text"] is False
    assert call_kwargs["hallucination_silence_threshold"] == 2.0
    assert call_kwargs["compression_ratio_threshold"] == 2.4
