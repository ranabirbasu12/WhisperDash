# aec.py
"""Acoustic Echo Cancellation using NLMS adaptive filter."""
import numpy as np


def nlms_echo_cancel(
    mic: np.ndarray,
    ref: np.ndarray,
    filter_len: int = 1600,
    step_size: float = 0.5,
    block_size: int = 256,
) -> np.ndarray:
    """Remove echo of `ref` (system audio) from `mic` (microphone) signal.

    Uses block NLMS (Normalized Least Mean Squares) adaptive filtering.
    The filter learns how the system audio leaks into the mic (through
    speakers → room → mic) and subtracts that estimated echo.

    Args:
        mic: Microphone signal (voice + echo), float32.
        ref: Reference signal (system audio output), float32, same sample rate.
        filter_len: Adaptive filter length in samples. At 16kHz, 1600 = 100ms
                     of echo tail. Covers room reflections + speaker-to-mic delay.
        step_size: NLMS step size (0 < mu <= 1). Higher = faster adaptation,
                    more noise. 0.5 is a good default.
        block_size: Process this many samples at a time for efficiency.

    Returns:
        Estimated voice signal (mic with echo removed), float32.
    """
    n = min(len(mic), len(ref))
    if n < filter_len:
        return mic[:n].copy()

    output = np.zeros(n, dtype=np.float32)
    output[:filter_len] = mic[:filter_len]
    w = np.zeros(filter_len, dtype=np.float64)
    eps = 1e-8

    for start in range(filter_len, n, block_size):
        end = min(start + block_size, n)
        blen = end - start

        # Build reference matrix: each row is ref[i-L:i] reversed (convolution)
        ref_matrix = np.zeros((blen, filter_len), dtype=np.float64)
        for j in range(blen):
            idx = start + j
            ref_matrix[j] = ref[idx - filter_len:idx][::-1]

        # Filter output = estimated echo for this block
        echo_est = ref_matrix @ w

        # Error = mic - echo estimate ≈ voice
        mic_block = mic[start:end].astype(np.float64)
        error = mic_block - echo_est
        output[start:end] = error.astype(np.float32)

        # NLMS weight update using block mean gradient
        norms = np.sum(ref_matrix ** 2, axis=1, keepdims=True) + eps
        gradients = ref_matrix * (error[:, np.newaxis] / norms)
        w += step_size * np.mean(gradients, axis=0)

    return output
