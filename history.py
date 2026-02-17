# history.py
import os
import sqlite3
from datetime import datetime, timezone


DEFAULT_DB_PATH = os.path.expanduser("~/.whisperdash/history.db")


class TranscriptionHistory:
    """SQLite-backed transcription history."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    duration_seconds REAL,
                    latency_seconds REAL
                )
            """)

    def add(self, text: str, duration: float = 0.0, latency: float = 0.0):
        ts = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO transcriptions (text, timestamp, duration_seconds, latency_seconds) VALUES (?, ?, ?, ?)",
                (text, ts, duration, latency),
            )

    def get_recent(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 50) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM transcriptions WHERE text LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]
