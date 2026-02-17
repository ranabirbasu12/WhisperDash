# app.py
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def create_app(
    recorder: AudioRecorder | None = None,
    transcriber: WhisperTranscriber | None = None,
) -> FastAPI:
    rec = recorder or AudioRecorder()
    txr = transcriber or WhisperTranscriber()

    @asynccontextmanager
    async def lifespan(app):
        if hasattr(txr, 'warmup'):
            threading.Thread(target=txr.warmup, daemon=True).start()
        yield

    app = FastAPI(lifespan=lifespan)

    @app.get("/")
    async def index():
        index_path = os.path.join(STATIC_DIR, "index.html")
        with open(index_path) as f:
            return HTMLResponse(f.read())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_json()
                action = data.get("action")

                if action == "start":
                    rec.start()
                    await ws.send_json({"type": "status", "status": "recording"})

                elif action == "stop":
                    try:
                        wav_path = rec.stop()
                        if not wav_path:
                            await ws.send_json({
                                "type": "error",
                                "message": "Recording too short. Hold the button longer.",
                            })
                            continue
                        await ws.send_json({"type": "status", "status": "transcribing"})
                        start_time = time.time()
                        text = txr.transcribe(wav_path)
                        elapsed = round(time.time() - start_time, 2)
                        copy_to_clipboard(text)
                        try:
                            os.unlink(wav_path)
                        except OSError:
                            pass
                        await ws.send_json({
                            "type": "result",
                            "text": text,
                            "latency": elapsed,
                        })
                    except Exception as e:
                        await ws.send_json({
                            "type": "error",
                            "message": str(e),
                        })

                elif action == "status":
                    status_data = {
                        "type": "model_status",
                        "ready": txr.is_ready,
                    }
                    if hasattr(txr, 'status'):
                        status_data["status"] = txr.status
                        status_data["message"] = txr.status_message
                    await ws.send_json(status_data)

        except WebSocketDisconnect:
            pass

    return app
