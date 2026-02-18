# tests/test_aec.py
import numpy as np
from aec import nlms_echo_cancel


def test_silent_ref_passes_mic_through():
    """When system audio is silent, mic signal passes through unchanged."""
    mic = np.random.randn(8000).astype(np.float32) * 0.1
    ref = np.zeros(8000, dtype=np.float32)
    out = nlms_echo_cancel(mic, ref)
    # Output should be very close to mic (no echo to remove)
    np.testing.assert_allclose(out, mic, atol=1e-4)


def test_cancels_echo_of_known_signal():
    """Echo of a known signal should be significantly reduced."""
    np.random.seed(42)
    n = 16000  # 1 second at 16kHz

    # System audio: a tone
    ref = (np.sin(2 * np.pi * 440 * np.arange(n) / 16000) * 0.3).astype(np.float32)

    # Simulate echo: delayed and attenuated copy of ref
    echo = np.zeros(n, dtype=np.float32)
    delay = 100  # samples
    echo[delay:] = ref[:-delay] * 0.5

    # Voice: different frequency
    voice = (np.sin(2 * np.pi * 200 * np.arange(n) / 16000) * 0.2).astype(np.float32)

    # Mic = voice + echo
    mic = voice + echo

    out = nlms_echo_cancel(mic, ref, filter_len=800, step_size=0.5)

    # After convergence (skip first 2000 samples), echo should be reduced
    converged = out[2000:]
    mic_converged = mic[2000:]
    voice_converged = voice[2000:]

    # Output should be closer to voice than the raw mic was
    error_before = np.mean((mic_converged - voice_converged) ** 2)
    error_after = np.mean((converged - voice_converged) ** 2)
    assert error_after < error_before * 0.5  # at least 50% reduction


def test_short_signal_returns_copy():
    """Signals shorter than filter length just return a copy of mic."""
    mic = np.ones(100, dtype=np.float32)
    ref = np.ones(100, dtype=np.float32)
    out = nlms_echo_cancel(mic, ref, filter_len=200)
    np.testing.assert_array_equal(out, mic)


def test_different_length_signals():
    """Handles mic and ref of different lengths (uses shorter)."""
    mic = np.random.randn(10000).astype(np.float32) * 0.1
    ref = np.random.randn(8000).astype(np.float32) * 0.1
    out = nlms_echo_cancel(mic, ref)
    assert len(out) == 8000  # min of both lengths
