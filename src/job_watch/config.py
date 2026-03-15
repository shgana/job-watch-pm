"""Configuration loading for Job Watch."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

from .models import AppSettings, CompanyConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.toml"
DEFAULT_COMPANIES_PATH = PROJECT_ROOT / "config" / "companies.toml"
ATS_REDIRECT_KINDS = {"greenhouse", "ashby", "lever", "smartrecruiters", "workday"}

DEFAULT_NEW_GRAD_POSITIVE = [
    "new grad",
    "new graduate",
    "recent graduate",
    "entry level",
    "early career",
    "associate",
    "apm",
    "college hire",
    "university grad",
    "campus",
    "rotation program",
    "rotational program",
]
DEFAULT_SENIORITY_NEGATIVE = [
    "senior",
    " sr ",
    "staff",
    "principal",
    "lead",
    "director",
    "head of",
    "vp",
    "vice president",
    "manager ii",
    "manager iii",
    "level 3",
    "level 4",
]
DEFAULT_INTERNSHIP_TERMS = ["intern", "internship", "co-op", "coop", "co op"]
DEFAULT_ROTATIONAL_TERMS = ["rotation", "rotational", "associate program", "graduate program"]
DEFAULT_US_LOCATION_TERMS = [
    "united states",
    "usa",
    "u.s.",
    "u.s.a",
    "us remote",
    "remote us",
]
DEFAULT_NON_US_LOCATION_TERMS = [
    "canada",
    "united kingdom",
    "uk",
    "india",
    "germany",
    "france",
    "spain",
    "ireland",
    "singapore",
    "japan",
    "australia",
    "mexico",
    "brazil",
    "netherlands",
]


def load_settings(settings_path: str | None = None) -> AppSettings:
    """Load application settings from TOML."""

    path = Path(settings_path or os.environ.get("JOB_WATCH_SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
    data = _load_toml(path)
    role_rules = data.get("role_rules", {})
    role_include = [item.lower() for item in role_rules.get("include", [])]
    role_exclude = [item.lower() for item in role_rules.get("exclude", [])]

    role_families = data.get("role_families", {})
    new_grad_rules = data.get("new_grad_rules", {})
    location_rules = data.get("location_rules", {})
    return AppSettings(
        metros={key: [alias.lower() for alias in value] for key, value in data["metros"].items()},
        role_include=role_include,
        role_exclude=role_exclude,
        freshness_days=int(data["scan"]["freshness_days"]),
        concurrency=int(data["request"]["concurrency"]),
        timeout_seconds=float(data["request"]["timeout_seconds"]),
        sheet_tab_name=data["sheet"]["tab_name"],
        source_retry_attempts=int(data["request"].get("retry_attempts", 2)),
        sheet_id_env_var=data["sheet"].get("sheet_id_env_var", "GOOGLE_SHEET_ID"),
        role_families=[item.lower() for item in role_families.get("include", role_include)],
        new_grad_positive_terms=[
            item.lower() for item in new_grad_rules.get("positive_terms", DEFAULT_NEW_GRAD_POSITIVE)
        ],
        seniority_negative_terms=[
            item.lower() for item in new_grad_rules.get("seniority_negative_terms", DEFAULT_SENIORITY_NEGATIVE)
        ],
        internship_terms=[item.lower() for item in new_grad_rules.get("internship_terms", DEFAULT_INTERNSHIP_TERMS)],
        rotational_terms=[item.lower() for item in new_grad_rules.get("rotational_terms", DEFAULT_ROTATIONAL_TERMS)],
        max_experience_years=int(new_grad_rules.get("max_experience_years", 2)),
        high_precision_new_grad=bool(new_grad_rules.get("high_precision", True)),
        location_mode=str(location_rules.get("mode", "metros")),
        allow_remote_us=bool(location_rules.get("allow_remote_us", False)),
        us_location_terms=[item.lower() for item in location_rules.get("us_terms", DEFAULT_US_LOCATION_TERMS)],
        non_us_location_terms=[
            item.lower() for item in location_rules.get("non_us_terms", DEFAULT_NON_US_LOCATION_TERMS)
        ],
    )


def load_companies(companies_path: str | None = None) -> list[CompanyConfig]:
    """Load company configurations from TOML."""

    path = Path(companies_path or os.environ.get("JOB_WATCH_COMPANIES_PATH", DEFAULT_COMPANIES_PATH))
    data = _load_toml(path)
    companies: list[CompanyConfig] = []
    for entry in data["company"]:
        companies.append(
            CompanyConfig(
                slug=entry["slug"],
                name=entry["name"],
                category=entry["category"],
                ats_kind=entry["ats_kind"],
                career_url=entry["career_url"],
                enabled=bool(entry.get("enabled", True)),
                board_token=entry.get("board_token"),
                site=entry.get("site"),
                company_identifier=entry.get("company_identifier"),
                feed_url=entry.get("feed_url"),
                listing_url=entry.get("listing_url"),
                tenant_hint=entry.get("tenant_hint"),
                requires_browser=bool(entry.get("requires_browser", False)),
                request_options=dict(entry.get("request_options", {})),
                headers=dict(entry.get("headers", {})),
                official_career_site_url=entry.get("official_career_site_url") or entry["career_url"],
                source_policy=entry.get("source_policy")
                or ("ats_redirect" if entry["ats_kind"] in ATS_REDIRECT_KINDS else "company_site"),
            )
        )
    return companies


def resolve_sheet_id(settings: AppSettings, override: str | None = None) -> str:
    """Resolve the Google Sheet ID from CLI or environment."""

    sheet_id = override or os.environ.get(settings.sheet_id_env_var)
    if not sheet_id:
        raise ValueError(
            f"Google Sheet ID is required. Pass --sheet-id or set {settings.sheet_id_env_var}."
        )
    return sheet_id


def _load_toml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as handle:
        return tomllib.load(handle)
