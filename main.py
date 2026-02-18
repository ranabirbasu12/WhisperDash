# main.py
import threading

import objc
import AppKit
import uvicorn
import webview

from app import create_app
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from hotkey import GlobalHotkey
from state import AppState, AppStateManager
from history import TranscriptionHistory
from config import SettingsManager

HOST = "127.0.0.1"
PORT = 8765
_app_quitting = False

# Bar dimensions per state
BAR_IDLE_W, BAR_IDLE_H = 120, 24
BAR_ACTIVE_W, BAR_ACTIVE_H = 280, 40


def start_server(app):
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def get_bar_position(width, height):
    """Center horizontally, 70px above screen bottom."""
    try:
        import AppKit
        screen = AppKit.NSScreen.mainScreen()
        frame = screen.frame()
        screen_w = int(frame.size.width)
        screen_h = int(frame.size.height)
    except ImportError:
        screen_w, screen_h = 1440, 900
    x = (screen_w - width) // 2
    y = screen_h - 70 - height
    return x, y



def _setup_dock_menu(main_window):
    """Add 'Open Dashboard' and 'Quit' to the macOS dock right-click menu."""
    import webview.platforms.cocoa as cocoa_backend

    AppDelegate = cocoa_backend.BrowserView.AppDelegate

    def applicationDockMenu_(self, sender):
        menu = AppKit.NSMenu.alloc().init()
        dash_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Dashboard", "openDashboard:", "",
        )
        dash_item.setTarget_(self)
        menu.addItem_(dash_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit WhisperDash", "quitApp:", "",
        )
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)
        return menu

    def openDashboard_(self, sender):
        main_window.show()

    def quitApp_(self, sender):
        global _app_quitting
        _app_quitting = True
        AppKit.NSApplication.sharedApplication().terminate_(None)

    objc.classAddMethod(AppDelegate, b"applicationDockMenu:", applicationDockMenu_)
    objc.classAddMethod(AppDelegate, b"openDashboard:", openDashboard_)
    objc.classAddMethod(AppDelegate, b"quitApp:", quitApp_)

    # Replace pywebview's applicationShouldTerminate: so standard Quit works too.
    # The original checks window.events.closing on every window, but our main window
    # closing handler returns False (to hide instead of close), which blocks quit.
    def applicationShouldTerminate_(self, app):
        global _app_quitting
        _app_quitting = True
        return AppKit.NSTerminateNow

    AppDelegate.applicationShouldTerminate_ = applicationShouldTerminate_


def main():
    transcriber = WhisperTranscriber()
    state_manager = AppStateManager()
    history = TranscriptionHistory()
    settings = SettingsManager()

    app = create_app(
        transcriber=transcriber,
        state_manager=state_manager,
        history=history,
        settings=settings,
    )

    # Global hotkey uses its own recorder to avoid conflicts with the UI
    hotkey_recorder = AudioRecorder()
    hotkey_recorder.on_amplitude = state_manager.push_amplitude
    hotkey = GlobalHotkey(
        recorder=hotkey_recorder,
        transcriber=transcriber,
        state_manager=state_manager,
        history=history,
        settings=settings,
    )
    app.state.hotkey = hotkey
    hotkey.start()

    if not hotkey.has_active_tap:
        print(
            "Accessibility permission not granted for this build.\n"
            "Grant it in: System Settings > Privacy & Security > Accessibility\n"
            "If WhisperDash is already listed, toggle it OFF then ON."
        )

    server_thread = threading.Thread(
        target=start_server,
        args=(app,),
        daemon=True,
    )
    server_thread.start()

    # Calculate bar position
    bar_x, bar_y = get_bar_position(BAR_IDLE_W, BAR_IDLE_H)

    # Create floating bar window (always exists, keeps app alive)
    bar_window = webview.create_window(
        "",
        f"http://{HOST}:{PORT}/bar",
        width=BAR_IDLE_W,
        height=BAR_IDLE_H,
        x=bar_x,
        y=bar_y,
        min_size=(80, 20),
        frameless=True,
        transparent=True,
        on_top=True,
        easy_drag=False,
    )

    # Create main window
    main_window = webview.create_window(
        "WhisperDash",
        f"http://{HOST}:{PORT}",
        width=450,
        height=650,
        resizable=True,
        min_size=(350, 450),
    )

    # Store reference so /api/browse-file can open a file dialog
    app.state.main_window = main_window

    # Handle bar resize based on state changes
    def on_state_change(old_state, new_state):
        if new_state == AppState.RECORDING or new_state == AppState.PROCESSING:
            cx, cy = get_bar_position(BAR_ACTIVE_W, BAR_ACTIVE_H)
            bar_window.resize(BAR_ACTIVE_W, BAR_ACTIVE_H)
            bar_window.move(cx, cy)
        elif new_state == AppState.IDLE:
            cx, cy = get_bar_position(BAR_IDLE_W, BAR_IDLE_H)
            bar_window.resize(BAR_IDLE_W, BAR_IDLE_H)
            bar_window.move(cx, cy)
        elif new_state == AppState.ERROR:
            # Stay at active size briefly, then shrink
            def shrink():
                import time
                time.sleep(1.0)
                cx, cy = get_bar_position(BAR_IDLE_W, BAR_IDLE_H)
                bar_window.resize(BAR_IDLE_W, BAR_IDLE_H)
                bar_window.move(cx, cy)
            threading.Thread(target=shrink, daemon=True).start()

    state_manager.on_state_change(on_state_change)

    # Handle main window close: hide instead of destroy (unless quitting)
    def on_main_closing():
        if _app_quitting:
            return True
        main_window.hide()
        return False

    main_window.events.closing += on_main_closing

    webview.start(func=lambda: _setup_dock_menu(main_window))


if __name__ == "__main__":
    main()
