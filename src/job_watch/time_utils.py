"""Time parsing utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """Return the current UTC time."""

    return datetime.now(tz=UTC)


def parse_datetime(value: object) -> datetime | None:
    """Parse datetimes from common ATS payload formats."""

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=UTC)
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if normalized.startswith("Posted "):
            return _parse_relative_posted(normalized)
        normalized = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    parsed = datetime.strptime(normalized, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _parse_relative_posted(value: str) -> datetime | None:
    lowered = value.lower().removeprefix("posted ").strip()
    now = utc_now()
    if lowered in {"today", "just now"}:
        return now
    if lowered == "yesterday":
        return now - timedelta(days=1)
    tokens = lowered.split()
    if len(tokens) < 2 or not tokens[0].isdigit():
        return None
    amount = int(tokens[0])
    unit = tokens[1]
    if unit.startswith("day"):
        return now - timedelta(days=amount)
    if unit.startswith("hour"):
        return now - timedelta(hours=amount)
    if unit.startswith("week"):
        return now - timedelta(days=amount * 7)
    return None


def to_sheet_timestamp(value: datetime | None) -> str:
    """Convert a datetime to a UTC ISO string for sheet storage."""

    if value is None:
        return ""
    aware = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def within_days(value: datetime | None, days: int) -> str:
    """Return freshness classification for a posting."""

    if value is None:
        return "unknown"
    return "fresh" if value >= utc_now() - timedelta(days=days) else "stale"
