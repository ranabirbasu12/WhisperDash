# system_audio.py
"""Capture system audio output via ScreenCaptureKit for echo cancellation."""
import threading

import objc
import numpy as np
import CoreMedia
import ScreenCaptureKit
from Foundation import NSObject


class _AudioHandler(NSObject):
    """Receives audio sample buffers from SCStream."""

    def initWithChunks_(self, chunks_list):
        self = objc.super(_AudioHandler, self).init()
        if self is not None:
            self._chunks = chunks_list
        return self

    def stream_didOutputSampleBuffer_ofType_(self, stream, sample_buffer, output_type):
        if output_type != ScreenCaptureKit.SCStreamOutputTypeAudio:
            return
        try:
            block_buf = CoreMedia.CMSampleBufferGetDataBuffer(sample_buffer)
            if block_buf is None:
                return
            length = CoreMedia.CMBlockBufferGetDataLength(block_buf)
            result = CoreMedia.CMBlockBufferCopyDataBytes(block_buf, 0, length, None)
            if result is not None:
                _, raw_bytes = result
                audio = np.frombuffer(raw_bytes, dtype=np.float32).copy()
                self._chunks.append(audio)
        except Exception:
            pass


class SystemAudioCapture:
    """Captures system audio output at 16kHz mono via ScreenCaptureKit."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._stream = None
        self._handler = None
        self._chunks: list[np.ndarray] = []
        self._available = True

    def start(self):
        """Start capturing system audio. Non-blocking."""
        self._chunks = []

        # Get shareable content (async → sync)
        event = threading.Event()
        result = {}

        def on_content(content, error):
            result["content"] = content
            result["error"] = error
            event.set()

        ScreenCaptureKit.SCShareableContent \
            .getShareableContentExcludingDesktopWindows_onScreenWindowsOnly_completionHandler_(
                True, True, on_content
            )

        if not event.wait(timeout=3):
            print("SystemAudio: timeout getting shareable content")
            self._available = False
            return

        if result.get("error") or not result.get("content"):
            print(f"SystemAudio: {result.get('error', 'no content')}")
            self._available = False
            return

        displays = result["content"].displays()
        if not displays:
            print("SystemAudio: no displays found")
            self._available = False
            return

        # Configure for audio-only capture
        config = ScreenCaptureKit.SCStreamConfiguration.alloc().init()
        config.setCapturesAudio_(True)
        config.setExcludesCurrentProcessAudio_(True)
        config.setSampleRate_(float(self.sample_rate))
        config.setChannelCount_(1)
        # Minimize video overhead
        config.setWidth_(2)
        config.setHeight_(2)
        config.setMinimumFrameInterval_(CoreMedia.CMTimeMake(1, 1))

        content_filter = ScreenCaptureKit.SCContentFilter.alloc() \
            .initWithDisplay_excludingApplications_exceptingWindows_(
                displays[0], [], []
            )

        self._handler = _AudioHandler.alloc().initWithChunks_(self._chunks)

        self._stream = ScreenCaptureKit.SCStream.alloc() \
            .initWithFilter_configuration_delegate_(content_filter, config, None)

        self._stream.addStreamOutput_type_sampleHandlerQueue_error_(
            self._handler, ScreenCaptureKit.SCStreamOutputTypeAudio, None, None
        )

        # Start capture (async → sync)
        start_event = threading.Event()

        def on_start(error):
            if error:
                print(f"SystemAudio: start error: {error}")
                self._available = False
            start_event.set()

        self._stream.startCaptureWithCompletionHandler_(on_start)
        start_event.wait(timeout=3)

    def stop(self) -> np.ndarray:
        """Stop capture and return the captured audio as a float32 numpy array."""
        if self._stream is not None:
            event = threading.Event()
            self._stream.stopCaptureWithCompletionHandler_(lambda err: event.set())
            event.wait(timeout=3)
            self._stream = None
            self._handler = None

        if not self._chunks:
            return np.array([], dtype=np.float32)

        return np.concatenate(self._chunks, axis=0)

    @property
    def is_available(self) -> bool:
        return self._available
