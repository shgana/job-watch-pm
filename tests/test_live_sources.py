import asyncio
import os

import pytest

from job_watch.config import load_companies, load_settings
from job_watch.constants import FAANG_PLUS_TARGET_SLUGS
from job_watch.service import JobWatchService

ENABLED_COMPANIES = [company for company in load_companies() if company.enabled]
ENABLED_COMPANY_MAP = {company.slug: company for company in ENABLED_COMPANIES}
FAANG_PLUS_ENABLED = [ENABLED_COMPANY_MAP[slug] for slug in FAANG_PLUS_TARGET_SLUGS if slug in ENABLED_COMPANY_MAP]


@pytest.fixture(scope="session")
def live_fetch_results():
    if os.environ.get("JOB_WATCH_RUN_LIVE_TESTS") != "1":
        pytest.skip("set JOB_WATCH_RUN_LIVE_TESTS=1 to run live source validation")

    settings = load_settings()
    settings.concurrency = max(settings.concurrency, 16)
    service = JobWatchService(settings=settings, companies=ENABLED_COMPANIES)
    results = asyncio.run(service.fetch_sources())
    return {result.company.slug: result for result in results}


@pytest.mark.live
@pytest.mark.parametrize("company", ENABLED_COMPANIES, ids=lambda company: company.slug)
def test_enabled_company_source_is_live(company, live_fetch_results):
    result = live_fetch_results[company.slug]
    if company.request_options.get("best_effort") and (result.error or not result.jobs):
        pytest.xfail(f"{company.slug} best-effort source returned unstable result: {result.error}")

    assert result.error is None, result.error
    assert result.jobs, f"{company.slug} returned no jobs"

    sample = result.jobs[0]
    assert sample.company_slug == company.slug
    assert sample.company_name == company.name
    assert sample.title
    assert sample.apply_url


@pytest.mark.live
@pytest.mark.parametrize("company", FAANG_PLUS_ENABLED, ids=lambda company: company.slug)
def test_faang_plus_company_source_is_live(company, live_fetch_results):
    result = live_fetch_results[company.slug]
    if company.request_options.get("best_effort") and (result.error or not result.jobs):
        pytest.xfail(f"{company.slug} best-effort source returned unstable result: {result.error}")

    assert result.error is None, result.error
    assert result.jobs, f"{company.slug} returned no jobs"

    sample = result.jobs[0]
    assert sample.company_slug == company.slug
    assert sample.company_name == company.name
