# tests/test_hotkey.py
import time
from unittest.mock import MagicMock, patch, PropertyMock
from hotkey import GlobalHotkey
from state import AppState, AppStateManager

# macOS virtual keycodes used in tests
KC_ALT_R = 61     # Right Option
KC_ALT_L = 58     # Left Option
KC_SHIFT = 56     # Left Shift
KC_SHIFT_R = 60   # Right Shift
KC_F5 = 96        # F5


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
    assert KC_ALT_R in hk.trigger_keys  # default fallback


def test_hold_to_talk():
    """Hold >400ms: starts on press, stops on release → transcribe."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.stop.return_value = "/tmp/fake.wav"
    txr.transcribe.return_value = "Hello"

    hk._on_press(KC_ALT_R)
    assert hk.is_recording
    rec.start.assert_called_once()
    assert sm.state == AppState.RECORDING

    # Simulate hold > HOLD_THRESHOLD
    hk.press_start_time = time.time() - 0.5
    hk._on_release(KC_ALT_R)
    assert not hk.is_recording
    assert not hk.toggle_mode


def test_double_tap_starts_toggle_mode():
    """Two quick taps within 500ms → enters toggle mode, keeps recording."""
    hk, rec, txr, sm, history = make_hotkey()

    # First tap
    hk._on_press(KC_ALT_R)
    assert hk.is_recording
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(KC_ALT_R)
    # After first tap, orphan timer is set, recording continues
    assert hk.is_recording
    assert hk.last_tap_time is not None
    assert hk._orphan_timer is not None

    # Second tap within window
    hk._on_press(KC_ALT_R)
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(KC_ALT_R)

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
    hk._on_press(KC_ALT_R)
    hk.press_start_time = time.time() - 0.1
    hk._on_release(KC_ALT_R)
    # First tap registered
    assert hk.last_tap_time is not None
    assert hk.toggle_mode is True

    # Second stop-tap
    hk._on_press(KC_ALT_R)
    hk.press_start_time = time.time() - 0.1
    hk._on_release(KC_ALT_R)

    assert hk.toggle_mode is False
    assert not hk.is_recording


def test_orphan_single_tap_cancels_recording():
    """Single quick tap with no follow-up → recording cancelled."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.is_recording = True

    hk._on_press(KC_ALT_R)
    assert hk.is_recording
    hk.press_start_time = time.time() - 0.1  # short hold
    hk._on_release(KC_ALT_R)

    # Simulate orphan timer firing
    hk._on_orphan_tap()

    assert not hk.is_recording
    assert sm.state == AppState.IDLE
    rec.stop.assert_called_once()  # discard audio


def test_hotkey_ignores_other_keys():
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_press(KC_ALT_L)
    assert not hk.is_recording
    hk._on_press(KC_SHIFT)
    assert not hk.is_recording
    rec.start.assert_not_called()
    assert sm.state == AppState.IDLE


def test_hotkey_does_not_activate_when_model_not_ready():
    hk, rec, txr, sm, history = make_hotkey(model_ready=False)
    hk._on_press(KC_ALT_R)
    assert not hk.is_recording
    rec.start.assert_not_called()


def test_hotkey_does_not_activate_when_processing():
    hk, rec, txr, sm, history = make_hotkey()
    hk._processing = True
    hk._on_press(KC_ALT_R)
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
    hk._on_release(KC_ALT_R)
    assert sm.state == AppState.IDLE
    rec.stop.assert_not_called()


def test_stop_cleans_up_timers():
    """Calling stop() should cancel all timers."""
    hk, rec, txr, sm, history = make_hotkey()
    hk._on_press(KC_ALT_R)
    hk.stop()
    assert hk._orphan_timer is None
    assert hk._warning_timer is None
    assert hk._max_timer is None


def test_hotkey_change_swaps_trigger_key():
    """Changing hotkey via _on_hotkey_changed swaps the trigger key."""
    hk, rec, txr, sm, history = make_hotkey()
    assert KC_ALT_R in hk.trigger_keys

    hk._on_hotkey_changed("f5")
    assert KC_F5 in hk.trigger_keys
    assert KC_ALT_R not in hk.trigger_keys

    # Old key should be ignored, new key should work
    hk._on_press(KC_ALT_R)
    assert not hk.is_recording

    hk._on_press(KC_F5)
    assert hk.is_recording


def test_hotkey_change_cancels_active_recording():
    """Changing hotkey while recording cancels the recording."""
    hk, rec, txr, sm, history = make_hotkey()
    rec.is_recording = True

    # Start recording
    hk._on_press(KC_ALT_R)
    assert hk.is_recording
    assert sm.state == AppState.RECORDING

    # Change hotkey mid-recording
    hk._on_hotkey_changed("shift_r")

    assert not hk.is_recording
    assert not hk.toggle_mode
    assert hk.last_tap_time is None
    assert sm.state == AppState.IDLE
    assert KC_SHIFT_R in hk.trigger_keys


def test_hotkey_change_with_settings_manager():
    """SettingsManager wiring triggers _on_hotkey_changed."""
    from config import SettingsManager
    import tempfile, os, json

    # Use a temp config file
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        import config as config_module
        orig_path = config_module.CONFIG_PATH
        orig_dir = config_module.CONFIG_DIR
        config_module.CONFIG_PATH = config_path
        config_module.CONFIG_DIR = tmpdir

        try:
            settings = SettingsManager()
            rec = MagicMock()
            rec.is_recording = False
            txr = MagicMock()
            txr.is_ready = True
            sm = AppStateManager()
            hk = GlobalHotkey(
                recorder=rec, transcriber=txr,
                state_manager=sm, history=MagicMock(),
                settings=settings,
            )
            assert KC_ALT_R in hk.trigger_keys

            settings.set_hotkey("f5")
            assert KC_F5 in hk.trigger_keys
        finally:
            config_module.CONFIG_PATH = orig_path
            config_module.CONFIG_DIR = orig_dir


def test_capture_mode_intercepts_key():
    """Capture mode grabs the next key press instead of triggering recording."""
    hk, rec, txr, sm, history = make_hotkey()

    hk.start_key_capture()
    assert hk.poll_key_capture() == {"captured": False}

    # Press F5 — should be captured, NOT start recording
    hk._on_press(KC_F5)
    assert not hk.is_recording
    rec.start.assert_not_called()

    result = hk.poll_key_capture()
    assert result["captured"] is True
    assert result["key"] == "f5"


def test_capture_mode_exits_after_capture():
    """Capture mode automatically exits after capturing a key."""
    hk, rec, txr, sm, history = make_hotkey()
    hk.start_key_capture()
    hk._on_press(KC_F5)

    # Next press should work normally (not captured again)
    hk._on_press(KC_ALT_R)
    assert hk.is_recording


def test_capture_mode_cancel():
    """Cancelling capture mode allows normal hotkey operation."""
    hk, rec, txr, sm, history = make_hotkey()
    hk.start_key_capture()
    hk.cancel_key_capture()

    assert hk.poll_key_capture() == {"captured": False}
    # Normal hotkey should work
    hk._on_press(KC_ALT_R)
    assert hk.is_recording


def test_capture_ignores_unknown_keycodes():
    """Keycodes not in KEYCODE_TO_NAME are ignored in capture mode."""
    hk, rec, txr, sm, history = make_hotkey()
    hk.start_key_capture()

    # Unknown keycode (not in mapping)
    hk._on_press(999)
    assert hk.poll_key_capture() == {"captured": False}
    # Still in capture mode — valid key works
    hk._on_press(KC_F5)
    result = hk.poll_key_capture()
    assert result["captured"] is True
