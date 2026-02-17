# tests/test_history.py
import os
import tempfile
from history import TranscriptionHistory


def make_history(db_path=None):
    if db_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        db_path = tmp.name
        tmp.close()
    return TranscriptionHistory(db_path), db_path


def test_add_and_get_recent():
    h, path = make_history()
    h.add("Hello world", duration=2.5, latency=0.8)
    h.add("Second entry", duration=3.0, latency=0.5)
    entries = h.get_recent(limit=10)
    assert len(entries) == 2
    assert entries[0]["text"] == "Second entry"  # most recent first
    assert entries[1]["text"] == "Hello world"
    os.unlink(path)


def test_get_recent_respects_limit():
    h, path = make_history()
    for i in range(5):
        h.add(f"Entry {i}", duration=1.0, latency=0.5)
    entries = h.get_recent(limit=3)
    assert len(entries) == 3
    os.unlink(path)


def test_get_recent_respects_offset():
    h, path = make_history()
    for i in range(5):
        h.add(f"Entry {i}", duration=1.0, latency=0.5)
    entries = h.get_recent(limit=2, offset=2)
    assert len(entries) == 2
    assert entries[0]["text"] == "Entry 2"
    os.unlink(path)


def test_search():
    h, path = make_history()
    h.add("The quick brown fox", duration=2.0, latency=0.5)
    h.add("Hello world", duration=1.5, latency=0.3)
    h.add("Fox jumps over", duration=1.0, latency=0.4)
    results = h.search("fox")
    assert len(results) == 2
    os.unlink(path)


def test_entry_has_all_fields():
    h, path = make_history()
    h.add("Test", duration=2.5, latency=0.8)
    entry = h.get_recent(limit=1)[0]
    assert "id" in entry
    assert "text" in entry
    assert "timestamp" in entry
    assert entry["duration_seconds"] == 2.5
    assert entry["latency_seconds"] == 0.8
    os.unlink(path)


def test_count():
    h, path = make_history()
    assert h.count() == 0
    h.add("One", duration=1.0, latency=0.5)
    h.add("Two", duration=1.0, latency=0.5)
    assert h.count() == 2
    os.unlink(path)
