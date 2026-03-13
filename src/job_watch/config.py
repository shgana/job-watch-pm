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


def load_settings(settings_path: str | None = None) -> AppSettings:
    """Load application settings from TOML."""

    path = Path(settings_path or os.environ.get("JOB_WATCH_SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
    data = _load_toml(path)
    return AppSettings(
        metros={key: [alias.lower() for alias in value] for key, value in data["metros"].items()},
        role_include=[item.lower() for item in data["role_rules"]["include"]],
        role_exclude=[item.lower() for item in data["role_rules"]["exclude"]],
        freshness_days=int(data["scan"]["freshness_days"]),
        concurrency=int(data["request"]["concurrency"]),
        timeout_seconds=float(data["request"]["timeout_seconds"]),
        sheet_tab_name=data["sheet"]["tab_name"],
        sheet_id_env_var=data["sheet"].get("sheet_id_env_var", "GOOGLE_SHEET_ID"),
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
                tenant_hint=entry.get("tenant_hint"),
                headers=dict(entry.get("headers", {})),
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
