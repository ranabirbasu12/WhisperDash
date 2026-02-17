# main.py
import threading
import uvicorn
import webview

from app import create_app
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from hotkey import GlobalHotkey

HOST = "127.0.0.1"
PORT = 8765


def start_server(app):
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main():
    transcriber = WhisperTranscriber()
    app = create_app(transcriber=transcriber)

    # Global hotkey uses its own recorder to avoid conflicts with the UI
    hotkey_recorder = AudioRecorder()
    hotkey = GlobalHotkey(recorder=hotkey_recorder, transcriber=transcriber)
    hotkey.start()

    server_thread = threading.Thread(
        target=start_server,
        args=(app,),
        daemon=True,
    )
    server_thread.start()

    webview.create_window(
        "WhisperDash",
        f"http://{HOST}:{PORT}",
        width=450,
        height=550,
        resizable=True,
        min_size=(350, 450),
    )
    webview.start()


if __name__ == "__main__":
    main()
