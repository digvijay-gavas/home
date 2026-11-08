"""Bounded, local SQLite history shared by the listener and settings viewer."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3


def log_path(config_path):
    return Path(config_path).resolve().with_suffix(".events.sqlite3")


class EventLog:
    def __init__(self, path, retention=1000):
        if retention < 1:
            raise ValueError("Retention must be positive")
        self.path = Path(path)
        self.retention = retention

    def append(self, event):
        payload = json.dumps(event, ensure_ascii=False, allow_nan=False)
        with closing(sqlite3.connect(self.path, timeout=2)) as connection:
            with connection:
                connection.execute("""CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL
                )""")
                connection.execute("INSERT OR IGNORE INTO events (event_id, payload) VALUES (?, ?)",
                                   (event["id"], payload))
                connection.execute("""DELETE FROM events WHERE sequence NOT IN
                    (SELECT sequence FROM events ORDER BY sequence DESC LIMIT ?)""", (self.retention,))

    def latest(self, limit=200):
        if not self.path.exists():
            return []
        # Opening settings must not create a log or write to an existing one.
        with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)) as connection:
            rows = connection.execute("SELECT payload FROM events ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
        events = []
        for (payload,) in rows:
            try:
                event = json.loads(payload)
                if isinstance(event, dict) and "id" in event:
                    events.append(event)
            except json.JSONDecodeError:
                continue
        return events

    def clear(self):
        if self.path.exists():
            with closing(sqlite3.connect(self.path, timeout=2)) as connection:
                with connection:
                    connection.execute("DELETE FROM events")
