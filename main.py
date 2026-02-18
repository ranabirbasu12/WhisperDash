# main.py
import os
import sys
import threading

# Fix SSL certificates in py2app bundle.
# __boot__.py sets SSL_CERT_FILE to a non-existent path; point it at certifi's CA bundle.
if getattr(sys, 'frozen', None) == 'macosx_app':
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ.pop('SSL_CERT_DIR', None)

import objc
import AppKit
import uvicorn
import webview

from app import create_app
from recorder import AudioRecorder
from transcriber import WhisperTranscriber
from hotkey import GlobalHotkey
from pipeline import StreamingPipeline
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


def _patch_window_host_as_panel():
    """Replace pywebview's WindowHost (NSWindow) with NSPanel.

    NSPanel is required for a window to reliably appear above full-screen apps.
    NSWindow + FullScreenAuxiliary is unreliable — macOS treats NSPanel specially
    for full-screen Space participation (confirmed by Helium app and Electron).
    """
    import webview.platforms.cocoa as cocoa_backend

    # Define an NSPanel subclass that floats above full-screen apps.
    # Collection behavior and hidesOnDeactivate must be set at init time —
    # setting them after the window is shown is too late for Space membership.
    class _PanelHost(AppKit.NSPanel):
        def initWithContentRect_styleMask_backing_defer_(self, rect, mask, backing, defer):
            # Add NonactivatingPanel so clicking won't steal focus from full-screen apps
            mask |= 1 << 7  # NSWindowStyleMaskNonactivatingPanel
            self = objc.super(_PanelHost, self).initWithContentRect_styleMask_backing_defer_(
                rect, mask, backing, defer,
            )
            if self is not None:
                self.setHidesOnDeactivate_(False)
                self.setCollectionBehavior_(
                    1 << 0   # NSWindowCollectionBehaviorCanJoinAllSpaces
                    | 1 << 8  # NSWindowCollectionBehaviorFullScreenAuxiliary
                )
            return self

        def canBecomeKeyWindow(self):
            return True

        def canBecomeMainWindow(self):
            return True

    cocoa_backend.BrowserView.WindowHost = _PanelHost


def _configure_bar_window(bar_window):
    """Make the bar float above full-screen apps and appear on all Spaces."""
    nswindow = bar_window.native
    if nswindow is None:
        return

    nswindow.setLevel_(AppKit.NSStatusWindowLevel)
    nswindow.setHidesOnDeactivate_(False)

    # NonactivatingPanel: clicking the bar won't steal focus from the full-screen app
    mask = nswindow.styleMask() | (1 << 7)  # NSWindowStyleMaskNonactivatingPanel
    nswindow.setStyleMask_(mask)

    behavior = (
        1 << 0   # NSWindowCollectionBehaviorCanJoinAllSpaces
        | 1 << 8  # NSWindowCollectionBehaviorFullScreenAuxiliary
    )
    nswindow.setCollectionBehavior_(behavior)


def _configure_main_window(main_window):
    """Undo NSPanel defaults on the main dashboard window.

    The monkey-patched _PanelHost gives all windows FullScreenAuxiliary,
    but only the bar should join full-screen Spaces.
    """
    nswindow = main_window.native
    if nswindow is None:
        return
    nswindow.setHidesOnDeactivate_(False)
    # Reset to normal managed behavior — don't join full-screen Spaces
    nswindow.setCollectionBehavior_(
        1 << 2  # NSWindowCollectionBehaviorManaged
    )


def main():
    transcriber = WhisperTranscriber()
    state_manager = AppStateManager()
    history = TranscriptionHistory()
    settings = SettingsManager()
    pipeline = StreamingPipeline(transcriber)

    app = create_app(
        transcriber=transcriber,
        state_manager=state_manager,
        history=history,
        settings=settings,
        pipeline=pipeline,
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
        pipeline=pipeline,
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

    # Use NSPanel instead of NSWindow so the bar can float above full-screen apps
    _patch_window_host_as_panel()

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

    def _on_start():
        _setup_dock_menu(main_window)
        _configure_bar_window(bar_window)
        _configure_main_window(main_window)

    webview.start(func=_on_start)


if __name__ == "__main__":
    main()
