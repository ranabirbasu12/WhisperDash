"""
py2app build script for WhisperDash.

Usage:
    python setup.py py2app          # Full standalone build
    python setup.py py2app -A       # Alias mode (development, links to source)

Output: dist/WhisperDash.app
"""
from setuptools import setup

APP = ['main.py']

DATA_FILES = [
    ('static', [
        'static/index.html',
        'static/style.css',
        'static/app.js',
        'static/bar.html',
        'static/bar.css',
        'static/bar.js',
    ]),
]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'WhisperDash.icns',
    'includes': [
        # Project modules (some are dynamically imported)
        'app', 'recorder', 'transcriber', 'clipboard', 'hotkey',
        'state', 'history', 'config', 'system_audio', 'aec',
        'vad', 'pipeline', 'permissions',
        # PyObjC frameworks
        'objc', 'Quartz', 'AppKit', 'Foundation', 'WebKit',
        'CoreMedia', 'ScreenCaptureKit', 'PyObjCTools', 'AVFoundation',
        # sounddevice
        'sounddevice', '_sounddevice_data', '_cffi_backend',
        # FastAPI/uvicorn stack
        'fastapi', 'uvicorn', 'uvicorn.logging', 'uvicorn.loops',
        'uvicorn.loops.auto', 'uvicorn.protocols',
        'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'starlette', 'websockets',
        'anyio', 'anyio._backends._asyncio',
        # ML stack
        'mlx', 'mlx_whisper', 'onnxruntime',
        'numpy', 'scipy', 'scipy.io', 'scipy.io.wavfile',
        # Other dependencies
        'pyperclip', 'pydantic', 'pydantic_core',
        'typing_extensions', 'annotated_types',
        'huggingface_hub', 'tiktoken', 'regex',
    ],
    'packages': [
        'mlx_whisper', 'numpy', 'scipy',
        'huggingface_hub', 'tiktoken', 'pydantic', 'pydantic_core',
        'webview', 'uvicorn', 'fastapi', 'starlette', 'anyio',
        'certifi',
        # sounddevice + native PortAudio dylib (must not be zipped)
        'sounddevice', '_sounddevice_data',
        # ONNX Runtime for VAD (has native libraries, must not be zipped)
        'onnxruntime',
        # PyObjC (mlx and PyObjCTools are namespace packages — handled separately)
        'objc', 'Quartz', 'AppKit', 'Foundation', 'WebKit',
        'CoreMedia', 'CoreFoundation', 'ScreenCaptureKit', 'AVFoundation',
    ],
    'excludes': [
        'torch', 'torchgen', 'functorch', 'sympy',
        'numba', 'llvmlite', 'matplotlib', 'PIL',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'pytest_asyncio', 'httpx', 'pynput',
    ],
    'plist': {
        'CFBundleName': 'WhisperDash',
        'CFBundleDisplayName': 'WhisperDash',
        'CFBundleIdentifier': 'com.whisperdash.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSMinimumSystemVersion': '15.0',
        'LSArchitecturePriority': ['arm64'],
        'NSHighResolutionCapable': True,
        'NSMicrophoneUsageDescription':
            'WhisperDash needs microphone access to record and transcribe your speech.',
        'NSScreenCaptureUsageDescription':
            'WhisperDash uses system audio capture for echo cancellation '
            'to improve transcription accuracy when audio is playing.',
        'NSAppTransportSecurity': {
            'NSAllowsLocalNetworking': True,
        },
    },
    'emulate_shell_environment': True,
    'semi_standalone': False,
    'site_packages': True,
    'strip': False,
    'arch': 'arm64',
}

setup(
    name='WhisperDash',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
