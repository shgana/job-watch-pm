"""Role, location, and freshness matching."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from .constants import TERMINAL_TRACKER_STATUSES
from .models import AppSettings, JobRecord
from .time_utils import to_sheet_timestamp, within_days

US_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}
US_STATE_NAMES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
}
YEARS_RANGE_RE = re.compile(r"\b(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to)\s*(\d{1,2})\s*years?\b")
YEARS_SINGLE_RE = re.compile(r"\b(\d{1,2})(?:\s*(?:\+|plus))?\s*years?\b")


def normalize_text(value: str) -> str:
    """Lowercase and collapse punctuation to spaces."""

    lowered = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", lowered).strip()


def matches_role(title: str, settings: AppSettings) -> bool:
    """Return whether a title fits the configured target role families."""

    normalized = normalize_text(title)
    include_terms = settings.role_families or settings.role_include
    if any(blocked in normalized for blocked in settings.role_exclude):
        return False
    return any(allowed in normalized for allowed in include_terms)


def _extract_experience_thresholds(text: str) -> tuple[int | None, int | None]:
    """Extract minimum and maximum years of experience mentioned in text."""

    minimum: int | None = None
    maximum: int | None = None
    for match in YEARS_RANGE_RE.finditer(text):
        low = int(match.group(1))
        high = int(match.group(2))
        minimum = low if minimum is None else min(minimum, low)
        maximum = high if maximum is None else max(maximum, high)
    for match in YEARS_SINGLE_RE.finditer(text):
        low = int(match.group(1))
        minimum = low if minimum is None else min(minimum, low)
        maximum = low if maximum is None else max(maximum, low)
    return minimum, maximum


def _build_role_text(record: JobRecord) -> str:
    return normalize_text(
        " ".join(
            part
            for part in [
                record.title,
                record.team,
                record.department,
                record.employment_type,
                record.description_text,
            ]
            if part
        )
    )


def classify_new_grad(record: JobRecord, settings: AppSettings) -> tuple[bool, str]:
    """Classify whether the role appears to target full-time early-career candidates."""

    title_text = normalize_text(record.title)
    role_text = _build_role_text(record)
    include_terms = settings.role_families or settings.role_include
    has_role_family = any(term in title_text for term in include_terms)
    if not has_role_family:
        return False, "missing_role_family"
    if any(term in role_text for term in settings.role_exclude):
        return False, "excluded_role_family"
    if any(term in role_text for term in settings.internship_terms):
        return False, "internship_role"
    if any(term in role_text for term in settings.seniority_negative_terms):
        return False, "senior_signal"

    min_years, max_years = _extract_experience_thresholds(role_text)
    if min_years is not None and min_years > settings.max_experience_years:
        return False, "experience_too_high"

    positive_signal = any(term in role_text for term in settings.new_grad_positive_terms)
    rotational_signal = any(term in role_text for term in settings.rotational_terms)
    explicit_early_experience = max_years is not None and max_years <= settings.max_experience_years
    if settings.high_precision_new_grad and not (
        positive_signal or rotational_signal or explicit_early_experience
    ):
        return False, "missing_early_career_signal"
    return True, "matched_new_grad"


def _contains_us_state_hint(normalized_location: str) -> bool:
    if any(state in normalized_location for state in US_STATE_NAMES):
        return True
    raw_upper = normalized_location.upper()
    chunks = re.split(r"[|;/]", raw_upper)
    for chunk in chunks:
        tokens = [token for token in re.split(r"[\s,()]+", chunk.strip()) if token]
        if len(tokens) < 2:
            continue
        if tokens[-1] in US_STATE_CODES:
            return True
    return False


def match_us_location(location: str, settings: AppSettings) -> tuple[bool, str]:
    normalized = normalize_text(location)
    if not normalized:
        return False, ""
    has_remote = "remote" in normalized
    has_us_term = any(term in normalized for term in settings.us_location_terms)
    has_non_us_term = any(term in normalized for term in settings.non_us_location_terms)
    has_us_state = _contains_us_state_hint(normalized)
    if has_remote and settings.allow_remote_us:
        if has_non_us_term and not (has_us_term or has_us_state):
            return False, ""
        return True, "us_remote"
    if has_non_us_term and not (has_us_term or has_us_state):
        return False, ""
    if has_us_term or has_us_state:
        return True, "us"
    return False, ""


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

    record.match_new_grad, record.match_reason = classify_new_grad(record, settings)
    record.match_role = record.match_new_grad
    if settings.location_mode == "us_or_remote":
        record.match_location, record.matched_metro = match_us_location(
            record.location_raw or record.location_normalized,
            settings,
        )
    else:
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
