# tests/test_recorder.py
import numpy as np
from unittest.mock import patch, MagicMock
from recorder import AudioRecorder

SAMPLE_RATE = 16000


def test_recorder_initializes_with_correct_settings():
    rec = AudioRecorder()
    assert rec.sample_rate == SAMPLE_RATE
    assert rec.channels == 1
    assert rec.is_recording is False


def test_recorder_start_sets_recording_flag():
    rec = AudioRecorder()
    with patch.object(rec, '_stream', create=True):
        with patch('recorder.sd.InputStream') as mock_stream:
            mock_instance = MagicMock()
            mock_stream.return_value = mock_instance
            rec.start()
            assert rec.is_recording is True
            mock_instance.start.assert_called_once()


def test_recorder_stop_returns_wav_path():
    rec = AudioRecorder()
    rec.is_recording = True
    rec._chunks = [np.zeros((1600, 1), dtype=np.float32)]
    with patch('recorder.sd.InputStream'):
        rec._stream = MagicMock()
        path = rec.stop()
        assert path.endswith('.wav')
        assert rec.is_recording is False


def test_recorder_callback_appends_chunks():
    rec = AudioRecorder()
    rec.is_recording = True
    rec._chunks = []
    fake_data = np.random.randn(1600, 1).astype(np.float32)
    rec._audio_callback(fake_data, 1600, None, None)
    assert len(rec._chunks) == 1
    np.testing.assert_array_equal(rec._chunks[0], fake_data)


def test_recorder_stop_empty_returns_empty_string():
    rec = AudioRecorder()
    rec.is_recording = True
    rec._chunks = []
    rec._stream = MagicMock()
    path = rec.stop()
    assert path == ""
