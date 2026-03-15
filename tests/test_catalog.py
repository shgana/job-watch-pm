from job_watch.config import load_companies
from job_watch.constants import FAANG_PLUS_TARGET_SLUGS
from job_watch.registry import ADAPTERS


def test_enabled_catalog_has_expected_scale():
    enabled = [company for company in load_companies() if company.enabled]

    assert len(enabled) >= 240


def test_enabled_catalog_entries_are_unique_and_complete():
    enabled = [company for company in load_companies() if company.enabled]
    seen_slugs: set[str] = set()

    for company in enabled:
        assert company.slug not in seen_slugs
        seen_slugs.add(company.slug)
        assert company.ats_kind in ADAPTERS
        assert company.career_url
        assert company.official_career_site_url
        assert company.source_policy in {"company_site", "ats_redirect"}

        if company.ats_kind in {"greenhouse", "ashby"}:
            assert company.board_token
        elif company.ats_kind == "lever":
            assert company.site
        elif company.ats_kind == "smartrecruiters":
            assert company.company_identifier
        elif company.ats_kind == "workday":
            assert company.feed_url
        elif company.ats_kind in {"amazon_jobs", "adobe_jobs", "linkedin_jobs", "netflix_jobs", "salesforce_jobs", "apple_jobs"}:
            assert company.listing_url
        elif company.ats_kind in {"microsoft_jobs", "tiktok_jobs", "uber_jobs"}:
            assert company.listing_url
            assert company.request_options
        elif company.ats_kind in {
            "google_jobs_browser",
            "meta_jobs_browser",
            "bytedance_jobs_browser",
            "tesla_jobs_browser",
        }:
            assert company.listing_url
            assert company.requires_browser


def test_faang_plus_target_slugs_are_present_and_enabled():
    companies = load_companies()
    company_map = {company.slug: company for company in companies}
    missing = [slug for slug in FAANG_PLUS_TARGET_SLUGS if slug not in company_map]
    assert missing == []

    intentionally_disabled = {"tesla"}
    disabled = [
        slug for slug in FAANG_PLUS_TARGET_SLUGS if slug not in intentionally_disabled and not company_map[slug].enabled
    ]
    assert disabled == []
    for slug in FAANG_PLUS_TARGET_SLUGS:
        assert company_map[slug].source_policy in {"company_site", "ats_redirect"}
        assert company_map[slug].official_career_site_url


def test_enabled_catalog_excludes_best_effort_sources():
    enabled = [company for company in load_companies() if company.enabled]
    best_effort_enabled = [
        company.slug for company in enabled if bool((company.request_options or {}).get("best_effort", False))
    ]
    assert best_effort_enabled == []
