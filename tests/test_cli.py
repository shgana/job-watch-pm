import json
from pathlib import Path

from typer.testing import CliRunner

from job_watch.cli import app
from job_watch.models import SourceCheckResult

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
