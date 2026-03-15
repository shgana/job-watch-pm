"""Typer CLI for Job Watch."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import load_companies, load_settings, resolve_sheet_id
from .constants import FAANG_PLUS_TARGET_SLUGS
from .dashboard import render_status_dashboard
from .logging_utils import get_logger
from .service import JobWatchService
from .sheets import GoogleSheetGateway

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def scan(
    company: str | None = typer.Option(None, help="Optional company slug to scan."),
    metro: str | None = typer.Option(None, help="Optional metro key to require."),
    freshness_days: int | None = typer.Option(None, help="Override freshness window in days."),
    format: str = typer.Option("text", help="Output format: text or json."),
    output: Path | None = typer.Option(None, help="Optional JSON output path."),
    sheet_id: str | None = typer.Option(None, help="Google Sheet ID override."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fetch jobs, filter matches, and sync them into Google Sheets."""

    settings = load_settings(str(settings_path) if settings_path else None)
    if freshness_days is not None:
        settings.freshness_days = freshness_days
    if format not in {"text", "json"}:
        raise typer.BadParameter("format must be text or json")
    if output is not None and format != "json":
        raise typer.BadParameter("--output requires --format json")
    if metro and metro not in settings.metros:
        raise typer.BadParameter(f"Unknown metro {metro}. Expected one of: {', '.join(settings.metros)}")
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    summary = asyncio.run(service.scan(sheet_id=sheet_id, company_slug=company, metro_key=metro))
    if format == "json":
        payload = service.scan_payload(summary)
        rendered = json.dumps(payload, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            console.print(f"Wrote scan report to {output}")
        else:
            console.print(rendered)
        return

    console.print(
        f"Scanned {summary.scanned_companies} companies, fetched {summary.fetched_jobs} jobs, "
        f"matched {summary.matched_jobs}, inserted {summary.new_rows}, updated {summary.updated_rows}."
    )
    if summary.failures:
        console.print("[yellow]Failures:[/yellow]")
        for failure in summary.failures:
            console.print(f" - {failure}")

    if summary.alert_rows:
        table = Table(title="New BA/PM Matches")
        for column in ["company", "title", "location", "apply_url"]:
            table.add_column(column)
        for row in summary.alert_rows:
            table.add_row(row["company"], row["title"], row["location"], row["apply_url"])
        console.print(table)
    else:
        console.print("No new fresh matches.")


@app.command("sources-check")
def sources_check(
    company: str | None = typer.Option(None, help="Optional company slug to check."),
    format: str = typer.Option("table", help="Output format: table or json."),
    output: Path | None = typer.Option(None, help="Optional JSON output path."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate configured public source endpoints without writing to the sheet."""

    if format not in {"table", "json"}:
        raise typer.BadParameter("format must be table or json")
    if output is not None and format != "json":
        raise typer.BadParameter("--output requires --format json")
    settings = load_settings(str(settings_path) if settings_path else None)
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    results = asyncio.run(service.sources_check(company_slug=company))
    if format == "json":
        payload = service.source_check_payload(results)
        rendered = json.dumps(payload, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            console.print(f"Wrote source check report to {output}")
        else:
            console.print(rendered)
    else:
        table = Table(title="Source Check")
        table.add_column("company")
        table.add_column("ats")
        table.add_column("status")
        table.add_column("jobs")
        table.add_column("details")
        for result in results:
            table.add_row(
                result.company_slug,
                result.ats_kind,
                "ok" if result.ok else "error",
                str(result.jobs_found),
                result.error or "",
            )
        console.print(table)

    if any(not result.ok for result in results):
        raise typer.Exit(code=1)


@app.command()
def export(
    status: str = typer.Option("all", help="Status filter: new, applied, tracked, or all."),
    format: str = typer.Option("csv", help="Output format: csv or json."),
    output: Path = typer.Option(..., help="Output file path."),
    sheet_id: str | None = typer.Option(None, help="Google Sheet ID override."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Export the application tracker to CSV or JSON."""

    if format not in {"csv", "json"}:
        raise typer.BadParameter("format must be csv or json")
    settings = load_settings(str(settings_path) if settings_path else None)
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    row_count = service.export_rows(
        sheet_id=sheet_id,
        status=status,
        output_format=format,
        output_path=output,
    )
    console.print(f"Exported {row_count} rows to {output}")


@app.command("sheet-template")
def sheet_template(
    sheet_id: str | None = typer.Option(None, help="Google Sheet ID override."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
) -> None:
    """Ensure the Google Sheet tab exists with the expected header template."""

    settings = load_settings(str(settings_path) if settings_path else None)
    resolved_sheet_id = resolve_sheet_id(settings, sheet_id)
    gateway = GoogleSheetGateway(resolved_sheet_id, settings.sheet_tab_name)
    gateway.ensure_template()
    console.print(
        f"Sheet template is ready in tab '{settings.sheet_tab_name}' for sheet {resolved_sheet_id}."
    )


@app.command("policy-check")
def policy_check(
    format: str = typer.Option("table", help="Output format: table or json."),
    output: Path | None = typer.Option(None, help="Optional JSON output path."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Validate official-source policy constraints for all configured companies."""

    if format not in {"table", "json"}:
        raise typer.BadParameter("format must be table or json")
    if output is not None and format != "json":
        raise typer.BadParameter("--output requires --format json")

    settings = load_settings(str(settings_path) if settings_path else None)
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    violations = service.validate_catalog_sources()

    if format == "json":
        rendered = json.dumps(violations, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            console.print(f"Wrote policy report to {output}")
        else:
            console.print(rendered)
    else:
        table = Table(title="Official Source Policy Check")
        table.add_column("company")
        table.add_column("error")
        for item in violations:
            table.add_row(item.get("company_slug", ""), item.get("error", ""))
        if violations:
            console.print(table)
        else:
            console.print("No policy violations found.")

    if violations:
        raise typer.Exit(code=1)


@app.command("faang-status")
def faang_status(
    format: str = typer.Option("table", help="Output format: table or json."),
    output: Path | None = typer.Option(None, help="Optional JSON output path."),
    scan_report: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        help="Optional scan JSON report path from `job-watch scan --format json`.",
    ),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate FAANG+ company status with explicit red/green reason codes."""

    if format not in {"table", "json"}:
        raise typer.BadParameter("format must be table or json")
    if output is not None and format != "json":
        raise typer.BadParameter("--output requires --format json")

    settings = load_settings(str(settings_path) if settings_path else None)
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)

    scan_company_results = None
    if scan_report is not None:
        payload = json.loads(scan_report.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            raw_results = payload.get("company_results", [])
            if isinstance(raw_results, list):
                scan_company_results = raw_results

    results = asyncio.run(service.faang_plus_status(scan_company_results=scan_company_results))
    payload = service.faang_plus_status_payload(results)
    if format == "json":
        rendered = json.dumps(payload, indent=2)
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            console.print(f"Wrote FAANG+ status report to {output}")
        else:
            console.print(rendered)
        return

    table = Table(title="FAANG+ Source Status")
    table.add_column("company")
    table.add_column("ats")
    table.add_column("enabled")
    table.add_column("jobs")
    table.add_column("status")
    table.add_column("reason")
    table.add_column("details")
    for item in payload["results"]:
        table.add_row(
            str(item.get("company_slug", "")),
            str(item.get("ats_kind", "")),
            "yes" if bool(item.get("enabled", False)) else "no",
            str(item.get("jobs_found", 0)),
            str(item.get("status", "red")),
            str(item.get("reason", "")),
            str(item.get("error") or ""),
        )
    console.print(table)


@app.command("cleanup-non-new-grad")
def cleanup_non_new_grad(
    sheet_id: str | None = typer.Option(None, help="Google Sheet ID override."),
    output: Path | None = typer.Option(None, help="Optional JSON cleanup report output path."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Archive existing sheet rows that are outside new-grad role scope."""

    settings = load_settings(str(settings_path) if settings_path else None)
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    summary = service.cleanup_non_new_grad_rows(sheet_id=sheet_id)

    console.print(
        f"Scanned {summary.scanned_rows} rows, archived {summary.archived_rows}, "
        f"skipped {summary.skipped_terminal_rows} terminal rows."
    )
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary.report_rows, indent=2) + "\n", encoding="utf-8")
        console.print(f"Wrote cleanup report to {output}")


@app.command("status-dashboard")
def status_dashboard(
    output: Path = typer.Option(
        Path("artifacts/status-dashboard.html"),
        help="Output HTML dashboard path.",
    ),
    scan_report: Path | None = typer.Option(
        None,
        exists=True,
        dir_okay=False,
        help="Optional scan JSON report path from `job-watch scan --format json`.",
    ),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate a FAANG+-only green/red company status dashboard."""

    if scan_report is not None:
        payload = json.loads(scan_report.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("results"), list):
            rows = [
                {
                    "company_slug": item.get("company_slug", ""),
                    "ats_kind": item.get("ats_kind", ""),
                    "jobs_found": int(item.get("jobs_found", item.get("fetched_jobs", 0)) or 0),
                    "status": item.get("status") or ("green" if item.get("ok") else "red"),
                    "reason": item.get("reason") or ("ok" if not item.get("error") else "fetch_failed"),
                    "error": item.get("error"),
                }
                for item in payload.get("results", [])
            ]
        elif isinstance(payload, list):
            rows = [
                {
                    "company_slug": item.get("company_slug", ""),
                    "ats_kind": item.get("ats_kind", ""),
                    "jobs_found": int(item.get("jobs_found", item.get("fetched_jobs", 0)) or 0),
                    "status": "green" if bool(item.get("ok", not bool(item.get("error")))) else "red",
                    "reason": "ok" if bool(item.get("ok", not bool(item.get("error")))) else "fetch_failed",
                    "error": item.get("error"),
                }
                for item in payload
            ]
        else:
            rows = [
                {
                    "company_slug": item.get("company_slug", ""),
                    "ats_kind": item.get("ats_kind", ""),
                    "jobs_found": int(item.get("fetched_jobs", 0) or 0),
                    "status": "green" if not bool(item.get("error")) else "red",
                    "reason": "ok" if not bool(item.get("error")) else "fetch_failed",
                    "error": item.get("error"),
                }
                for item in payload.get("company_results", [])
            ]
    else:
        settings = load_settings(str(settings_path) if settings_path else None)
        companies = load_companies(str(companies_path) if companies_path else None)
        logger = get_logger(verbose=verbose)
        service = JobWatchService(settings=settings, companies=companies, logger=logger)
        report = service.faang_plus_status_payload(asyncio.run(service.faang_plus_status()))
        rows = report["results"]

    target = set(FAANG_PLUS_TARGET_SLUGS)
    filtered = [row for row in rows if str(row.get("company_slug", "")) in target]
    row_map = {str(row.get("company_slug", "")): row for row in filtered}
    for slug in FAANG_PLUS_TARGET_SLUGS:
        if slug not in row_map:
            row_map[slug] = {
                "company_slug": slug,
                "ats_kind": "",
                "jobs_found": 0,
                "status": "red",
                "reason": "missing_status_row",
                "error": "status row not found in input payload",
            }
    rows = [row_map[slug] for slug in FAANG_PLUS_TARGET_SLUGS]
    rendered = render_status_dashboard(rows, title="Job Watch FAANG+ Source Status")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    console.print(f"Wrote status dashboard to {output}")


if __name__ == "__main__":  # pragma: no cover
    app()
