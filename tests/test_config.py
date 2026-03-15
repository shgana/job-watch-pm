from pathlib import Path

from job_watch.config import load_companies, load_settings


def test_load_companies_parses_first_party_fields(tmp_path: Path):
    companies_toml = tmp_path / "companies.toml"
    companies_toml.write_text(
        """
[[company]]
slug = "example"
name = "Example"
category = "tech"
ats_kind = "google_jobs_browser"
career_url = "https://example.com/careers"
listing_url = "https://example.com/careers/search?q=project%20manager"
enabled = true
requires_browser = true

[company.request_options]
query = "project manager"
max_pages = 2
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    companies = load_companies(str(companies_toml))

    assert len(companies) == 1
    company = companies[0]
    assert company.listing_url == "https://example.com/careers/search?q=project%20manager"
    assert company.requires_browser is True
    assert company.request_options["query"] == "project manager"
    assert company.request_options["max_pages"] == 2
    assert company.official_career_site_url == "https://example.com/careers"
    assert company.source_policy == "company_site"


def test_load_settings_parses_new_grad_and_location_rules(tmp_path: Path):
    settings_toml = tmp_path / "settings.toml"
    settings_toml.write_text(
        """
[metros]
seattle = ["Seattle"]

[role_rules]
include = ["Business Analyst"]
exclude = ["Project Coordinator"]

[role_families]
include = ["business analyst", "product manager"]

[new_grad_rules]
positive_terms = ["new grad", "entry level"]
seniority_negative_terms = ["senior", "staff"]
internship_terms = ["intern"]
rotational_terms = ["rotation program"]
max_experience_years = 2
high_precision = true

[location_rules]
mode = "us_or_remote"
allow_remote_us = true
us_terms = ["united states", "usa"]
non_us_terms = ["canada"]

[scan]
freshness_days = 7

[request]
concurrency = 4
timeout_seconds = 10

[sheet]
tab_name = "Jobs"
sheet_id_env_var = "GOOGLE_SHEET_ID"
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    settings = load_settings(str(settings_toml))
    assert settings.role_families == ["business analyst", "product manager"]
    assert settings.new_grad_positive_terms == ["new grad", "entry level"]
    assert settings.seniority_negative_terms == ["senior", "staff"]
    assert settings.internship_terms == ["intern"]
    assert settings.location_mode == "us_or_remote"
    assert settings.allow_remote_us is True
    assert settings.source_retry_attempts == 2
