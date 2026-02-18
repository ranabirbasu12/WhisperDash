# tests/test_vad.py
import queue
from unittest.mock import MagicMock, patch

import numpy as np

from vad import SileroVAD, VADSegmenter, SealedSegment, VAD_WINDOW_SAMPLES


class FakeVAD:
    """Deterministic VAD for testing: returns preset probabilities."""

    def __init__(self, probs=None, threshold=0.5):
        self.threshold = threshold
        self._probs = probs or []
        self._call_count = 0
        self._available = True

    def __call__(self, audio_chunk):
        if self._call_count < len(self._probs):
            prob = self._probs[self._call_count]
        else:
            prob = 0.0
        self._call_count += 1
        return prob

    def reset(self):
        self._call_count = 0

    @property
    def is_available(self):
        return self._available


def test_silero_vad_graceful_when_unavailable():
    """Returns 0.0 when model is not loaded."""
    vad = SileroVAD()
    assert not vad.is_available
    assert vad(np.zeros(512, dtype=np.float32)) == 0.0


def test_silero_vad_load_missing_onnxruntime():
    """Returns False if onnxruntime is broken."""
    vad = SileroVAD()
    with patch("vad.os.path.exists", return_value=True):
        with patch("builtins.__import__", side_effect=ImportError("no ort")):
            assert vad.load() is False
    assert not vad.is_available


def test_segmenter_seals_on_silence_transition():
    """Feed speech chunks then silence chunks; segment appears in queue."""
    # 20 windows of speech (0.8) then 20 windows of silence (0.1)
    # At 512 samples/window, 20 silence windows = 10240 samples = 640ms > 600ms threshold
    probs = [0.8] * 20 + [0.1] * 20
    vad = FakeVAD(probs=probs, threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    # Feed enough audio for all 40 windows (40 * 512 = 20480 samples)
    # Feed in chunks of 1024 samples (realistic callback size)
    for _ in range(20):
        chunk = np.random.randn(1024).astype(np.float32) * 0.1
        seg.feed(chunk)

    # Should have one sealed segment
    assert not seg.segment_queue.empty()
    segment = seg.segment_queue.get_nowait()
    assert isinstance(segment, SealedSegment)
    assert segment.segment_index == 0
    assert segment.start_sample == 0
    assert len(segment.mic_audio) > 0


def test_segmenter_respects_minimum_duration():
    """Very short speech bursts (< 1s) are not sealed as independent segments."""
    # 2 windows speech + 20 windows silence = ~64ms speech, way under 1s minimum
    probs = [0.8] * 2 + [0.1] * 20
    vad = FakeVAD(probs=probs, threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    for _ in range(11):  # 11 * 1024 = 11264 samples, covers all 22 windows
        chunk = np.random.randn(1024).astype(np.float32) * 0.1
        seg.feed(chunk)

    # Segment too short, should NOT be sealed
    assert seg.segment_queue.empty()


def test_segmenter_seal_final():
    """Remaining audio is returned by seal_final()."""
    probs = [0.8] * 10  # All speech, no silence transition
    vad = FakeVAD(probs=probs, threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    # Feed 5120 samples of speech (10 windows)
    for _ in range(5):
        chunk = np.random.randn(1024).astype(np.float32) * 0.1
        seg.feed(chunk)

    # Queue should be empty (no silence transition)
    assert seg.segment_queue.empty()

    # seal_final should return the accumulated audio
    final = seg.seal_final()
    assert final is not None
    assert final.segment_index == 0
    assert len(final.mic_audio) == 5 * 1024


def test_segmenter_seal_final_too_short():
    """Very short final audio (< 100ms) is discarded."""
    vad = FakeVAD(probs=[0.8], threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    # Feed just 512 samples (32ms)
    seg.feed(np.random.randn(512).astype(np.float32))

    final = seg.seal_final()
    assert final is None  # < 100ms = 1600 samples


def test_segmenter_reset_clears_state():
    """Reset drains queue and resets all counters."""
    probs = [0.8] * 30 + [0.1] * 20
    vad = FakeVAD(probs=probs, threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    for _ in range(25):
        seg.feed(np.random.randn(1024).astype(np.float32) * 0.1)

    seg.reset()
    assert seg.segment_queue.empty()
    assert seg._segment_index == 0
    assert seg._global_sample_count == 0


def test_segmenter_tracks_sample_offsets():
    """Multiple sealed segments have correct cumulative offsets."""
    # Two speech-silence cycles, each long enough to seal
    speech_windows = 40  # 40 * 512 = 20480 samples > 16000 (1s min)
    silence_windows = 20  # 20 * 512 = 10240 samples > 9600 (600ms threshold)
    probs = ([0.8] * speech_windows + [0.1] * silence_windows) * 2
    vad = FakeVAD(probs=probs, threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)

    total_windows = len(probs)
    total_samples = total_windows * VAD_WINDOW_SAMPLES
    chunks_needed = total_samples // 1024 + 1

    for _ in range(chunks_needed):
        seg.feed(np.random.randn(1024).astype(np.float32) * 0.1)

    segments = []
    while not seg.segment_queue.empty():
        s = seg.segment_queue.get_nowait()
        if s is not None:
            segments.append(s)

    assert len(segments) >= 1
    # First segment starts at 0
    assert segments[0].start_sample == 0
    assert segments[0].end_sample == len(segments[0].mic_audio)
    # Second segment (if present) starts where first ended
    if len(segments) >= 2:
        assert segments[1].start_sample == segments[0].end_sample


def test_segmenter_signal_done():
    """signal_done puts None sentinel on queue."""
    vad = FakeVAD(threshold=0.5)
    seg = VADSegmenter(vad, sample_rate=16000)
    seg.signal_done()
    assert seg.segment_queue.get_nowait() is None
