"""
utils.py
Small helpers with zero dependencies on the rest of the package.
"""

from __future__ import annotations


def clock(ms: int) -> str:
    """Milliseconds to m:ss (or h:mm:ss past an hour). Negative clamps to 0."""
    total = max(0, int(ms or 0)) // 1000
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def looks_like_link(text: str) -> bool:
    """True when the field holds a URL the resolver should handle directly."""
    probe = (text or "").strip().lower()
    return (
        probe.startswith("http://")
        or probe.startswith("https://")
        or "youtu.be/" in probe
        or "youtube.com/watch" in probe
        or "music.youtube.com" in probe
    )


def pretty_count(value: int, singular: str, plural: str = "") -> str:
    """'1 track' / '12 tracks' without the caller branching."""
    word = singular if value == 1 else (plural or singular + "s")
    return f"{value} {word}"


def clamp(value: int, low: int, high: int) -> int:
    """Clamp an int into [low, high]."""
    return max(low, min(high, int(value)))
