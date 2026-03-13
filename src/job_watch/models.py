"""Data models for Job Watch."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CompanyConfig:
    """Configured company source definition."""

    slug: str
    name: str
    category: str
    ats_kind: str
    career_url: str
    enabled: bool = True
    board_token: str | None = None
    site: str | None = None
    company_identifier: str | None = None
    feed_url: str | None = None
    tenant_hint: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AppSettings:
    """Application settings loaded from TOML."""

    metros: dict[str, list[str]]
    role_include: list[str]
    role_exclude: list[str]
    freshness_days: int
    concurrency: int
    timeout_seconds: float
    sheet_tab_name: str
    sheet_id_env_var: str = "GOOGLE_SHEET_ID"


@dataclass(slots=True)
class JobRecord:
    """Normalized job posting."""

    job_key: str
    company_slug: str
    company_name: str
    ats_kind: str
    source_job_id: str
    title: str
    team: str
    department: str
    location_raw: str
    location_normalized: str
    posted_at: datetime | None
    updated_at: datetime | None
    apply_url: str
    career_page_url: str
    employment_type: str
    remote_flag: bool
    description_text: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    match_role: bool = False
    match_location: bool = False
    freshness_status: str = "unknown"
    matched_metro: str | None = None


@dataclass(slots=True)
class FetchResult:
    """Result of fetching jobs for a single company."""

    company: CompanyConfig
    jobs: list[JobRecord] = field(default_factory=list)
    error: str | None = None


@dataclass(slots=True)
class SourceCheckResult:
    """Sources-check status for a company."""

    company_slug: str
    company_name: str
    ats_kind: str
    ok: bool
    jobs_found: int = 0
    error: str | None = None


@dataclass(slots=True)
class ScanSummary:
    """Aggregated scan output."""

    scanned_companies: int
    fetched_jobs: int
    matched_jobs: int
    new_rows: int
    new_alerts: int
    updated_rows: int
    failures: list[str]
    alert_rows: list[dict[str, str]]


@dataclass(slots=True)
class TrackerSyncResult:
    """Sheet synchronization result."""

    inserted_keys: set[str]
    updated_keys: set[str]
    all_rows: list[dict[str, str]]


JsonDict = dict[str, Any]
