# tests/test_app.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app import create_app


def test_static_index_served():
    app = create_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "WhisperDash" in resp.text


def test_websocket_start_stop_flow():
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
