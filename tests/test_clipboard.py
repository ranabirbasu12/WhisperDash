import pyperclip
from clipboard import copy_to_clipboard


def test_copy_to_clipboard():
    copy_to_clipboard("hello whisperdash")
    assert pyperclip.paste() == "hello whisperdash"


def test_copy_empty_string():
    copy_to_clipboard("")
    assert pyperclip.paste() == ""
