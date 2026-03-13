"""Role, location, and freshness matching."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from .constants import TERMINAL_TRACKER_STATUSES
from .models import AppSettings, JobRecord
from .time_utils import to_sheet_timestamp, within_days


def normalize_text(value: str) -> str:
    """Lowercase and collapse punctuation to spaces."""

    lowered = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", lowered).strip()


def matches_role(title: str, settings: AppSettings) -> bool:
    """Return whether a title fits the strict BA/PM rule set."""

    normalized = normalize_text(title)
    if any(blocked in normalized for blocked in settings.role_exclude):
        return False
    return any(allowed in normalized for allowed in settings.role_include)


def match_metro(location: str, settings: AppSettings, metro_key: str | None = None) -> tuple[bool, str]:
    """Return whether a location matches the configured metros."""

    normalized = normalize_text(location)
    if "remote" in normalized and metro_key is None:
        return False, ""
    targets = {metro_key: settings.metros[metro_key]} if metro_key else settings.metros
    for key, aliases in targets.items():
        if any(alias in normalized for alias in aliases):
            return True, key
    return False, ""


def apply_matching(record: JobRecord, settings: AppSettings, metro_key: str | None = None) -> JobRecord:
    """Apply configured matching rules to a record."""

    record.match_role = matches_role(record.title, settings)
    record.match_location, record.matched_metro = match_metro(
        record.location_raw or record.location_normalized,
        settings,
        metro_key=metro_key,
    )
    record.freshness_status = within_days(record.posted_at, settings.freshness_days)
    return record


def stable_job_key(company_slug: str, source_job_id: str, title: str, apply_url: str) -> str:
    """Build a stable job key."""

    base = "::".join([company_slug, source_job_id or normalize_text(title), apply_url])
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]


def record_to_sheet_row(
    record: JobRecord,
    discovered_at: datetime,
    existing_row: dict[str, str] | None = None,
) -> dict[str, str]:
    """Convert a record to a sheet row while preserving manual fields."""

    existing_row = existing_row or {}
    existing_status = existing_row.get("status", "").strip().lower()
    if existing_status in TERMINAL_TRACKER_STATUSES:
        status = existing_row["status"]
    elif existing_status == "stale":
        status = "tracked"
    else:
        status = existing_row.get("status") or (
            "new" if record.freshness_status != "stale" else "tracked"
        )

    return {
        "job_key": record.job_key,
        "status": status,
        "company": record.company_name,
        "title": record.title,
        "location": record.location_normalized or record.location_raw,
        "metro": record.matched_metro or existing_row.get("metro", ""),
        "freshness_status": record.freshness_status,
        "posted_at": to_sheet_timestamp(record.posted_at),
        "discovered_at": existing_row.get("discovered_at") or to_sheet_timestamp(discovered_at),
        "apply_url": record.apply_url,
        "career_page_url": record.career_page_url,
        "source": record.ats_kind,
        "notes": existing_row.get("notes", ""),
        "manual_priority": existing_row.get("manual_priority", ""),
        "last_seen_at": to_sheet_timestamp(discovered_at),
    }
