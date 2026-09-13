"""SQLite favorites & playback history — zero external bloat."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Track

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    video_id   TEXT PRIMARY KEY,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT (unixepoch('now'))
);
CREATE TABLE IF NOT EXISTS history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT NOT NULL,
    payload    TEXT NOT NULL,
    played_at  REAL NOT NULL DEFAULT (unixepoch('now'))
);
CREATE INDEX IF NOT EXISTS idx_history_played ON history (played_at DESC);
"""


class HearthStore:
    """Persistent local library (favorites) and listening history."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path))
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # --- favorites ---

    def pin(self, track: Track) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO favorites (video_id, payload) VALUES (?, ?)",
            (track.video_id, track.to_json()),
        )
        self._db.commit()

    def unpin(self, video_id: str) -> None:
        self._db.execute("DELETE FROM favorites WHERE video_id = ?", (video_id,))
        self._db.commit()

    def is_pinned(self, video_id: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM favorites WHERE video_id = ?", (video_id,)
        ).fetchone()
        return row is not None

    def favorites(self) -> list[Track]:
        rows = self._db.execute(
            "SELECT payload FROM favorites ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
        return [Track.from_json(payload) for (payload,) in rows]

    # --- history ---

    def log_play(self, track: Track) -> None:
        self._db.execute(
            "INSERT INTO history (video_id, payload) VALUES (?, ?)",
            (track.video_id, track.to_json()),
        )
        self._db.commit()

    def history(self, limit: int = 100) -> list[Track]:
        rows = self._db.execute(
            "SELECT payload FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [Track.from_json(payload) for (payload,) in rows]

    def prune_history(self, keep: int = 500) -> int:
        """Delete history beyond the newest `keep` rows. Returns rows removed."""
        cur = self._db.execute(
            "DELETE FROM history WHERE id NOT IN "
            "(SELECT id FROM history ORDER BY id DESC LIMIT ?)",
            (keep,),
        )
        self._db.commit()
        return cur.rowcount
