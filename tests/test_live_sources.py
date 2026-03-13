import asyncio
import os

import pytest

from job_watch.config import load_companies, load_settings
from job_watch.service import JobWatchService

ENABLED_COMPANIES = [company for company in load_companies() if company.enabled]


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

    assert result.error is None, result.error
    assert result.jobs, f"{company.slug} returned no jobs"

    sample = result.jobs[0]
    assert sample.company_slug == company.slug
    assert sample.company_name == company.name
    assert sample.title
    assert sample.apply_url
