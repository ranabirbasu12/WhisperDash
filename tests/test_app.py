# tests/test_app.py
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app import create_app
from history import TranscriptionHistory
from state import AppState, AppStateManager
from config import SettingsManager
import config as config_module


def test_static_index_served():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "WhisperDash" in resp.text


@patch("app.get_wav_duration", return_value=3.5)
def test_websocket_start_stop_flow(_mock_dur):
    mock_recorder = MagicMock()
    mock_recorder.stop.return_value = "/tmp/fake.wav"
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "Hello world."
    mock_transcriber.is_ready = True

    app = create_app(recorder=mock_recorder, transcriber=mock_transcriber)
    client = TestClient(app)

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"action": "start"})
        resp = ws.receive_json()
        assert resp["type"] == "status"
        assert resp["status"] == "recording"
        mock_recorder.start.assert_called_once()

        ws.send_json({"action": "stop"})
        # Should get transcribing status, then result
        messages = []
        for _ in range(2):
            messages.append(ws.receive_json())
        types = [m["type"] for m in messages]
        assert "status" in types
        assert "result" in types
        result_msg = next(m for m in messages if m["type"] == "result")
        assert result_msg["text"] == "Hello world."


def test_bar_page_served():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/bar")
    assert resp.status_code == 200
    assert "bar" in resp.text.lower()


def test_bar_websocket_receives_state():
    sm = AppStateManager()
    mock_recorder = MagicMock()
    mock_transcriber = MagicMock()
    mock_transcriber.is_ready = True
    app = create_app(recorder=mock_recorder, transcriber=mock_transcriber, state_manager=sm)
    client = TestClient(app)
    with client.websocket_connect("/ws/bar") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["state"] == "idle"


def test_bar_websocket_start_stop():
    sm = AppStateManager()
    mock_recorder = MagicMock()
    mock_recorder.stop.return_value = "/tmp/fake.wav"
    mock_transcriber = MagicMock()
    mock_transcriber.transcribe.return_value = "Hello"
    mock_transcriber.is_ready = True
    app = create_app(recorder=mock_recorder, transcriber=mock_transcriber, state_manager=sm)
    client = TestClient(app)
    with client.websocket_connect("/ws/bar") as ws:
        msg = ws.receive_json()  # initial state
        ws.send_json({"action": "start"})
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["state"] == "recording"


def test_history_api_returns_entries():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()
    history = TranscriptionHistory(db_path)
    history.add("Test entry", duration=1.0, latency=0.5)

    app = create_app(history=history)
    client = TestClient(app)
    resp = client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["text"] == "Test entry"
    os.unlink(db_path)


def test_history_search_api():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = tmp.name
    tmp.close()
    history = TranscriptionHistory(db_path)
    history.add("The quick brown fox", duration=1.0, latency=0.5)
    history.add("Hello world", duration=1.0, latency=0.5)

    app = create_app(history=history)
    client = TestClient(app)
    resp = client.get("/api/history/search?q=fox")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) == 1
    os.unlink(db_path)


def test_get_hotkey_endpoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path, orig_dir = config_module.CONFIG_PATH, config_module.CONFIG_DIR
        config_module.CONFIG_PATH = os.path.join(tmpdir, "config.json")
        config_module.CONFIG_DIR = tmpdir
        try:
            settings = SettingsManager()
            app = create_app(settings=settings)
            client = TestClient(app)
            resp = client.get("/api/settings/hotkey")
            assert resp.status_code == 200
            data = resp.json()
            assert data["key"] == "alt_r"
            assert data["display"] == "Right Option"
        finally:
            config_module.CONFIG_PATH = orig_path
            config_module.CONFIG_DIR = orig_dir


def test_set_hotkey_endpoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path, orig_dir = config_module.CONFIG_PATH, config_module.CONFIG_DIR
        config_module.CONFIG_PATH = os.path.join(tmpdir, "config.json")
        config_module.CONFIG_DIR = tmpdir
        try:
            settings = SettingsManager()
            app = create_app(settings=settings)
            client = TestClient(app)
            resp = client.post("/api/settings/hotkey", json={"key": "f5"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["key"] == "f5"
            assert data["display"] == "F5"
            assert settings.hotkey_string == "f5"
        finally:
            config_module.CONFIG_PATH = orig_path
            config_module.CONFIG_DIR = orig_dir


def test_set_hotkey_invalid_key():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_path, orig_dir = config_module.CONFIG_PATH, config_module.CONFIG_DIR
        config_module.CONFIG_PATH = os.path.join(tmpdir, "config.json")
        config_module.CONFIG_DIR = tmpdir
        try:
            settings = SettingsManager()
            app = create_app(settings=settings)
            client = TestClient(app)
            resp = client.post("/api/settings/hotkey", json={"key": "not_a_key"})
            assert resp.status_code == 400
            assert settings.hotkey_string == "alt_r"
        finally:
            config_module.CONFIG_PATH = orig_path
            config_module.CONFIG_DIR = orig_dir
