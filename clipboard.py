import pyperclip


def copy_to_clipboard(text: str) -> None:
    pyperclip.copy(text)
