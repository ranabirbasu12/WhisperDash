# tests/test_hotkey.py
from unittest.mock import MagicMock, patch
from pynput import keyboard
from hotkey import GlobalHotkey


def test_hotkey_initializes():
    rec = MagicMock()
    txr = MagicMock()
    hk = GlobalHotkey(recorder=rec, transcriber=txr)
    assert hk.is_recording is False
    assert hk._processing is False


def test_hotkey_activates_on_right_option():
    rec = MagicMock()
    txr = MagicMock()
    txr.is_ready = True
    hk = GlobalHotkey(recorder=rec, transcriber=txr)

    hk._on_press(keyboard.Key.alt_r)
    assert hk.is_recording
    rec.start.assert_called_once()


def test_hotkey_ignores_other_keys():
    rec = MagicMock()
    txr = MagicMock()
    txr.is_ready = True
    hk = GlobalHotkey(recorder=rec, transcriber=txr)

    hk._on_press(keyboard.Key.alt_l)
    assert not hk.is_recording
    hk._on_press(keyboard.Key.shift)
    assert not hk.is_recording
    rec.start.assert_not_called()


def test_hotkey_does_not_activate_when_model_not_ready():
    rec = MagicMock()
    txr = MagicMock()
    txr.is_ready = False
    hk = GlobalHotkey(recorder=rec, transcriber=txr)

    hk._on_press(keyboard.Key.alt_r)
    assert not hk.is_recording
    rec.start.assert_not_called()
