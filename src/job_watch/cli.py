"""Typer CLI for Job Watch."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import load_companies, load_settings
from .logging_utils import get_logger
from .service import JobWatchService

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command()
def scan(
    company: str | None = typer.Option(None, help="Optional company slug to scan."),
    metro: str | None = typer.Option(None, help="Optional metro key to require."),
    freshness_days: int | None = typer.Option(None, help="Override freshness window in days."),
    sheet_id: str | None = typer.Option(None, help="Google Sheet ID override."),
    settings_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    companies_path: Path | None = typer.Option(None, exists=True, dir_okay=False),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Fetch jobs, filter matches, and sync them into Google Sheets."""

    settings = load_settings(str(settings_path) if settings_path else None)
    if freshness_days is not None:
        settings.freshness_days = freshness_days
    if metro and metro not in settings.metros:
        raise typer.BadParameter(f"Unknown metro {metro}. Expected one of: {', '.join(settings.metros)}")
    companies = load_companies(str(companies_path) if companies_path else None)
    logger = get_logger(verbose=verbose)
    service = JobWatchService(settings=settings, companies=companies, logger=logger)
    summary = asyncio.run(service.scan(sheet_id=sheet_id, company_slug=company, metro_key=metro))

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


if __name__ == "__main__":  # pragma: no cover
    app()
