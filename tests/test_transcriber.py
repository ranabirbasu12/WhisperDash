# tests/test_transcriber.py
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
    )


@patch("transcriber.mlx_whisper.transcribe")
def test_transcribe_strips_whitespace(mock_transcribe):
    mock_transcribe.return_value = {"text": "  Some text  "}
    t = WhisperTranscriber()
    t.is_ready = True
    result = t.transcribe("/tmp/test.wav")
    assert result == "Some text"
