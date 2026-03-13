import asyncio
from datetime import UTC, datetime
from pathlib import Path

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


def _settings() -> AppSettings:
    return AppSettings(
        metros={
            "seattle": ["seattle"],
            "northern_virginia": ["mclean", "reston"],
        },
        role_include=["business analyst", "project manager"],
        role_exclude=["program manager", "product manager"],
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
