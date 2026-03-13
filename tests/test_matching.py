from datetime import UTC, datetime

from job_watch.config import load_settings
from job_watch.matching import apply_matching, matches_role
from job_watch.models import JobRecord


def _record(title: str, location: str, posted_at: datetime | None = None) -> JobRecord:
    return JobRecord(
        job_key="abc",
        company_slug="asana",
        company_name="Asana",
        ats_kind="greenhouse",
        source_job_id="1",
        title=title,
        team="",
        department="",
        location_raw=location,
        location_normalized=location,
        posted_at=posted_at,
        updated_at=posted_at,
        apply_url="https://example.com/job",
        career_page_url="https://example.com/careers",
        employment_type="Full-time",
        remote_flag=False,
        description_text="",
    )


def test_role_matching_is_strict():
    settings = load_settings()
    assert matches_role("Senior Project Manager", settings) is True
    assert matches_role("Business Analyst", settings) is True
    assert matches_role("Program Manager", settings) is False
    assert matches_role("Business Systems Analyst", settings) is False


def test_location_and_freshness_matching():
    settings = load_settings()
    record = _record(
        "Business Analyst",
        "McLean, VA",
        posted_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
    )
    apply_matching(record, settings)
    assert record.match_location is True
    assert record.matched_metro == "northern_virginia"
    assert record.freshness_status == "fresh"


def test_remote_only_is_not_a_match():
    settings = load_settings()
    record = _record("Project Manager", "Remote - United States")
    apply_matching(record, settings)
    assert record.match_location is False
