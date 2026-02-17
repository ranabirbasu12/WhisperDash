from state import AppState, AppStateManager


def test_initial_state_is_idle():
    sm = AppStateManager()
    assert sm.state == AppState.IDLE


def test_set_state_fires_callbacks():
    sm = AppStateManager()
    received = []
    sm.on_state_change(lambda old, new: received.append((old, new)))
    sm.set_state(AppState.RECORDING)
    assert received == [(AppState.IDLE, AppState.RECORDING)]


def test_multiple_callbacks_all_fire():
    sm = AppStateManager()
    a, b = [], []
    sm.on_state_change(lambda old, new: a.append(new))
    sm.on_state_change(lambda old, new: b.append(new))
    sm.set_state(AppState.PROCESSING)
    assert a == [AppState.PROCESSING]
    assert b == [AppState.PROCESSING]


def test_set_same_state_does_not_fire():
    sm = AppStateManager()
    received = []
    sm.on_state_change(lambda old, new: received.append(new))
    sm.set_state(AppState.IDLE)
    assert received == []


def test_push_amplitude():
    sm = AppStateManager()
    sm.push_amplitude(0.5)
    sm.push_amplitude(0.8)
    assert sm.get_amplitudes() == [0.5, 0.8]


def test_get_amplitudes_clears_buffer():
    sm = AppStateManager()
    sm.push_amplitude(0.3)
    sm.get_amplitudes()
    assert sm.get_amplitudes() == []


def test_amplitude_callback_fires():
    sm = AppStateManager()
    received = []
    sm.on_amplitude(lambda val: received.append(val))
    sm.push_amplitude(0.7)
    assert received == [0.7]
