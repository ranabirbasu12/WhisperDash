# main.py
import threading
import uvicorn
import webview

from app import create_app
from transcriber import WhisperTranscriber

HOST = "127.0.0.1"
PORT = 8765


def start_server(app):
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main():
    transcriber = WhisperTranscriber()
    app = create_app(transcriber=transcriber)

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
