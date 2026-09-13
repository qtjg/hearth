"""
storage.py
SQLite-backed favorites and playback history.

Every method is exception-guarded: storage is a convenience layer and must
never take the player down. One connection per operation keeps it safe for
desktop-scale concurrent reads/writes.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List

from .config import HISTORY_LIMIT
from .models import Track

log = logging.getLogger(__name__)

DB_FILENAME = "hearth.db"


class HearthStorage:
    """Favorites and history on local SQLite (stdlib only, zero bloat)."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._ensure_tables()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """Shutdown hook (connections are per-operation; nothing buffered)."""
        pass

    def _ensure_tables(self) -> None:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS favorites (
                        video_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL,
                        duration TEXT,
                        artwork_url TEXT,
                        added_at REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        video_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        artist TEXT NOT NULL,
                        duration TEXT,
                        artwork_url TEXT,
                        played_at REAL NOT NULL
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_history_played ON history(played_at DESC);"
                )
                conn.commit()
            log.info("Hearth storage ready at %s", self.db_path)
        except Exception as exc:
            log.error("storage init failed at %s: %s", self.db_path, exc)

    # ---------------------------------------------------------------- favorites
    def add_favorite(self, track: Track) -> None:
        """Insert or refresh a favorite row."""
        if not track or not track.video_id:
            return
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO favorites (video_id, title, artist, duration, artwork_url, added_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        title = excluded.title,
                        artist = excluded.artist,
                        duration = excluded.duration,
                        artwork_url = excluded.artwork_url,
                        added_at = excluded.added_at;
                    """,
                    (track.video_id, track.title, track.artist, track.duration,
                     track.artwork_url, time.time()),
                )
                conn.commit()
        except Exception as exc:
            log.error("favorite add failed for %s: %s", track.video_id, exc)

    def remove_favorite(self, video_id: str) -> None:
        if not video_id:
            return
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM favorites WHERE video_id = ?;", (video_id,))
                conn.commit()
        except Exception as exc:
            log.error("favorite remove failed for %s: %s", video_id, exc)

    def is_favorite(self, video_id: str) -> bool:
        if not video_id:
            return False
        try:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM favorites WHERE video_id = ? LIMIT 1;", (video_id,)
                ).fetchone()
                return row is not None
        except Exception as exc:
            log.error("favorite check failed for %s: %s", video_id, exc)
            return False

    def get_favorites(self) -> List[Track]:
        rows: List[Track] = []
        try:
            with self._connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT video_id, title, artist, duration, artwork_url
                    FROM favorites ORDER BY added_at DESC;
                    """
                )
                for row in cursor.fetchall():
                    rows.append(Track(
                        video_id=row["video_id"], title=row["title"], artist=row["artist"],
                        duration=row["duration"] or "", artwork_url=row["artwork_url"] or "",
                    ))
        except Exception as exc:
            log.error("favorites load failed: %s", exc)
        return rows

    # ------------------------------------------------------------------ history
    def record_history(self, track: Track) -> None:
        """Append a play and prune the table back to HISTORY_LIMIT rows."""
        if not track or not track.video_id:
            return
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO history (video_id, title, artist, duration, artwork_url, played_at)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (track.video_id, track.title, track.artist, track.duration,
                     track.artwork_url, time.time()),
                )
                conn.execute(
                    """
                    DELETE FROM history WHERE id NOT IN (
                        SELECT id FROM history ORDER BY played_at DESC LIMIT ?
                    );
                    """,
                    (HISTORY_LIMIT,),
                )
                conn.commit()
        except Exception as exc:
            log.error("history record failed for %s: %s", track.video_id, exc)

    def get_history(self, limit: int = 50) -> List[Track]:
        """Most recent plays, one row per track (newest win)."""
        rows: List[Track] = []
        try:
            with self._connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT video_id, title, artist, duration, artwork_url,
                           MAX(played_at) AS last_played
                    FROM history
                    GROUP BY video_id
                    ORDER BY last_played DESC
                    LIMIT ?;
                    """,
                    (max(1, int(limit)),),
                )
                for row in cursor.fetchall():
                    rows.append(Track(
                        video_id=row["video_id"], title=row["title"], artist=row["artist"],
                        duration=row["duration"] or "", artwork_url=row["artwork_url"] or "",
                    ))
        except Exception as exc:
            log.error("history load failed: %s", exc)
        return rows

    def clear_history(self) -> None:
        try:
            with self._connection() as conn:
                conn.execute("DELETE FROM history;")
                conn.commit()
        except Exception as exc:
            log.error("history clear failed: %s", exc)
