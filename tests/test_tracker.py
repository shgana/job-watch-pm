from datetime import UTC, datetime

from job_watch.models import JobRecord
from job_watch.sheets import SheetTracker


class MemoryGateway:
    def __init__(self, rows=None):
        self._rows = [row.copy() for row in (rows or [])]

    def read_rows(self):
        return [row.copy() for row in self._rows]

    def write_rows(self, rows):
        self._rows = [row.copy() for row in rows]


def _record(job_key: str, title: str) -> JobRecord:
    return JobRecord(
        job_key=job_key,
        company_slug="asana",
        company_name="Asana",
        ats_kind="greenhouse",
        source_job_id=job_key,
        title=title,
        team="",
        department="",
        location_raw="Seattle, WA",
        location_normalized="Seattle, WA",
        posted_at=datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
        apply_url=f"https://example.com/{job_key}",
        career_page_url="https://example.com/careers",
        employment_type="Full-time",
        remote_flag=False,
        description_text="",
        freshness_status="fresh",
    )


def test_tracker_preserves_manual_columns():
    gateway = MemoryGateway(
        rows=[
            {
                "job_key": "job-1",
                "status": "applied",
                "company": "Asana",
                "title": "Old Title",
                "location": "Seattle, WA",
                "metro": "seattle",
                "freshness_status": "fresh",
                "posted_at": "",
                "discovered_at": "2026-03-10T00:00:00Z",
                "apply_url": "https://example.com/job-1",
                "career_page_url": "https://example.com/careers",
                "source": "greenhouse",
                "notes": "resume sent",
                "manual_priority": "high",
                "last_seen_at": "2026-03-10T00:00:00Z",
            }
        ]
    )
    tracker = SheetTracker(gateway)
    result = tracker.sync([_record("job-1", "Senior Project Manager"), _record("job-2", "Business Analyst")])

    rows = {row["job_key"]: row for row in gateway.read_rows()}
    assert rows["job-1"]["status"] == "applied"
    assert rows["job-1"]["notes"] == "resume sent"
    assert rows["job-2"]["status"] == "new"
    assert rows["job-2"]["metro"] == ""
    assert rows["job-2"]["freshness_status"] == "fresh"
    assert result.inserted_keys == {"job-2"}
    assert result.updated_keys == {"job-1"}
