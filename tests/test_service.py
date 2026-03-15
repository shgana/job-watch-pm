import asyncio
from datetime import UTC, datetime
from pathlib import Path

from job_watch.constants import FAANG_PLUS_TARGET_SLUGS
from job_watch.models import AppSettings, CompanyConfig, JobRecord
from job_watch.service import JobWatchService
from job_watch.sheets import SheetTracker


class MemoryGateway:
    def __init__(self, rows=None):
        self._rows = [row.copy() for row in (rows or [])]

    def read_rows(self):
        return [row.copy() for row in self._rows]

    def write_rows(self, rows):
        self._rows = [row.copy() for row in rows]


class StaticAdapter:
    def __init__(self, jobs):
        self.jobs = jobs

    async def fetch(self, client, company):
        return [job for job in self.jobs]


class SequenceAdapter:
    def __init__(self, sequences):
        self.sequences = list(sequences)
        self.index = 0

    async def fetch(self, client, company):
        if self.index >= len(self.sequences):
            jobs = self.sequences[-1]
        else:
            jobs = self.sequences[self.index]
            self.index += 1
        return [job for job in jobs]


class FailingAdapter:
    async def fetch(self, client, company):
        raise RuntimeError("boom")


class FailOnceAdapter:
    def __init__(self, jobs):
        self.jobs = jobs
        self.calls = 0

    async def fetch(self, client, company):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        return [job for job in self.jobs]


def _settings() -> AppSettings:
    return AppSettings(
        metros={
            "seattle": ["seattle"],
            "northern_virginia": ["mclean", "reston"],
        },
        role_include=["business analyst", "project manager"],
        role_exclude=["program manager", "product manager"],
        role_families=["business analyst", "project manager"],
        high_precision_new_grad=False,
        freshness_days=7,
        concurrency=4,
        timeout_seconds=5,
        sheet_tab_name="Jobs",
    )


def _job(key: str, title: str, location: str, posted_at: datetime | None) -> JobRecord:
    return JobRecord(
        job_key=key,
        company_slug="openai",
        company_name="OpenAI",
        ats_kind="ashby",
        source_job_id=key,
        title=title,
        team="",
        department="",
        location_raw=location,
        location_normalized=location,
        posted_at=posted_at,
        updated_at=posted_at,
        apply_url=f"https://example.com/{key}",
        career_page_url="https://example.com/careers",
        employment_type="Full-time",
        remote_flag=False,
        description_text="",
    )


def test_scan_dedupes_and_filters_stale_rows(tmp_path: Path):
    company = CompanyConfig(
        slug="openai",
        name="OpenAI",
        category="ai",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/openai",
    )
    companies = [
        company,
        CompanyConfig(
            slug="broken",
            name="Broken",
            category="saas",
            ats_kind="workday",
            career_url="https://example.com",
        ),
    ]
    adapters = {
        "ashby": StaticAdapter(
            [
                _job("fresh-1", "Project Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC)),
                _job("stale-1", "Business Analyst", "McLean, VA", datetime(2026, 2, 20, tzinfo=UTC)),
                _job("bad-1", "Product Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC)),
            ]
        ),
        "workday": FailingAdapter(),
    }
    tracker = SheetTracker(MemoryGateway())
    service = JobWatchService(settings=_settings(), companies=companies, adapters=adapters)

    first = asyncio.run(service.scan(sheet_id=None, tracker=tracker))
    second = asyncio.run(service.scan(sheet_id=None, tracker=tracker))

    assert first.matched_jobs == 2
    assert first.new_rows == 2
    assert first.new_alerts == 1
    assert len(first.failures) == 1
    assert second.new_rows == 0
    assert second.updated_rows == 2
    assert second.new_alerts == 0


def test_scan_marks_missing_rows_stale_and_recovers():
    company = CompanyConfig(
        slug="openai",
        name="OpenAI",
        category="ai",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/openai",
    )
    trackers = SheetTracker(MemoryGateway())
    adapters = {
        "ashby": SequenceAdapter(
            [
                [_job("fresh-1", "Project Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC))],
                [],
                [_job("fresh-1", "Project Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC))],
            ]
        )
    }
    service = JobWatchService(settings=_settings(), companies=[company], adapters=adapters)

    asyncio.run(service.scan(sheet_id=None, tracker=trackers))
    rows = {row["job_key"]: row for row in trackers.rows()}
    assert rows["fresh-1"]["status"] == "new"
    assert rows["fresh-1"]["metro"] == "seattle"
    assert rows["fresh-1"]["freshness_status"] == "fresh"

    asyncio.run(service.scan(sheet_id=None, tracker=trackers))
    rows = {row["job_key"]: row for row in trackers.rows()}
    assert rows["fresh-1"]["status"] == "stale"

    asyncio.run(service.scan(sheet_id=None, tracker=trackers))
    rows = {row["job_key"]: row for row in trackers.rows()}
    assert rows["fresh-1"]["status"] == "tracked"


def test_export_rows_writes_csv(tmp_path: Path):
    gateway = MemoryGateway(
        rows=[
            {
                "job_key": "abc",
                "status": "new",
                "company": "OpenAI",
                "title": "Project Manager",
                "location": "Seattle, WA",
                "metro": "seattle",
                "freshness_status": "fresh",
                "posted_at": "2026-03-12T00:00:00Z",
                "discovered_at": "2026-03-12T00:00:00Z",
                "apply_url": "https://example.com/job",
                "career_page_url": "https://example.com/careers",
                "source": "ashby",
                "notes": "",
                "manual_priority": "",
                "last_seen_at": "2026-03-12T00:00:00Z",
            }
        ]
    )
    service = JobWatchService(settings=_settings(), companies=[])
    output = tmp_path / "jobs.csv"
    count = service.export_rows(
        sheet_id=None,
        status="new",
        output_format="csv",
        output_path=output,
        tracker=SheetTracker(gateway),
    )
    assert count == 1
    assert "OpenAI" in output.read_text(encoding="utf-8")
    assert "metro" in output.read_text(encoding="utf-8")


def test_scan_payload_includes_company_results():
    company = CompanyConfig(
        slug="openai",
        name="OpenAI",
        category="ai",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/openai",
    )
    adapters = {
        "ashby": StaticAdapter(
            [_job("fresh-1", "Project Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC))]
        )
    }
    tracker = SheetTracker(MemoryGateway())
    service = JobWatchService(settings=_settings(), companies=[company], adapters=adapters)

    summary = asyncio.run(service.scan(sheet_id=None, tracker=tracker))
    payload = service.scan_payload(summary)

    assert payload["new_rows"] == 1
    assert payload["company_results"][0]["company_slug"] == "openai"
    assert payload["company_results"][0]["inserted_rows"] == 1
    assert payload["company_results"][0]["error"] is None


def test_cleanup_non_new_grad_rows_archives_out_of_scope_rows():
    gateway = MemoryGateway(
        rows=[
            {
                "job_key": "1",
                "status": "new",
                "company": "OpenAI",
                "title": "Senior Product Manager",
                "location": "Seattle, WA",
                "metro": "",
                "freshness_status": "fresh",
                "posted_at": "",
                "discovered_at": "",
                "apply_url": "https://example.com/jobs/1",
                "career_page_url": "https://example.com/careers",
                "source": "ashby",
                "notes": "",
                "manual_priority": "",
                "last_seen_at": "",
            },
            {
                "job_key": "2",
                "status": "applied",
                "company": "OpenAI",
                "title": "Product Manager",
                "location": "Seattle, WA",
                "metro": "",
                "freshness_status": "fresh",
                "posted_at": "",
                "discovered_at": "",
                "apply_url": "https://example.com/jobs/2",
                "career_page_url": "https://example.com/careers",
                "source": "ashby",
                "notes": "",
                "manual_priority": "",
                "last_seen_at": "",
            },
        ]
    )
    service = JobWatchService(settings=_settings(), companies=[])
    summary = service.cleanup_non_new_grad_rows(sheet_id=None, tracker=SheetTracker(gateway))
    rows = {row["job_key"]: row for row in gateway.read_rows()}
    assert summary.archived_rows == 1
    assert summary.skipped_terminal_rows == 1
    assert rows["1"]["status"] == "archived"
    assert rows["2"]["status"] == "applied"


def test_scan_normalizes_direct_apply_urls():
    company = CompanyConfig(
        slug="example",
        name="Example",
        category="saas",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/example",
    )
    direct_apply_job = JobRecord(
        job_key="x1",
        company_slug="example",
        company_name="Example",
        ats_kind="ashby",
        source_job_id="x1",
        title="Business Analyst",
        team="",
        department="",
        location_raw="Seattle, WA",
        location_normalized="Seattle, WA",
        posted_at=datetime(2026, 3, 12, tzinfo=UTC),
        updated_at=datetime(2026, 3, 12, tzinfo=UTC),
        apply_url="https://example.com/apply/123",
        career_page_url="https://example.com/jobs/123",
        employment_type="Full-time",
        remote_flag=False,
        description_text="Entry level role for recent graduates.",
    )
    adapters = {"ashby": StaticAdapter([direct_apply_job])}
    tracker = SheetTracker(MemoryGateway())
    service = JobWatchService(settings=_settings(), companies=[company], adapters=adapters)

    asyncio.run(service.scan(sheet_id=None, tracker=tracker))
    rows = tracker.rows()
    assert rows[0]["apply_url"] == "https://example.com/jobs/123"


def test_scan_retries_transient_fetch_failures():
    company = CompanyConfig(
        slug="openai",
        name="OpenAI",
        category="ai",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/openai",
    )
    adapter = FailOnceAdapter(
        [_job("fresh-1", "Project Manager", "Seattle, WA", datetime(2026, 3, 12, tzinfo=UTC))]
    )
    service = JobWatchService(settings=_settings(), companies=[company], adapters={"ashby": adapter})
    summary = asyncio.run(service.scan(sheet_id=None, tracker=SheetTracker(MemoryGateway())))
    assert summary.failures == []
    assert summary.new_rows == 1
    assert adapter.calls == 2


def test_faang_plus_status_includes_missing_and_green_rows():
    company = CompanyConfig(
        slug="openai",
        name="OpenAI",
        category="ai",
        ats_kind="ashby",
        career_url="https://jobs.ashbyhq.com/openai",
        enabled=True,
        board_token="openai",
        official_career_site_url="https://openai.com/careers/",
        source_policy="ats_redirect",
    )
    service = JobWatchService(settings=_settings(), companies=[company], adapters={"ashby": StaticAdapter([])})

    results = asyncio.run(
        service.faang_plus_status(
            scan_company_results=[
                {"company_slug": "openai", "ats_kind": "ashby", "fetched_jobs": 7, "error": None}
            ]
        )
    )
    assert len(results) == len(FAANG_PLUS_TARGET_SLUGS)
    by_slug = {item.company_slug: item for item in results}
    assert by_slug["openai"].status == "green"
    assert by_slug["openai"].reason == "ok"
    assert by_slug["openai"].jobs_found == 7
    assert by_slug["google"].status == "red"
    assert by_slug["google"].reason == "missing_in_catalog"


def test_faang_plus_status_surfaces_disabled_adapter_and_policy_reasons():
    companies = [
        CompanyConfig(
            slug="google",
            name="Google",
            category="tech",
            ats_kind="google_jobs_browser",
            career_url="https://www.google.com/about/careers/",
            enabled=False,
            listing_url="https://www.google.com/about/careers/",
            official_career_site_url="https://www.google.com/about/careers/",
            source_policy="company_site",
        ),
        CompanyConfig(
            slug="microsoft",
            name="Microsoft",
            category="tech",
            ats_kind="unknown_source",
            career_url="https://careers.microsoft.com/",
            enabled=True,
            listing_url="https://careers.microsoft.com/",
            official_career_site_url="https://careers.microsoft.com/",
            source_policy="company_site",
        ),
        CompanyConfig(
            slug="amazon",
            name="Amazon",
            category="tech",
            ats_kind="amazon_jobs",
            career_url="https://boards.greenhouse.io/amazon",
            enabled=True,
            listing_url="https://boards.greenhouse.io/amazon",
            official_career_site_url="https://amazon.jobs/en/",
            source_policy="company_site",
        ),
    ]
    adapters = {"amazon_jobs": StaticAdapter([])}
    service = JobWatchService(settings=_settings(), companies=companies, adapters=adapters)

    results = asyncio.run(service.faang_plus_status())
    by_slug = {item.company_slug: item for item in results}
    assert by_slug["google"].reason == "disabled_in_catalog"
    assert by_slug["microsoft"].reason == "adapter_not_registered"
    assert by_slug["amazon"].reason == "policy_failed"
    assert by_slug["amazon"].status == "red"

    payload = service.faang_plus_status_payload(results)
    assert payload["total_companies"] == len(FAANG_PLUS_TARGET_SLUGS)
    assert payload["red"] >= 3
