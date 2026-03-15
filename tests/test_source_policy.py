from job_watch.models import CompanyConfig
from job_watch.source_policy import (
    looks_like_direct_apply_url,
    validate_company_source_policy,
)


def _company(**kwargs) -> CompanyConfig:
    base = CompanyConfig(
        slug="example",
        name="Example",
        category="tech",
        ats_kind="greenhouse",
        career_url="https://boards.greenhouse.io/example",
        board_token="example",
        official_career_site_url="https://example.com/careers",
        source_policy="ats_redirect",
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_validate_company_policy_accepts_ats_redirect():
    company = _company()
    assert validate_company_source_policy(company) == []


def test_validate_company_policy_rejects_aggregators():
    company = _company(career_url="https://www.indeed.com/jobs?q=example")
    errors = validate_company_source_policy(company)
    assert errors
    assert "disallowed aggregator source url" in errors[0]


def test_validate_company_policy_rejects_company_site_domain_mismatch():
    company = _company(
        source_policy="company_site",
        career_url="https://boards.greenhouse.io/example",
    )
    errors = validate_company_source_policy(company)
    assert errors
    assert "company_site source must stay on company domain" in errors[0]


def test_direct_apply_url_detector():
    assert looks_like_direct_apply_url("https://example.com/apply/123") is True
    assert looks_like_direct_apply_url("https://example.com/jobs/123") is False
