# WhisperDash

Local offline dictation for macOS. Runs OpenAI's Whisper model directly on Apple Silicon via [mlx-whisper](https://github.com/ml-explore/mlx-examples) — no network required.

Built as a fast, privacy-first alternative to cloud-based dictation tools like [Wispr Flow](https://wisprflow.ai).

## Features

- **Fully offline** — everything runs locally on your Mac
- **Fast** — mlx-whisper large-v3-turbo optimized for Apple Silicon (M1/M2/M3/M4)
- **Push-to-talk** — hold to record, release to transcribe
- **Global hotkey** — hold Right Option from any app, transcription auto-copies to clipboard
- **Auto-copy** — transcribed text is copied to clipboard instantly
- **Native window** — lightweight PyWebView app, no Electron bloat
- **Model status** — progress indicators for download, loading, and ready states

## Requirements

- macOS with Apple Silicon (M1 or later)
- Python 3.11+
- ~1.5 GB disk space for the Whisper model (downloaded on first run)

## Setup

```bash
git clone https://github.com/ranabirbasu12/WhisperDash.git
cd WhisperDash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
source venv/bin/activate
python3 main.py
```

On first launch, the model (~1.5 GB) will download automatically. You'll see the progress in the status bar.

### In-app

Hold the mic button to record, release to transcribe. Text is auto-copied to your clipboard.

### Global hotkey

Hold **Right Option** from any app to record, release to stop. Transcription is copied to your clipboard — just Cmd+V to paste.

> **Note:** macOS will ask for Accessibility permission on first use. Grant it in **System Settings > Privacy & Security > Accessibility**.

## Architecture

```
PyWebView Window
├── Frontend (HTML/CSS/JS) — dark-themed UI with push-to-talk
│   └── WebSocket
└── FastAPI Backend
    ├── AudioRecorder (sounddevice) — 16kHz mono capture
    ├── WhisperTranscriber (mlx-whisper) — large-v3-turbo inference
    └── Clipboard (pyperclip) — auto-copy results

Global Hotkey (pynput) — Right Option hold-to-talk
```

## Project Structure

```
WhisperDash/
├── main.py          # Entry point — PyWebView + threaded uvicorn
├── app.py           # FastAPI backend with WebSocket
├── recorder.py      # Audio capture via sounddevice
├── transcriber.py   # mlx-whisper inference + model warmup
├── clipboard.py     # Clipboard utility
├── hotkey.py        # Global hotkey listener
├── static/
│   ├── index.html   # Dark-themed UI
│   ├── style.css    # Styles + animations
│   └── app.js       # WebSocket client + push-to-talk logic
├── tests/           # pytest suite
└── requirements.txt
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Transcription | mlx-whisper (large-v3-turbo) |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla HTML/CSS/JS |
| Window | PyWebView |
| Audio | sounddevice (16kHz mono) |
| Hotkey | pynput |
| Clipboard | pyperclip |

## License

MIT
