"""Core scan and export workflows."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from dataclasses import asdict
from pathlib import Path

import httpx

from .config import resolve_sheet_id
from .constants import DEFAULT_USER_AGENT, SHEET_COLUMNS
from .matching import apply_matching
from .models import AppSettings, CompanyConfig, FetchResult, ScanSummary, SourceCheckResult
from .registry import ADAPTERS, get_adapter
from .sheets import GoogleSheetGateway, SheetTracker


class JobWatchService:
    """Execute scan, export, and source-check operations."""

    def __init__(
        self,
        settings: AppSettings,
        companies: list[CompanyConfig],
        logger: logging.Logger | None = None,
        adapters=None,
    ) -> None:
        self.settings = settings
        self.companies = companies
        self.logger = logger or logging.getLogger("job-watch")
        self.adapters = adapters or ADAPTERS

    async def scan(
        self,
        *,
        sheet_id: str | None,
        company_slug: str | None = None,
        metro_key: str | None = None,
        tracker: SheetTracker | None = None,
    ) -> ScanSummary:
        """Run a scan and synchronize matched jobs to the tracker."""

        fetch_results = await self._fetch_all(company_slug=company_slug)
        matched_records = []
        failures: list[str] = []
        fetched_jobs = 0
        for result in fetch_results:
            fetched_jobs += len(result.jobs)
            if result.error:
                failures.append(f"{result.company.slug}: {result.error}")
                continue
            for record in result.jobs:
                apply_matching(record, self.settings, metro_key=metro_key)
                if record.match_role and record.match_location:
                    matched_records.append(record)

        active_tracker = tracker or SheetTracker(
            GoogleSheetGateway(resolve_sheet_id(self.settings, sheet_id), self.settings.sheet_tab_name)
        )
        sync_result = active_tracker.sync(matched_records)
        row_map = {row["job_key"]: row for row in sync_result.all_rows}
        matched_map = {record.job_key: record for record in matched_records}
        alert_rows = [
            row_map[key]
            for key in sync_result.inserted_keys
            if matched_map[key].freshness_status != "stale"
        ]
        alert_rows.sort(key=lambda row: (row.get("company", ""), row.get("title", "")))

        return ScanSummary(
            scanned_companies=len(fetch_results),
            fetched_jobs=fetched_jobs,
            matched_jobs=len(matched_records),
            new_rows=len(sync_result.inserted_keys),
            new_alerts=len(alert_rows),
            updated_rows=len(sync_result.updated_keys),
            failures=failures,
            alert_rows=alert_rows,
        )

    async def sources_check(self, company_slug: str | None = None) -> list[SourceCheckResult]:
        """Validate configured source endpoints."""

        results = await self._fetch_all(company_slug=company_slug)
        checks: list[SourceCheckResult] = []
        for result in results:
            checks.append(
                SourceCheckResult(
                    company_slug=result.company.slug,
                    company_name=result.company.name,
                    ats_kind=result.company.ats_kind,
                    ok=result.error is None,
                    jobs_found=len(result.jobs),
                    error=result.error,
                )
            )
        return checks

    @staticmethod
    def source_check_payload(results: list[SourceCheckResult]) -> list[dict[str, str | int | bool | None]]:
        """Serialize source-check results for machine-readable output."""

        return [asdict(result) for result in results]

    def export_rows(
        self,
        *,
        sheet_id: str | None,
        status: str,
        output_format: str,
        output_path: Path,
        tracker: SheetTracker | None = None,
    ) -> int:
        """Export tracker rows to CSV or JSON."""

        active_tracker = tracker or SheetTracker(
            GoogleSheetGateway(resolve_sheet_id(self.settings, sheet_id), self.settings.sheet_tab_name)
        )
        rows = active_tracker.rows()
        if status != "all":
            rows = [row for row in rows if row.get("status", "").lower() == status.lower()]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "csv":
            with output_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
        else:
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(rows, handle, indent=2)
        return len(rows)

    async def _fetch_all(self, company_slug: str | None = None) -> list[FetchResult]:
        companies = [company for company in self.companies if company.enabled]
        if company_slug:
            companies = [company for company in companies if company.slug == company_slug]
        semaphore = asyncio.Semaphore(self.settings.concurrency)
        async with httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            follow_redirects=True,
        ) as client:
            tasks = [self._fetch_company(client, semaphore, company) for company in companies]
            return await asyncio.gather(*tasks)

    async def _fetch_company(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        company: CompanyConfig,
    ) -> FetchResult:
        adapter = self.adapters.get(company.ats_kind)
        if adapter is None:
            adapter = get_adapter(company.ats_kind)
        async with semaphore:
            try:
                jobs = await adapter.fetch(client, company)
                return FetchResult(company=company, jobs=jobs)
            except Exception as exc:  # pragma: no cover - exercised in service tests
                self.logger.debug("source fetch failed for %s: %s", company.slug, exc)
                return FetchResult(company=company, jobs=[], error=str(exc))
