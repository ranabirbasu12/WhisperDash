# tests/test_hotkey.py
from unittest.mock import MagicMock, patch
from pynput import keyboard
from hotkey import GlobalHotkey
from state import AppState, AppStateManager


def make_hotkey(model_ready=True):
    rec = MagicMock()
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


def test_hotkey_activates_on_right_option():
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_press(keyboard.Key.alt_r)
    assert hk.is_recording
    rec.start.assert_called_once()
    assert sm.state == AppState.RECORDING


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
