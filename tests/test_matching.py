from datetime import UTC, datetime

from job_watch.config import load_settings
from job_watch.matching import apply_matching, classify_new_grad, matches_role
from job_watch.models import JobRecord


def _record(
    title: str,
    location: str,
    posted_at: datetime | None = None,
    description: str = "",
    employment_type: str = "Full-time",
) -> JobRecord:
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
        employment_type=employment_type,
        remote_flag=False,
        description_text=description,
    )


def test_role_family_matching_includes_product_and_program():
    settings = load_settings()
    assert matches_role("Business Analyst", settings) is True
    assert matches_role("Associate Product Manager", settings) is True
    assert matches_role("Technical Program Manager", settings) is True
    assert matches_role("Business Systems Analyst", settings) is False


def test_new_grad_classifier_requires_positive_signal_under_high_precision():
    settings = load_settings()
    matched, reason = classify_new_grad(
        _record(
            "Associate Product Manager",
            "San Francisco, CA",
            description="Entry level role for recent graduates. 0-2 years experience.",
        ),
        settings,
    )
    assert matched is True
    assert reason == "matched_new_grad"

    rejected, reject_reason = classify_new_grad(
        _record(
            "Product Manager",
            "San Francisco, CA",
            description="Requires 5+ years of product management experience.",
        ),
        settings,
    )
    assert rejected is False
    assert reject_reason == "experience_too_high"


def test_location_and_freshness_matching_for_us_mode():
    settings = load_settings()
    record = _record(
        "Business Analyst",
        "McLean, VA",
        posted_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        description="Recent graduate program, 0-2 years experience.",
    )
    apply_matching(record, settings)
    assert record.match_location is True
    assert record.matched_metro == "us"
    assert record.freshness_status == "fresh"
    assert record.match_role is True


def test_remote_us_is_a_match_and_non_us_is_rejected():
    settings = load_settings()
    us_remote = _record(
        "Program Manager",
        "Remote - United States",
        description="Early career rotational program for new graduates.",
    )
    apply_matching(us_remote, settings)
    assert us_remote.match_location is True
    assert us_remote.matched_metro == "us_remote"

    non_us = _record(
        "Program Manager",
        "Toronto, Canada",
        description="Entry level role for recent graduates.",
    )
    apply_matching(non_us, settings)
    assert non_us.match_location is False
