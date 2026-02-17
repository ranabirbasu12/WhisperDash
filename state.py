import threading
from enum import Enum


class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"


class AppStateManager:
    """Central state tracker with callback system for UI synchronization."""

    def __init__(self):
        self._state = AppState.IDLE
        self._state_callbacks: list = []
        self._amplitude_callbacks: list = []
        self._amplitudes: list[float] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> AppState:
        return self._state

    def set_state(self, new_state: AppState):
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        for cb in self._state_callbacks:
            try:
                cb(old, new_state)
            except Exception:
                pass

    def on_state_change(self, callback):
        self._state_callbacks.append(callback)

    def push_amplitude(self, value: float):
        with self._lock:
            self._amplitudes.append(value)
        for cb in self._amplitude_callbacks:
            try:
                cb(value)
            except Exception:
                pass

    def get_amplitudes(self) -> list[float]:
        with self._lock:
            amps = self._amplitudes[:]
            self._amplitudes.clear()
            return amps

    def on_amplitude(self, callback):
        self._amplitude_callbacks.append(callback)
