# app.py
import asyncio
import gc
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from recorder import AudioRecorder, get_wav_duration
from transcriber import WhisperTranscriber
from clipboard import copy_to_clipboard, paste_clipboard
from state import AppState, AppStateManager
from history import TranscriptionHistory


def _get_static_dir():
    """Resolve static/ path for both development and py2app bundle."""
    if getattr(sys, 'frozen', None) == 'macosx_app':
        resource_path = os.environ.get('RESOURCEPATH', '.')
        return os.path.join(resource_path, 'static')
    return os.path.join(os.path.dirname(__file__), 'static')


STATIC_DIR = _get_static_dir()
SUPPORTED_AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".wma", ".aac"}


def create_app(
    recorder: AudioRecorder | None = None,
    transcriber: WhisperTranscriber | None = None,
    state_manager: AppStateManager | None = None,
    history: TranscriptionHistory | None = None,
    settings=None,
    pipeline=None,
) -> FastAPI:
    rec = recorder or AudioRecorder()
    txr = transcriber or WhisperTranscriber()
    sm = state_manager or AppStateManager()
    hist = history or TranscriptionHistory()
    pipe = pipeline

    # Wire recorder amplitude to state manager
    rec.on_amplitude = sm.push_amplitude

    @asynccontextmanager
    async def lifespan(app):
        def _init_models():
            if pipe is not None:
                pipe.load_vad()
            if hasattr(txr, 'warmup'):
                txr.warmup()
        threading.Thread(target=_init_models, daemon=True).start()
        yield

    app = FastAPI(lifespan=lifespan)

    # Store references for external access
    app.state.state_manager = sm
    app.state.history = hist

    @app.get("/")
    async def index():
        index_path = os.path.join(STATIC_DIR, "index.html")
        with open(index_path) as f:
            return HTMLResponse(f.read())

    @app.get("/bar")
    async def bar_page():
        bar_path = os.path.join(STATIC_DIR, "bar.html")
        with open(bar_path) as f:
            return HTMLResponse(f.read())

    @app.get("/api/history")
    async def get_history(limit: int = 50, offset: int = 0):
        entries = hist.get_recent(limit=limit, offset=offset)
        return JSONResponse({"entries": entries, "total": hist.count()})

    @app.get("/api/history/search")
    async def search_history(q: str = "", limit: int = 50):
        entries = hist.search(q, limit=limit)
        return JSONResponse({"entries": entries})

    @app.get("/api/browse-file")
    async def browse_file():
        main_window = getattr(app.state, "main_window", None)
        if not main_window:
            return JSONResponse({"path": None})
        try:
            import webview
            result = main_window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Audio Files (*.wav;*.mp3;*.m4a;*.flac;*.ogg;*.webm;*.wma;*.aac)",),
            )
            path = result[0] if result else None
            return JSONResponse({"path": path})
        except Exception:
            return JSONResponse({"path": None})

    @app.get("/api/settings/hotkey")
    async def get_hotkey():
        if not settings:
            return JSONResponse({"key": "alt_r", "display": "Right Option"})
        return JSONResponse({
            "key": settings.hotkey_string,
            "display": settings.hotkey_display,
        })

    @app.post("/api/settings/hotkey")
    async def set_hotkey(request: Request):
        body = await request.json()
        key_str = body.get("key", "")
        if not key_str:
            return JSONResponse({"ok": False, "error": "Missing key"}, status_code=400)
        if not settings:
            return JSONResponse({"ok": False, "error": "Settings not available"}, status_code=500)
        success = settings.set_hotkey(key_str)
        if not success:
            return JSONResponse({"ok": False, "error": "Invalid key"}, status_code=400)
        return JSONResponse({
            "ok": True,
            "key": settings.hotkey_string,
            "display": settings.hotkey_display,
        })

    @app.post("/api/settings/hotkey/capture")
    async def start_capture():
        hotkey = getattr(app.state, "hotkey", None)
        if not hotkey:
            return JSONResponse({"ok": False, "error": "Hotkey not available"}, status_code=500)
        hotkey.start_key_capture()
        return JSONResponse({"ok": True})

    @app.get("/api/settings/hotkey/capture")
    async def poll_capture():
        hotkey = getattr(app.state, "hotkey", None)
        if not hotkey:
            return JSONResponse({"captured": False})
        return JSONResponse(hotkey.poll_key_capture())

    @app.delete("/api/settings/hotkey/capture")
    async def cancel_capture():
        hotkey = getattr(app.state, "hotkey", None)
        if hotkey:
            hotkey.cancel_key_capture()
        return JSONResponse({"ok": True})

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
                    sm.set_state(AppState.RECORDING)
                    if pipe is not None and pipe.vad_available:
                        sys_chunks = rec.get_sys_audio_chunks()
                        pipe.start(sys_audio_chunks=sys_chunks)
                        rec.on_vad_chunk = pipe.feed
                    await ws.send_json({"type": "status", "status": "recording"})

                elif action == "stop":
                    try:
                        text, elapsed, audio_duration = await asyncio.to_thread(
                            _ws_stop_and_transcribe, rec, txr, pipe
                        )
                        if text is None:
                            sm.set_state(AppState.IDLE)
                            await ws.send_json({
                                "type": "error",
                                "message": "Recording too short. Hold the button longer.",
                            })
                            continue
                        sm.set_state(AppState.PROCESSING)
                        await ws.send_json({"type": "status", "status": "transcribing"})
                        copy_to_clipboard(text)
                        paste_clipboard()
                        hist.add(text, duration=audio_duration, latency=elapsed)
                        gc.collect()
                        sm.set_state(AppState.IDLE)
                        await ws.send_json({
                            "type": "result",
                            "text": text,
                            "latency": elapsed,
                        })
                    except Exception as e:
                        sm.set_state(AppState.ERROR)
                        await ws.send_json({
                            "type": "error",
                            "message": str(e),
                        })

                elif action == "transcribe_file":
                    file_path = data.get("path", "")
                    p = Path(file_path)
                    if not p.is_file():
                        await ws.send_json({
                            "type": "error",
                            "message": f"File not found: {file_path}",
                        })
                        continue
                    if p.suffix.lower() not in SUPPORTED_AUDIO_EXT:
                        await ws.send_json({
                            "type": "error",
                            "message": f"Unsupported format: {p.suffix}",
                        })
                        continue
                    await ws.send_json({
                        "type": "file_status",
                        "status": "transcribing",
                        "message": f"Transcribing {p.name}...",
                    })
                    try:
                        start_time = time.time()
                        text = await asyncio.to_thread(txr.transcribe, str(p))
                        elapsed = round(time.time() - start_time, 2)
                        out_name = f"{p.stem}_{date.today().isoformat()}_transcription.txt"
                        out_path = p.parent / out_name
                        out_path.write_text(text, encoding="utf-8")
                        hist.add(text, latency=elapsed)
                        await ws.send_json({
                            "type": "file_result",
                            "text": text,
                            "output_path": str(out_path),
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

    @app.websocket("/ws/bar")
    async def bar_websocket(ws: WebSocket):
        await ws.accept()
        # Send initial state
        await ws.send_json({"type": "state", "state": sm.state.value})

        # Queue for state changes and amplitude data pushed from background threads
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_state_change(old, new):
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "state", "state": new.value})

        def on_amplitude(val):
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "amplitude", "value": round(val, 4)})

        def on_warning(msg):
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "warning", "message": msg})

        def on_hotkey_change(serialized):
            from config import display_name
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "hotkey", "display": display_name(serialized)}
            )

        sm.on_state_change(on_state_change)
        sm.on_amplitude(on_amplitude)
        sm.on_warning(on_warning)
        if settings:
            settings.on_hotkey_change(on_hotkey_change)

        # Send initial hotkey display name
        if settings:
            await ws.send_json({"type": "hotkey", "display": settings.hotkey_display})

        try:
            # Run two tasks: listen for incoming messages and push outgoing updates
            async def push_updates():
                while True:
                    msg = await queue.get()
                    await ws.send_json(msg)

            async def receive_commands():
                while True:
                    data = await ws.receive_json()
                    action = data.get("action")
                    if action == "start":
                        rec.start()
                        sm.set_state(AppState.RECORDING)
                        if pipe is not None and pipe.vad_available:
                            sys_chunks = rec.get_sys_audio_chunks()
                            pipe.start(sys_audio_chunks=sys_chunks)
                            rec.on_vad_chunk = pipe.feed
                    elif action == "stop":
                        threading.Thread(
                            target=_bar_stop_and_transcribe,
                            args=(rec, txr, sm, hist, pipe),
                            daemon=True,
                        ).start()
                    elif action == "cancel":
                        if rec.is_recording:
                            rec.stop()  # discard audio
                        sm.set_state(AppState.IDLE)

            await asyncio.gather(push_updates(), receive_commands())
        except WebSocketDisconnect:
            pass
        finally:
            # Remove callbacks
            if on_state_change in sm._state_callbacks:
                sm._state_callbacks.remove(on_state_change)
            if on_amplitude in sm._amplitude_callbacks:
                sm._amplitude_callbacks.remove(on_amplitude)
            if on_warning in sm._warning_callbacks:
                sm._warning_callbacks.remove(on_warning)
            if settings and on_hotkey_change in settings._hotkey_callbacks:
                settings._hotkey_callbacks.remove(on_hotkey_change)

    return app


def _stop_and_transcribe(rec, txr, pipe):
    """Shared stop+transcribe logic for websocket and bar handlers.

    Returns (text, elapsed, audio_duration) or (None, 0, 0) if no audio.
    """
    use_streaming = pipe is not None and pipe.vad_available and pipe._active

    if use_streaming:
        rec.on_vad_chunk = None
        mic_audio, sys_audio = rec.stop_raw()

        if mic_audio is None or len(mic_audio) == 0:
            pipe.stop(None)
            return None, 0, 0

        audio_duration = round(len(mic_audio) / rec.sample_rate, 2)

        if audio_duration < pipe.SHORT_RECORDING_THRESHOLD_S:
            pipe.stop(None)
            if sys_audio is not None and len(sys_audio) > 0:
                try:
                    from aec import nlms_echo_cancel, noise_gate
                    mic_audio = nlms_echo_cancel(mic_audio, sys_audio)
                    mic_audio = noise_gate(mic_audio, sample_rate=rec.sample_rate)
                except Exception:
                    pass
            del sys_audio
            start_time = time.time()
            text = txr.transcribe_array(mic_audio)
            elapsed = round(time.time() - start_time, 2)
            del mic_audio
        else:
            del mic_audio
            start_time = time.time()
            results = pipe.stop(sys_audio)
            elapsed = round(time.time() - start_time, 2)
            del sys_audio
            text = " ".join(r.text for r in results if r.text)

        return text or None, elapsed, audio_duration
    else:
        wav_path = rec.stop()
        if not wav_path:
            return None, 0, 0
        audio_duration = round(get_wav_duration(wav_path), 2)
        start_time = time.time()
        text = txr.transcribe(wav_path)
        elapsed = round(time.time() - start_time, 2)
        try:
            os.unlink(wav_path)
        except OSError:
            pass
        return text or None, elapsed, audio_duration


def _ws_stop_and_transcribe(rec, txr, pipe):
    """Called from asyncio.to_thread for websocket stop."""
    text, elapsed, audio_duration = _stop_and_transcribe(rec, txr, pipe)
    gc.collect()
    return text, elapsed, audio_duration


def _bar_stop_and_transcribe(rec, txr, sm, hist, pipe=None):
    """Background thread: stop recording, transcribe, update state."""
    sm.set_state(AppState.PROCESSING)
    try:
        text, elapsed, audio_duration = _stop_and_transcribe(rec, txr, pipe)
        if not text:
            sm.set_state(AppState.IDLE)
            return
        copy_to_clipboard(text)
        paste_clipboard()
        hist.add(text, duration=audio_duration, latency=elapsed)
        gc.collect()
        sm.set_state(AppState.IDLE)
    except Exception as e:
        print(f"Bar transcription error: {e}")
        sm.set_state(AppState.ERROR)
