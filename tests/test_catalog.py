from job_watch.config import load_companies
from job_watch.registry import ADAPTERS


def test_enabled_catalog_has_expected_scale():
    enabled = [company for company in load_companies() if company.enabled]

    assert len(enabled) >= 150


def test_enabled_catalog_entries_are_unique_and_complete():
    enabled = [company for company in load_companies() if company.enabled]
    seen_slugs: set[str] = set()

    for company in enabled:
        assert company.slug not in seen_slugs
        seen_slugs.add(company.slug)
        assert company.ats_kind in ADAPTERS
        assert company.career_url

        if company.ats_kind in {"greenhouse", "ashby"}:
            assert company.board_token
        elif company.ats_kind == "lever":
            assert company.site
        elif company.ats_kind == "smartrecruiters":
            assert company.company_identifier
        elif company.ats_kind == "workday":
            assert company.feed_url
