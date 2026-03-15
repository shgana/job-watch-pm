import json
from pathlib import Path

from typer.testing import CliRunner

from job_watch.cli import app
from job_watch.models import CleanupSummary
from job_watch.models import ScanSummary, SourceCheckResult

runner = CliRunner()


class DummyService:
    def __init__(self, *args, **kwargs):
        pass

    async def sources_check(self, company_slug=None):
        return [
            SourceCheckResult(
                company_slug="openai",
                company_name="OpenAI",
                ats_kind="ashby",
                ok=True,
                jobs_found=3,
                error=None,
            ),
            SourceCheckResult(
                company_slug="broken",
                company_name="Broken",
                ats_kind="workday",
                ok=False,
                jobs_found=0,
                error="boom",
            ),
        ]

    @staticmethod
    def source_check_payload(results):
        return [
            {
                "company_slug": item.company_slug,
                "company_name": item.company_name,
                "ats_kind": item.ats_kind,
                "ok": item.ok,
                "jobs_found": item.jobs_found,
                "error": item.error,
            }
            for item in results
        ]


class DummyScanService:
    def __init__(self, *args, **kwargs):
        pass

    async def scan(self, *args, **kwargs):
        return ScanSummary(
            scanned_companies=1,
            fetched_jobs=5,
            matched_jobs=2,
            new_rows=1,
            new_alerts=1,
            updated_rows=0,
            failures=["tesla: blocked"],
            alert_rows=[
                {
                    "company": "Example",
                    "title": "Project Manager",
                    "location": "Seattle, WA",
                    "apply_url": "https://example.com/jobs/1",
                }
            ],
            company_results=[
                {
                    "company_slug": "example",
                    "company_name": "Example",
                    "ats_kind": "example_jobs",
                    "fetched_jobs": 5,
                    "matched_jobs": 2,
                    "inserted_rows": 1,
                    "updated_rows": 0,
                    "error": None,
                }
            ],
        )

    @staticmethod
    def scan_payload(summary):
        return {
            "scanned_companies": summary.scanned_companies,
            "fetched_jobs": summary.fetched_jobs,
            "matched_jobs": summary.matched_jobs,
            "new_rows": summary.new_rows,
            "new_alerts": summary.new_alerts,
            "updated_rows": summary.updated_rows,
            "failures": summary.failures,
            "company_results": summary.company_results,
        }


class DummyGateway:
    called = False

    def __init__(self, sheet_id, worksheet_name):
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name

    def ensure_template(self):
        DummyGateway.called = True


class DummyPolicyService:
    def __init__(self, *args, **kwargs):
        pass

    def validate_catalog_sources(self):
        return [{"company_slug": "broken", "error": "disallowed aggregator source url"}]


class DummyCleanupService:
    def __init__(self, *args, **kwargs):
        pass

    def cleanup_non_new_grad_rows(self, *args, **kwargs):
        return CleanupSummary(
            scanned_rows=10,
            archived_rows=3,
            skipped_terminal_rows=2,
            report_rows=[{"job_key": "abc", "reason": "missing_early_career_signal"}],
        )


class DummyFaangService:
    def __init__(self, *args, **kwargs):
        pass

    async def faang_plus_status(self, *args, **kwargs):
        return [
            {
                "company_slug": "openai",
                "company_name": "OpenAI",
                "ats_kind": "ashby",
                "enabled": True,
                "jobs_found": 4,
                "status": "green",
                "reason": "ok",
                "error": None,
            },
            {
                "company_slug": "google",
                "company_name": "Google",
                "ats_kind": "google_jobs_browser",
                "enabled": True,
                "jobs_found": 0,
                "status": "red",
                "reason": "fetch_failed",
                "error": "timeout",
            },
        ]

    @staticmethod
    def faang_plus_status_payload(results):
        green = sum(1 for item in results if item.get("status") == "green")
        return {
            "target_slugs": ["openai", "google"],
            "total_companies": len(results),
            "green": green,
            "red": len(results) - green,
            "results": results,
        }


def test_sources_check_json_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyService)

    output = tmp_path / "sources.json"
    result = runner.invoke(app, ["sources-check", "--format", "json", "--output", str(output)])

    assert result.exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["company_slug"] == "openai"
    assert payload[1]["ats_kind"] == "workday"


def test_sources_check_table_output(monkeypatch):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyService)

    result = runner.invoke(app, ["sources-check"])

    assert result.exit_code == 1
    assert "openai" in result.stdout
    assert "ashby" in result.stdout


def test_scan_json_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyScanService)

    output = tmp_path / "scan.json"
    result = runner.invoke(app, ["scan", "--format", "json", "--output", str(output)])

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["scanned_companies"] == 1
    assert payload["company_results"][0]["company_slug"] == "example"


def test_sheet_template_command(monkeypatch):
    DummyGateway.called = False
    monkeypatch.setattr(
        "job_watch.cli.load_settings",
        lambda *args, **kwargs: type("S", (), {"sheet_tab_name": "Jobs", "sheet_id_env_var": "GOOGLE_SHEET_ID"})(),
    )
    monkeypatch.setattr("job_watch.cli.resolve_sheet_id", lambda settings, sheet_id: "sheet-123")
    monkeypatch.setattr("job_watch.cli.GoogleSheetGateway", DummyGateway)

    result = runner.invoke(app, ["sheet-template"])

    assert result.exit_code == 0
    assert DummyGateway.called is True
    assert "Sheet template is ready" in result.stdout


def test_policy_check_json_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyPolicyService)

    output = tmp_path / "policy.json"
    result = runner.invoke(app, ["policy-check", "--format", "json", "--output", str(output)])

    assert result.exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["company_slug"] == "broken"


def test_cleanup_non_new_grad_command(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyCleanupService)

    output = tmp_path / "cleanup.json"
    result = runner.invoke(app, ["cleanup-non-new-grad", "--output", str(output)])

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["job_key"] == "abc"
    assert "archived 3" in result.stdout


def test_status_dashboard_from_scan_report(tmp_path: Path):
    scan_payload = {
        "company_results": [
            {
                "company_slug": "openai",
                "ats_kind": "ashby",
                "fetched_jobs": 10,
                "error": None,
            },
            {
                "company_slug": "broken",
                "ats_kind": "workday",
                "fetched_jobs": 0,
                "error": "timeout",
            },
        ]
    }
    scan_file = tmp_path / "scan.json"
    scan_file.write_text(json.dumps(scan_payload), encoding="utf-8")
    output = tmp_path / "dashboard.html"

    result = runner.invoke(app, ["status-dashboard", "--scan-report", str(scan_file), "--output", str(output)])

    assert result.exit_code == 0
    html = output.read_text(encoding="utf-8")
    assert "openai" in html
    assert "broken" not in html
    assert "green" in html
    assert "Reason" in html


def test_status_dashboard_from_sources_check_report(tmp_path: Path):
    source_payload = [
        {
            "company_slug": "openai",
            "company_name": "OpenAI",
            "ats_kind": "ashby",
            "ok": True,
            "jobs_found": 3,
            "error": None,
        },
        {
            "company_slug": "broken",
            "company_name": "Broken",
            "ats_kind": "workday",
            "ok": False,
            "jobs_found": 0,
            "error": "timeout",
        },
    ]
    source_file = tmp_path / "sources.json"
    source_file.write_text(json.dumps(source_payload), encoding="utf-8")
    output = tmp_path / "dashboard.html"

    result = runner.invoke(app, ["status-dashboard", "--scan-report", str(source_file), "--output", str(output)])

    assert result.exit_code == 0
    html = output.read_text(encoding="utf-8")
    assert "openai" in html
    assert "broken" not in html


def test_status_dashboard_from_faang_status_report(tmp_path: Path):
    report_payload = {
        "results": [
            {
                "company_slug": "google",
                "ats_kind": "google_jobs_browser",
                "jobs_found": 0,
                "status": "red",
                "reason": "fetch_failed",
                "error": "timeout",
            },
            {
                "company_slug": "openai",
                "ats_kind": "ashby",
                "jobs_found": 4,
                "status": "green",
                "reason": "ok",
                "error": None,
            },
        ]
    }
    report_file = tmp_path / "faang-status.json"
    report_file.write_text(json.dumps(report_payload), encoding="utf-8")
    output = tmp_path / "dashboard.html"

    result = runner.invoke(app, ["status-dashboard", "--scan-report", str(report_file), "--output", str(output)])

    assert result.exit_code == 0
    html = output.read_text(encoding="utf-8")
    assert "google" in html
    assert "openai" in html
    assert "fetch_failed" in html


def test_faang_status_json_output(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("job_watch.cli.load_settings", lambda *args, **kwargs: object())
    monkeypatch.setattr("job_watch.cli.load_companies", lambda *args, **kwargs: [])
    monkeypatch.setattr("job_watch.cli.JobWatchService", DummyFaangService)

    output = tmp_path / "faang.json"
    result = runner.invoke(app, ["faang-status", "--format", "json", "--output", str(output)])

    assert result.exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["total_companies"] == 2
    assert payload["green"] == 1
    assert payload["results"][1]["reason"] == "fetch_failed"
