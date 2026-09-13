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
CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT (unixepoch('now'))
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    video_id    TEXT NOT NULL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (playlist_id, position)
);
"""


class HearthStore:
    """Persistent local library (favorites) and listening history."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.db_path))
        self._db.execute("PRAGMA foreign_keys = ON")
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

    # --- playlists ---

    def create_playlist(self, name: str) -> int:
        cur = self._db.execute(
            "INSERT INTO playlists (name) VALUES (?)", (name.strip(),)
        )
        self._db.commit()
        return int(cur.lastrowid)

    def rename_playlist(self, playlist_id: int, name: str) -> None:
        self._db.execute(
            "UPDATE playlists SET name = ? WHERE id = ?", (name.strip(), playlist_id)
        )
        self._db.commit()

    def delete_playlist(self, playlist_id: int) -> None:
        self._db.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
        )
        self._db.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        self._db.commit()

    def playlists(self) -> list[tuple[int, str, int]]:
        """[(id, name, track_count)] oldest first — stable sidebar order."""
        rows = self._db.execute(
            "SELECT p.id, p.name, COUNT(t.position) FROM playlists p "
            "LEFT JOIN playlist_tracks t ON t.playlist_id = p.id "
            "GROUP BY p.id ORDER BY p.id"
        ).fetchall()
        return [(int(pid), name, int(count)) for pid, name, count in rows]

    def playlist_name(self, playlist_id: int) -> str | None:
        row = self._db.execute(
            "SELECT name FROM playlists WHERE id = ?", (playlist_id,)
        ).fetchone()
        return row[0] if row else None

    def add_to_playlist(self, playlist_id: int, track: Track) -> bool:
        """Append a track (skips duplicates). True when inserted."""
        row = self._db.execute(
            "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, track.video_id),
        ).fetchone()
        if row is not None:
            return False
        nxt = self._db.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks "
            "WHERE playlist_id = ?",
            (playlist_id,),
        ).fetchone()[0]
        self._db.execute(
            "INSERT INTO playlist_tracks (playlist_id, position, video_id, payload) "
            "VALUES (?, ?, ?, ?)",
            (playlist_id, int(nxt), track.video_id, track.to_json()),
        )
        self._db.commit()
        return True

    def remove_from_playlist(self, playlist_id: int, video_id: str) -> int:
        """Drop every occurrence of a track, then compact positions."""
        cur = self._db.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id),
        )
        rows = self._db.execute(
            "SELECT position FROM playlist_tracks WHERE playlist_id = ? "
            "ORDER BY position",
            (playlist_id,),
        ).fetchall()
        for new_pos, (old_pos,) in enumerate(rows, start=1):
            if old_pos != new_pos:
                self._db.execute(
                    "UPDATE playlist_tracks SET position = ? "
                    "WHERE playlist_id = ? AND position = ?",
                    (new_pos, playlist_id, old_pos),
                )
        self._db.commit()
        return cur.rowcount

    def playlist_tracks(self, playlist_id: int) -> list[Track]:
        rows = self._db.execute(
            "SELECT payload FROM playlist_tracks WHERE playlist_id = ? "
            "ORDER BY position",
            (playlist_id,),
        ).fetchall()
        return [Track.from_json(payload) for (payload,) in rows]
