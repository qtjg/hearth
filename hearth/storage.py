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

    def top_tracks(self, limit: int = 10) -> list[Track]:
        """Most-played tracks; ties broken by most-recent play."""
        rows = self._db.execute(
            "SELECT payload FROM history GROUP BY video_id "
            "ORDER BY COUNT(*) DESC, MAX(played_at) DESC LIMIT ?",
            (limit,),
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

    # --- library backup (portable JSON, favorites + playlists) ---

    EXPORT_FORMAT = "hearth-library"

    def export_library(self) -> dict:
        """Everything user-created as one portable dict."""
        return {
            "format": self.EXPORT_FORMAT,
            "version": 1,
            "favorites": [t.to_dict() for t in self.favorites()],
            "playlists": [
                {
                    "name": name,
                    "tracks": [t.to_dict() for t in self.playlist_tracks(pid)],
                }
                for pid, name, _count in self.playlists()
            ],
        }

    def import_library(self, data: dict, merge: bool = False) -> tuple[int, int]:
        """Restore an export_library() dict. Returns (playlists, tracks) added.

        merge=False wipes the current library first; merge=True skips entries
        that already exist. Corrupt entries are skipped individually — a
        partial file restores as much as it can.
        """
        if not isinstance(data, dict) or data.get("format") != self.EXPORT_FORMAT:
            raise ValueError("not a hearth library export")
        if not merge:
            for pid, _name, _count in self.playlists():
                self.delete_playlist(pid)
            for track in self.favorites():
                self.unpin(track.video_id)

        playlists_added = 0
        tracks_added = 0
        for entry in data.get("favorites") or []:
            track = self._track_from(entry)
            if track is None or self.is_pinned(track.video_id):
                continue
            self.pin(track)
            tracks_added += 1
        for entry in data.get("playlists") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            pid = self._playlist_for_import(name, merge=merge)
            if pid is None:
                playlists_added += 1
                pid = self.create_playlist(name)
            for track_data in entry.get("tracks") or []:
                track = self._track_from(track_data)
                if track is not None and self.add_to_playlist(pid, track):
                    tracks_added += 1
        return playlists_added, tracks_added

    def _playlist_for_import(self, name: str, merge: bool) -> int | None:
        """merge=True reuses a same-named playlist; None = create a new one."""
        if not merge:
            return None
        for pid, existing, _count in self.playlists():
            if existing == name:
                return pid
        return None

    def _track_from(self, data) -> Track | None:
        if not isinstance(data, dict):
            return None
        try:
            track = Track.from_dict(data)
        except (TypeError, ValueError):
            return None
        if not track.video_id or not track.title:
            return None
        return track
