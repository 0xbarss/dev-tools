"""Small, dependency-free helper functions shared across commands."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_SIZE_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([A-Za-z]*)\s*$")
_SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024**2,
    "MB": 1024**2,
    "G": 1024**3,
    "GB": 1024**3,
}

_DURATION_RE = re.compile(r"^\s*([0-9]+)\s*([a-zA-Z]+)\s*$")
_DURATION_UNITS = {
    "s": 1,
    "sec": 1,
    "secs": 1,
    "m": 60,
    "min": 60,
    "mins": 60,
    "h": 3600,
    "hr": 3600,
    "hrs": 3600,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "w": 604800,
    "week": 604800,
    "weeks": 604800,
}


class ParseError(ValueError):
    """Raised when a human-friendly size/duration string can't be parsed."""


def parse_size(text: str) -> int:
    """Parse strings like '5MB', '512K', '10' (bytes) into an integer byte count."""
    m = _SIZE_RE.match(text)
    if not m:
        raise ParseError(f"Could not parse size: {text!r}")
    value, unit = m.groups()
    unit = unit.upper()
    if unit not in _SIZE_UNITS:
        raise ParseError(f"Unknown size unit {unit!r} in {text!r}")
    return int(float(value) * _SIZE_UNITS[unit])


def parse_duration_to_seconds(text: str) -> int:
    """Parse strings like '30d', '2w', '12h' into seconds."""
    m = _DURATION_RE.match(text)
    if not m:
        raise ParseError(f"Could not parse duration: {text!r}")
    value, unit = m.groups()
    unit = unit.lower()
    if unit not in _DURATION_UNITS:
        raise ParseError(f"Unknown duration unit {unit!r} in {text!r}")
    return int(value) * _DURATION_UNITS[unit]


def cutoff_datetime(older_than: str) -> datetime:
    """Return the UTC datetime before which files are considered 'older than'."""
    seconds = parse_duration_to_seconds(older_than)
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def human_size(num_bytes: float) -> str:
    """Format a byte count as a human-readable string, e.g. 1.5MB."""
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < step:
            return f"{num_bytes:.1f}{unit}" if unit != "B" else f"{int(num_bytes)}{unit}"
        num_bytes /= step
    return f"{num_bytes:.1f}PB"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9_-]+", "-", name)
    return re.sub(r"-{2,}", "-", name).strip("-")