# tests/test_hotkey.py
import time
from unittest.mock import MagicMock, patch, PropertyMock
from pynput import keyboard
from hotkey import GlobalHotkey
from state import AppState, AppStateManager


def make_hotkey(model_ready=True):
    rec = MagicMock()
    rec.is_recording = False
    txr = MagicMock()
    txr.is_ready = model_ready
    sm = AppStateManager()
    history = MagicMock()
    hk = GlobalHotkey(recorder=rec, transcriber=txr, state_manager=sm, history=history)
    return hk, rec, txr, sm, history


def test_hotkey_initializes():
    hk, rec, txr, sm, history = make_hotkey()
    assert hk.is_recording is False
    assert hk._processing is False
    assert hk.toggle_mode is False
    assert hk.last_tap_time is None


def test_hold_to_talk():
    """Hold >400ms: starts on press, stops on release → transcribe."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = "/tmp/fake.wav"
    txr.transcribe.return_value = "Hello"

    hk._on_press(keyboard.Key.alt_r)
    assert hk.is_recording
    rec.start.assert_called_once()
    assert sm.state == AppState.RECORDING

    # Simulate hold > HOLD_THRESHOLD
    hk.press_start_time = time.time() - 0.5
    hk._on_release(keyboard.Key.alt_r)
    assert not hk.is_recording
    assert not hk.toggle_mode


def test_double_tap_starts_toggle_mode():
    """Two quick taps within 500ms → enters toggle mode, keeps recording."""
    hk, rec, txr, sm, history = make_hotkey()

    # First tap
    hk._on_press(keyboard.Key.alt_r)
    assert hk.is_recording
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(keyboard.Key.alt_r)
    # After first tap, orphan timer is set, recording continues
    assert hk.is_recording
    assert hk.last_tap_time is not None
    assert hk._orphan_timer is not None

    # Second tap within window
    hk._on_press(keyboard.Key.alt_r)
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(keyboard.Key.alt_r)

    assert hk.toggle_mode is True
    assert hk.is_recording  # still recording
    assert hk.last_tap_time is None


def test_double_tap_stops_toggle_mode():
    """Double-tap while in toggle mode → stops recording & transcribes."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = "/tmp/fake.wav"
    txr.transcribe.return_value = "Hello"

    # Put into toggle mode manually
    hk.is_recording = True
    hk.toggle_mode = True
    sm.set_state(AppState.RECORDING)

    # First stop-tap
    hk.press_start_time = time.time() - 0.1
    hk._on_press(keyboard.Key.alt_r)
    hk.press_start_time = time.time() - 0.1
    hk._on_release(keyboard.Key.alt_r)
    # First tap registered
    assert hk.last_tap_time is not None
    assert hk.toggle_mode is True

    # Second stop-tap
    hk._on_press(keyboard.Key.alt_r)
    hk.press_start_time = time.time() - 0.1
    hk._on_release(keyboard.Key.alt_r)

    assert hk.toggle_mode is False
    assert not hk.is_recording


def test_orphan_single_tap_cancels_recording():
    """Single quick tap with no follow-up → recording cancelled."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.is_recording = True

    hk._on_press(keyboard.Key.alt_r)
    assert hk.is_recording
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(keyboard.Key.alt_r)

    # Simulate orphan timer firing
    hk._on_orphan_tap()

    assert not hk.is_recording
    assert sm.state == AppState.IDLE
    rec.stop.assert_called_once()  # discard audio


def test_hotkey_ignores_other_keys():
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_press(keyboard.Key.alt_l)
    assert not hk.is_recording
    hk._on_press(keyboard.Key.shift)
    assert not hk.is_recording
    rec.start.assert_not_called()
    assert sm.state == AppState.IDLE


def test_hotkey_does_not_activate_when_model_not_ready():
    hk, rec, txr, sm, history = make_hotkey(model_ready=False)
    hk._on_press(keyboard.Key.alt_r)
    assert not hk.is_recording
    rec.start.assert_not_called()


def test_hotkey_does_not_activate_when_processing():
    hk, rec, txr, sm, history = make_hotkey()
    hk._processing = True
    hk._on_press(keyboard.Key.alt_r)
    assert not hk.is_recording
    rec.start.assert_not_called()


def test_process_recording_sets_states():
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = "/tmp/fake.wav"
    txr.transcribe.return_value = "Hello"
    sm.set_state(AppState.RECORDING)
    hk._process_recording()
    assert sm.state == AppState.IDLE
    history.add.assert_called_once()


def test_process_recording_empty_returns_idle():
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = ""
    sm.set_state(AppState.RECORDING)
    hk._process_recording()
    assert sm.state == AppState.IDLE
    history.add.assert_not_called()


def test_max_duration_stops_recording():
    """Max duration timer fires → force stops recording."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = "/tmp/fake.wav"
    txr.transcribe.return_value = "Dictation text"

    # Simulate toggle recording in progress
    hk.is_recording = True
    hk.toggle_mode = True
    sm.set_state(AppState.RECORDING)

    hk._on_max_duration()

    assert not hk.is_recording
    assert not hk.toggle_mode
    assert hk.last_tap_time is None


def test_warning_fires():
    """Warning timer calls push_warning on state manager."""
    hk, rec, txr, sm, history = make_hotkey()
    warnings = []
    sm.on_warning(lambda msg: warnings.append(msg))

    hk._on_warning()

    assert warnings == ["Recording ends in 1 minute"]


def test_release_without_recording_is_noop():
    """Releasing key when not recording should do nothing."""
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_release(keyboard.Key.alt_r)
    assert sm.state == AppState.IDLE
    rec.stop.assert_not_called()


def test_stop_cleans_up_timers():
    """Calling stop() should cancel all timers."""
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_press(keyboard.Key.alt_r)
    hk.stop()
    assert hk._orphan_timer is None
    assert hk._warning_timer is None
    assert hk._max_timer is None
