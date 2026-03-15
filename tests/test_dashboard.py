from job_watch.dashboard import render_status_dashboard


def test_render_status_dashboard_counts_and_labels():
    html = render_status_dashboard(
        [
            {"company_slug": "openai", "ats_kind": "ashby", "jobs_found": 3, "status": "green", "reason": "ok", "error": None},
            {"company_slug": "broken", "ats_kind": "workday", "jobs_found": 0, "status": "red", "reason": "fetch_failed", "error": "boom"},
        ]
    )
    assert "Total Companies: 2" in html
    assert "Green: 1" in html
    assert "Red: 1" in html
    assert "Reason" in html
    assert "fetch_failed" in html
    assert "openai" in html
    assert "broken" in html
