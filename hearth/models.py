"""Track dataclass and serialization helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields


@dataclass
class Album:
    """An album container from the catalogue — opened, not directly playable."""

    browse_id: str
    title: str
    artist: str = ""
    year: str = ""
    thumbnail: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


@dataclass
class Track:
    """A playable song in the Hearth universe."""

    video_id: str
    title: str
    artist: str
    duration: str = ""          # human readable, e.g. "3:45"
    duration_sec: int = 0
    thumbnail: str = ""
    playlist_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Track":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "Track":
        return cls.from_dict(json.loads(raw))

    @property
    def display_name(self) -> str:
        return f"{self.artist} — {self.title}" if self.artist else self.title


def format_duration(seconds: int | float | None) -> str:
    """441 -> '7:21'; None/negative -> ''."""
    if seconds is None or seconds < 0:
        return ""
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_duration(text: str) -> int:
    """'3:45' -> 225; '1:02:03' -> 3723; garbage -> 0."""
    if not text:
        return 0
    parts = text.strip().split(":")
    if not all(p.isdigit() for p in parts):
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total
