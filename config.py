# config.py
import os
import json
import threading

CONFIG_DIR = os.path.expanduser("~/.whisperdash")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_HOTKEY = "alt_r"

# macOS virtual keycodes → serialized key names
KEYCODE_TO_NAME = {
    # Modifiers
    54: "cmd_r", 55: "cmd_l", 56: "shift_l", 57: "caps_lock",
    58: "alt_l", 59: "ctrl_l", 60: "shift_r", 61: "alt_r",
    62: "ctrl_r", 63: "fn",
    # Function keys (standard keycodes)
    122: "f1", 120: "f2", 99: "f3", 118: "f4",
    96: "f5", 97: "f6", 98: "f7", 100: "f8",
    101: "f9", 109: "f10", 103: "f11", 111: "f12",
    105: "f13", 107: "f14", 113: "f15", 106: "f16",
    64: "f17", 79: "f18", 80: "f19", 90: "f20",
    # MacBook media-mode keycodes (bare F-keys without Fn)
    145: "f1", 144: "f2", 160: "f3", 131: "f4",
    176: "f5", 177: "f6",
    # Special keys
    36: "enter", 48: "tab", 49: "space", 51: "backspace", 53: "esc",
    # Letters
    0: "char:a", 1: "char:s", 2: "char:d", 3: "char:f",
    4: "char:h", 5: "char:g", 6: "char:z", 7: "char:x",
    8: "char:c", 9: "char:v", 11: "char:b", 12: "char:q",
    13: "char:w", 14: "char:e", 15: "char:r", 16: "char:y",
    17: "char:t", 31: "char:o", 32: "char:u", 34: "char:i",
    35: "char:p", 37: "char:l", 38: "char:j", 40: "char:k",
    45: "char:n", 46: "char:m",
    # Numbers
    18: "char:1", 19: "char:2", 20: "char:3", 21: "char:4",
    23: "char:5", 22: "char:6", 26: "char:7", 28: "char:8",
    25: "char:9", 29: "char:0",
    # Arrow keys
    123: "left", 124: "right", 125: "down", 126: "up",
}

NAME_TO_KEYCODE = {v: k for k, v in KEYCODE_TO_NAME.items()}

# Reverse mapping: name → ALL keycodes (handles MacBook dual keycodes)
NAME_TO_KEYCODES: dict[str, frozenset[int]] = {}
for _kc, _name in KEYCODE_TO_NAME.items():
    NAME_TO_KEYCODES.setdefault(_name, set()).add(_kc)
NAME_TO_KEYCODES = {k: frozenset(v) for k, v in NAME_TO_KEYCODES.items()}

DISPLAY_NAMES = {
    "alt_r": "Right Option",
    "alt_l": "Left Option",
    "ctrl_r": "Right Control",
    "ctrl_l": "Left Control",
    "cmd_r": "Right Command",
    "cmd_l": "Left Command",
    "shift_r": "Right Shift",
    "shift_l": "Left Shift",
    "fn": "Fn",
    "space": "Space",
    "tab": "Tab",
    "caps_lock": "Caps Lock",
    "backspace": "Backspace",
    "enter": "Enter",
    "esc": "Escape",
    "left": "Left Arrow",
    "right": "Right Arrow",
    "up": "Up Arrow",
    "down": "Down Arrow",
    **{f"f{i}": f"F{i}" for i in range(1, 21)},
}


def key_to_string(keycode: int) -> str:
    """Convert a macOS virtual keycode to its serialized string form."""
    return KEYCODE_TO_NAME.get(keycode, "")


def string_to_key(s: str) -> int:
    """Convert a serialized key string to a macOS virtual keycode."""
    if s in NAME_TO_KEYCODE:
        return NAME_TO_KEYCODE[s]
    raise KeyError(f"Unknown key: {s}")


def string_to_keycodes(s: str) -> frozenset[int]:
    """Return ALL macOS keycodes for a key name (handles MacBook dual keycodes)."""
    if s in NAME_TO_KEYCODES:
        return NAME_TO_KEYCODES[s]
    raise KeyError(f"Unknown key: {s}")


def display_name(serialized: str) -> str:
    """Return human-readable name for a serialized key string."""
    if serialized in DISPLAY_NAMES:
        return DISPLAY_NAMES[serialized]
    if serialized.startswith("char:"):
        return serialized[5:].upper()
    return serialized.replace("_", " ").title()


class SettingsManager:
    """Loads/saves ~/.whisperdash/config.json and notifies on changes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: dict = {}
        self._hotkey_callbacks: list = []
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    @property
    def hotkey_string(self) -> str:
        return self._data.get("hotkey", DEFAULT_HOTKEY)

    @property
    def hotkey_display(self) -> str:
        return display_name(self.hotkey_string)

    @property
    def hotkey_key(self) -> frozenset[int]:
        """Return ALL macOS keycodes for the current hotkey."""
        try:
            return string_to_keycodes(self.hotkey_string)
        except (KeyError, ValueError):
            return string_to_keycodes(DEFAULT_HOTKEY)

    def set_hotkey(self, serialized: str) -> bool:
        """Validate, save, and notify. Returns True on success."""
        try:
            string_to_key(serialized)
        except (KeyError, ValueError):
            return False

        with self._lock:
            old = self.hotkey_string
            self._data["hotkey"] = serialized
            self._save()

        if old != serialized:
            for cb in self._hotkey_callbacks:
                try:
                    cb(serialized)
                except Exception:
                    pass
        return True

    def get(self, key: str, default=None):
        """Get an arbitrary config value."""
        return self._data.get(key, default)

    def set(self, key: str, value):
        """Set an arbitrary config value and persist."""
        with self._lock:
            self._data[key] = value
            self._save()

    def on_hotkey_change(self, callback):
        """Register a callback: fn(new_serialized_string)."""
        self._hotkey_callbacks.append(callback)
