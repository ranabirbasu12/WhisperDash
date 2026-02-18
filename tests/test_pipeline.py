# tests/test_pipeline.py
import time
import numpy as np
from unittest.mock import MagicMock, patch

from pipeline import StreamingPipeline, SegmentResult
from vad import SealedSegment


class FakePipeline(StreamingPipeline):
    """Pipeline with mocked VAD for testing."""

    def __init__(self, transcriber, sample_rate=16000):
        super().__init__(transcriber, sample_rate)
        # Override VAD to always be available
        self._vad_loaded = True
        self._vad._available = True


def _make_transcriber(text="Hello."):
    txr = MagicMock()
    txr.transcribe_array = MagicMock(return_value=text)
    return txr


def test_pipeline_vad_not_available_fallback():
    """Pipeline returns empty results when VAD is not loaded."""
    txr = _make_transcriber()
    pipe = StreamingPipeline(txr)
    assert not pipe.vad_available
    pipe.start()
    assert not pipe._active  # Should not activate
    results = pipe.stop(None)
    assert results == []


def test_pipeline_process_segment_transcribes():
    """_process_segment returns a SegmentResult on success."""
    txr = _make_transcriber("Hello world.")
    pipe = FakePipeline(txr)
    segment = SealedSegment(
        segment_index=0,
        mic_audio=np.random.randn(16000).astype(np.float32),
        start_sample=0,
        end_sample=16000,
    )
    result = pipe._process_segment(segment, None)
    assert result is not None
    assert result.text == "Hello world."
    assert result.segment_index == 0
    assert abs(result.audio_duration - 1.0) < 0.01


def test_pipeline_process_segment_with_aec():
    """_process_segment applies AEC when system audio is provided."""
    txr = _make_transcriber("Clean audio.")
    pipe = FakePipeline(txr)
    segment = SealedSegment(
        segment_index=0,
        mic_audio=np.random.randn(16000).astype(np.float32),
        start_sample=0,
        end_sample=16000,
    )
    sys_audio = np.random.randn(16000).astype(np.float32) * 0.1
    with patch("aec.nlms_echo_cancel", return_value=segment.mic_audio), \
         patch("aec.noise_gate", return_value=segment.mic_audio):
        result = pipe._process_segment(segment, sys_audio)
    assert result is not None
    assert result.text == "Clean audio."


def test_pipeline_process_segment_empty_text():
    """_process_segment returns None when transcription is empty."""
    txr = _make_transcriber("")
    pipe = FakePipeline(txr)
    segment = SealedSegment(
        segment_index=0,
        mic_audio=np.random.randn(16000).astype(np.float32),
        start_sample=0,
        end_sample=16000,
    )
    result = pipe._process_segment(segment, None)
    assert result is None


def test_pipeline_align_sys_audio():
    """System audio alignment extracts correct slice."""
    pipe = FakePipeline(_make_transcriber())
    sys_audio = np.arange(32000, dtype=np.float32)

    # Extract samples 8000-16000
    ref = pipe._align_sys_audio(sys_audio, 8000, 16000)
    assert ref is not None
    assert len(ref) == 8000
    np.testing.assert_array_equal(ref, np.arange(8000, 16000, dtype=np.float32))


def test_pipeline_align_sys_audio_pads_when_short():
    """When system audio is shorter than needed, pad with zeros."""
    pipe = FakePipeline(_make_transcriber())
    sys_audio = np.ones(10000, dtype=np.float32)

    ref = pipe._align_sys_audio(sys_audio, 8000, 16000)
    assert ref is not None
    assert len(ref) == 8000
    # First 2000 from sys_audio[8000:10000], rest zeros
    np.testing.assert_array_equal(ref[:2000], np.ones(2000, dtype=np.float32))
    np.testing.assert_array_equal(ref[2000:], np.zeros(6000, dtype=np.float32))


def test_pipeline_align_sys_audio_beyond_range():
    """When segment starts beyond system audio, returns None."""
    pipe = FakePipeline(_make_transcriber())
    sys_audio = np.ones(5000, dtype=np.float32)
    ref = pipe._align_sys_audio(sys_audio, 8000, 16000)
    assert ref is None


def test_pipeline_ordered_results():
    """Results are returned sorted by segment_index."""
    txr = MagicMock()
    call_count = [0]

    def mock_transcribe(audio):
        call_count[0] += 1
        return f"Segment {call_count[0]}."

    txr.transcribe_array = mock_transcribe
    pipe = FakePipeline(txr)

    # Manually set results out of order
    with pipe._results_lock:
        pipe._results = [
            SegmentResult(segment_index=2, text="Third.", audio_duration=1.0),
            SegmentResult(segment_index=0, text="First.", audio_duration=1.0),
            SegmentResult(segment_index=1, text="Second.", audio_duration=1.0),
        ]

    pipe._active = True
    pipe._segmenter = MagicMock()
    pipe._segmenter.seal_final.return_value = None
    pipe._segmenter.signal_done = MagicMock()
    pipe._segmenter.segment_queue = MagicMock()
    pipe._worker_thread = None

    results = pipe.stop(None)
    assert [r.text for r in results] == ["First.", "Second.", "Third."]


def test_pipeline_get_sys_audio_snapshot():
    """Snapshot concatenates available system audio chunks."""
    pipe = FakePipeline(_make_transcriber())
    pipe._sys_audio_chunks = [
        np.ones(1000, dtype=np.float32),
        np.ones(2000, dtype=np.float32) * 2,
    ]
    snapshot = pipe._get_sys_audio_snapshot()
    assert snapshot is not None
    assert len(snapshot) == 3000
    assert snapshot[0] == 1.0
    assert snapshot[1500] == 2.0


def test_pipeline_get_sys_audio_snapshot_none():
    """Snapshot returns None when no system audio."""
    pipe = FakePipeline(_make_transcriber())
    pipe._sys_audio_chunks = None
    assert pipe._get_sys_audio_snapshot() is None


def test_pipeline_get_sys_audio_snapshot_empty():
    """Snapshot returns None when chunk list is empty."""
    pipe = FakePipeline(_make_transcriber())
    pipe._sys_audio_chunks = []
    assert pipe._get_sys_audio_snapshot() is None
