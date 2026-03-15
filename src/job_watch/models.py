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
    listing_url: str | None = None
    tenant_hint: str | None = None
    requires_browser: bool = False
    request_options: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    official_career_site_url: str | None = None
    source_policy: str | None = None


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
    source_retry_attempts: int = 2
    sheet_id_env_var: str = "GOOGLE_SHEET_ID"
    role_families: list[str] = field(default_factory=list)
    new_grad_positive_terms: list[str] = field(default_factory=list)
    seniority_negative_terms: list[str] = field(default_factory=list)
    internship_terms: list[str] = field(default_factory=list)
    rotational_terms: list[str] = field(default_factory=list)
    max_experience_years: int = 2
    high_precision_new_grad: bool = True
    location_mode: str = "metros"
    allow_remote_us: bool = False
    us_location_terms: list[str] = field(default_factory=list)
    non_us_location_terms: list[str] = field(default_factory=list)


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
    match_new_grad: bool = False
    match_location: bool = False
    freshness_status: str = "unknown"
    matched_metro: str | None = None
    match_reason: str = ""


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
class FaangStatusResult:
    """Status for a single FAANG+ target company."""

    company_slug: str
    company_name: str
    ats_kind: str
    in_catalog: bool
    enabled: bool
    adapter_registered: bool
    policy_ok: bool
    fetch_ok: bool
    jobs_found: int
    status: str
    reason: str
    source_policy: str | None = None
    official_career_site_url: str | None = None
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
    company_results: list[dict[str, str | int | None]]


@dataclass(slots=True)
class TrackerSyncResult:
    """Sheet synchronization result."""

    inserted_keys: set[str]
    updated_keys: set[str]
    all_rows: list[dict[str, str]]


@dataclass(slots=True)
class CleanupSummary:
    """Results for one-time tracker cleanup operations."""

    scanned_rows: int
    archived_rows: int
    skipped_terminal_rows: int
    report_rows: list[dict[str, str]]


JsonDict = dict[str, Any]
