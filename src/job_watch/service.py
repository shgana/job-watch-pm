"""Core scan and export workflows."""

from __future__ import annotations

import asyncio
import csv
import html
import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import httpx

from .config import resolve_sheet_id
from .constants import DEFAULT_USER_AGENT, FAANG_PLUS_TARGET_SLUGS, SHEET_COLUMNS
from .matching import apply_matching
from .models import (
    AppSettings,
    CleanupSummary,
    CompanyConfig,
    FaangStatusResult,
    FetchResult,
    JobRecord,
    ScanSummary,
    SourceCheckResult,
)
from .registry import ADAPTERS, get_adapter
from .source_policy import looks_like_direct_apply_url, validate_company_source_policy
from .sheets import GoogleSheetGateway, SheetTracker

DETAIL_ENRICHMENT_KINDS = {
    "amazon_jobs",
    "apple_jobs",
    "linkedin_jobs",
    "netflix_jobs",
    "salesforce_jobs",
    "google_jobs_browser",
    "meta_jobs_browser",
    "bytedance_jobs_browser",
    "tesla_jobs_browser",
}
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


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

        fetch_results = await self.fetch_sources(company_slug=company_slug)
        matched_records = []
        failures: list[str] = []
        fetched_jobs = 0
        matched_by_company: dict[str, int] = {}
        fetched_by_company: dict[str, int] = {}
        error_by_company: dict[str, str | None] = {}
        for result in fetch_results:
            fetched_jobs += len(result.jobs)
            fetched_by_company[result.company.slug] = len(result.jobs)
            matched_by_company.setdefault(result.company.slug, 0)
            if result.error:
                failures.append(f"{result.company.slug}: {result.error}")
                error_by_company[result.company.slug] = result.error
                continue
            error_by_company[result.company.slug] = None
            for record in result.jobs:
                apply_matching(record, self.settings, metro_key=metro_key)
                if record.match_role and record.match_location:
                    matched_records.append(record)
                    matched_by_company[result.company.slug] += 1

        active_tracker = tracker or SheetTracker(
            GoogleSheetGateway(resolve_sheet_id(self.settings, sheet_id), self.settings.sheet_tab_name)
        )
        sync_result = active_tracker.sync(matched_records)
        job_key_to_company = {record.job_key: record.company_slug for record in matched_records}
        inserted_by_company: dict[str, int] = {}
        updated_by_company: dict[str, int] = {}
        for key in sync_result.inserted_keys:
            slug = job_key_to_company.get(key)
            if slug:
                inserted_by_company[slug] = inserted_by_company.get(slug, 0) + 1
        for key in sync_result.updated_keys:
            slug = job_key_to_company.get(key)
            if slug:
                updated_by_company[slug] = updated_by_company.get(slug, 0) + 1
        row_map = {row["job_key"]: row for row in sync_result.all_rows}
        matched_map = {record.job_key: record for record in matched_records}
        alert_rows = [
            row_map[key]
            for key in sync_result.inserted_keys
            if matched_map[key].freshness_status != "stale"
        ]
        alert_rows.sort(key=lambda row: (row.get("company", ""), row.get("title", "")))
        company_results: list[dict[str, str | int | None]] = []
        for result in fetch_results:
            slug = result.company.slug
            company_results.append(
                {
                    "company_slug": slug,
                    "company_name": result.company.name,
                    "ats_kind": result.company.ats_kind,
                    "fetched_jobs": fetched_by_company.get(slug, 0),
                    "matched_jobs": matched_by_company.get(slug, 0),
                    "inserted_rows": inserted_by_company.get(slug, 0),
                    "updated_rows": updated_by_company.get(slug, 0),
                    "error": error_by_company.get(slug),
                }
            )
        company_results.sort(key=lambda item: str(item["company_slug"]))

        return ScanSummary(
            scanned_companies=len(fetch_results),
            fetched_jobs=fetched_jobs,
            matched_jobs=len(matched_records),
            new_rows=len(sync_result.inserted_keys),
            new_alerts=len(alert_rows),
            updated_rows=len(sync_result.updated_keys),
            failures=failures,
            alert_rows=alert_rows,
            company_results=company_results,
        )

    async def sources_check(self, company_slug: str | None = None) -> list[SourceCheckResult]:
        """Validate configured source endpoints."""

        results = await self.fetch_sources(company_slug=company_slug)
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

    async def faang_plus_status(
        self,
        *,
        scan_company_results: list[dict[str, Any]] | None = None,
    ) -> list[FaangStatusResult]:
        """Build per-company FAANG+ status with deterministic red/green reasons."""

        company_map = {company.slug: company for company in self.companies}
        scan_map: dict[str, dict[str, Any]] = {}
        if scan_company_results is not None:
            for item in scan_company_results:
                slug = str(item.get("company_slug", "") or "")
                if slug:
                    scan_map[slug] = item

        results_by_slug: dict[str, FaangStatusResult] = {}
        fetch_candidates: list[CompanyConfig] = []
        for slug in FAANG_PLUS_TARGET_SLUGS:
            company = company_map.get(slug)
            if company is None:
                results_by_slug[slug] = FaangStatusResult(
                    company_slug=slug,
                    company_name=slug.replace("-", " ").title(),
                    ats_kind="",
                    in_catalog=False,
                    enabled=False,
                    adapter_registered=False,
                    policy_ok=False,
                    fetch_ok=False,
                    jobs_found=0,
                    status="red",
                    reason="missing_in_catalog",
                    error="company slug missing from catalog",
                )
                continue

            adapter_registered = self._is_adapter_registered(company.ats_kind)
            policy_errors = validate_company_source_policy(company)
            policy_ok = not policy_errors
            status = FaangStatusResult(
                company_slug=company.slug,
                company_name=company.name,
                ats_kind=company.ats_kind,
                in_catalog=True,
                enabled=company.enabled,
                adapter_registered=adapter_registered,
                policy_ok=policy_ok,
                fetch_ok=False,
                jobs_found=0,
                status="red",
                reason="unknown",
                source_policy=company.source_policy,
                official_career_site_url=company.official_career_site_url,
            )

            if not company.enabled:
                status.reason = "disabled_in_catalog"
                status.error = "company disabled in catalog"
                results_by_slug[slug] = status
                continue
            if not adapter_registered:
                status.reason = "adapter_not_registered"
                status.error = f"adapter not registered for ats_kind={company.ats_kind}"
                results_by_slug[slug] = status
                continue
            if not policy_ok:
                status.reason = "policy_failed"
                status.error = "; ".join(policy_errors)
                results_by_slug[slug] = status
                continue

            scan_item = scan_map.get(slug)
            if scan_item is not None:
                fetched_jobs = int(scan_item.get("fetched_jobs", scan_item.get("jobs_found", 0)) or 0)
                fetch_error = scan_item.get("error")
                status.jobs_found = fetched_jobs
                status.fetch_ok = fetch_error is None
                status.reason = "ok" if fetch_error is None else "fetch_failed"
                status.status = "green" if fetch_error is None else "red"
                status.error = str(fetch_error) if fetch_error is not None else None
                results_by_slug[slug] = status
                continue

            fetch_candidates.append(company)
            results_by_slug[slug] = status

        if fetch_candidates:
            fetched = await self._fetch_companies(fetch_candidates)
            for fetched_result in fetched:
                slug = fetched_result.company.slug
                existing = results_by_slug[slug]
                if fetched_result.error is None:
                    existing.fetch_ok = True
                    existing.jobs_found = len(fetched_result.jobs)
                    existing.status = "green"
                    existing.reason = "ok"
                    existing.error = None
                else:
                    existing.fetch_ok = False
                    existing.jobs_found = 0
                    existing.status = "red"
                    existing.reason = "fetch_failed"
                    existing.error = fetched_result.error

        return [results_by_slug[slug] for slug in FAANG_PLUS_TARGET_SLUGS]

    @staticmethod
    def faang_plus_status_payload(results: list[FaangStatusResult]) -> dict[str, Any]:
        """Serialize FAANG+ status for machine-readable output."""

        payload_rows = [asdict(result) for result in results]
        green = sum(1 for row in payload_rows if row.get("status") == "green")
        red = len(payload_rows) - green
        return {
            "target_slugs": list(FAANG_PLUS_TARGET_SLUGS),
            "total_companies": len(payload_rows),
            "green": green,
            "red": red,
            "results": payload_rows,
        }

    def validate_faang_plus_catalog(self) -> list[str]:
        """Return catalog issues for FAANG+ target slugs."""

        company_map = {company.slug: company for company in self.companies}
        errors: list[str] = []
        for slug in FAANG_PLUS_TARGET_SLUGS:
            company = company_map.get(slug)
            if company is None:
                errors.append(f"{slug}: missing_in_catalog")
                continue
            if not company.enabled:
                errors.append(f"{slug}: disabled_in_catalog")
            if not self._is_adapter_registered(company.ats_kind):
                errors.append(f"{slug}: adapter_not_registered ({company.ats_kind})")
        return errors

    def _is_adapter_registered(self, ats_kind: str) -> bool:
        if ats_kind in self.adapters:
            return True
        try:
            get_adapter(ats_kind)
            return True
        except ValueError:
            return False

    def validate_catalog_sources(self) -> list[dict[str, str]]:
        """Validate company source policy metadata and URL constraints."""

        violations: list[dict[str, str]] = []
        for company in self.companies:
            errors = validate_company_source_policy(company)
            for error in errors:
                violations.append({"company_slug": company.slug, "error": error})
        return violations

    @staticmethod
    def scan_payload(summary: ScanSummary) -> dict[str, Any]:
        """Serialize scan summary for machine-readable output."""

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

    def cleanup_non_new_grad_rows(
        self,
        *,
        sheet_id: str | None,
        tracker: SheetTracker | None = None,
    ) -> CleanupSummary:
        """Archive non-new-grad rows immediately while preserving terminal statuses."""

        active_tracker = tracker or SheetTracker(
            GoogleSheetGateway(resolve_sheet_id(self.settings, sheet_id), self.settings.sheet_tab_name)
        )
        rows = active_tracker.rows()
        report_rows: list[dict[str, str]] = []
        archived_rows = 0
        skipped_terminal_rows = 0
        for row in rows:
            status = row.get("status", "").strip().lower()
            if status in {"applied", "rejected"}:
                skipped_terminal_rows += 1
                continue
            if status == "archived":
                skipped_terminal_rows += 1
                continue
            record = JobRecord(
                job_key=row.get("job_key", ""),
                company_slug=row.get("company", "").strip().lower().replace(" ", "-"),
                company_name=row.get("company", ""),
                ats_kind=row.get("source", ""),
                source_job_id=row.get("job_key", ""),
                title=row.get("title", ""),
                team="",
                department="",
                location_raw=row.get("location", ""),
                location_normalized=row.get("location", ""),
                posted_at=None,
                updated_at=None,
                apply_url=row.get("apply_url", ""),
                career_page_url=row.get("career_page_url", ""),
                employment_type="",
                remote_flag="remote" in row.get("location", "").lower(),
                description_text="",
            )
            apply_matching(record, self.settings)
            if record.match_role and record.match_location:
                continue
            row["status"] = "archived"
            existing_notes = row.get("notes", "")
            marker = "auto-archived: non-new-grad scope"
            row["notes"] = f"{existing_notes} | {marker}".strip(" |") if existing_notes else marker
            archived_rows += 1
            report_rows.append(
                {
                    "job_key": row.get("job_key", ""),
                    "company": row.get("company", ""),
                    "title": row.get("title", ""),
                    "location": row.get("location", ""),
                    "reason": record.match_reason or "outside_new_grad_scope",
                }
            )

        if archived_rows:
            rows.sort(key=lambda item: (item.get("status") != "new", item.get("company", ""), item.get("title", "")))
            active_tracker.gateway.write_rows(rows)
        return CleanupSummary(
            scanned_rows=len(rows),
            archived_rows=archived_rows,
            skipped_terminal_rows=skipped_terminal_rows,
            report_rows=report_rows,
        )

    async def fetch_sources(self, company_slug: str | None = None) -> list[FetchResult]:
        """Fetch jobs from all enabled company sources."""

        companies = [company for company in self.companies if company.enabled]
        if company_slug:
            companies = [company for company in companies if company.slug == company_slug]
        return await self._fetch_companies(companies)

    async def _fetch_companies(self, companies: list[CompanyConfig]) -> list[FetchResult]:
        """Fetch jobs for a specific set of companies."""

        if not companies:
            return []
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
            policy_errors = validate_company_source_policy(company)
            if policy_errors:
                error = "; ".join(policy_errors)
                self.logger.debug("source policy failed for %s: %s", company.slug, error)
                return FetchResult(company=company, jobs=[], error=error)

            attempts = max(1, int(self.settings.source_retry_attempts))
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    jobs = await adapter.fetch(client, company)
                    for job in jobs:
                        if looks_like_direct_apply_url(job.apply_url):
                            job.apply_url = job.career_page_url or company.career_url
                    await self._enrich_missing_descriptions(client, company, jobs)
                    return FetchResult(company=company, jobs=jobs)
                except Exception as exc:  # pragma: no cover - exercised in service tests
                    last_exc = exc
                    self.logger.debug(
                        "source fetch failed for %s (attempt %s/%s): %s",
                        company.slug,
                        attempt,
                        attempts,
                        exc,
                    )
                    if attempt < attempts:
                        await asyncio.sleep(min(1.0 * attempt, 3.0))

            return FetchResult(company=company, jobs=[], error=str(last_exc) if last_exc else "unknown error")

    async def _enrich_missing_descriptions(
        self,
        client: httpx.AsyncClient,
        company: CompanyConfig,
        jobs: list,
    ) -> None:
        if company.ats_kind not in DETAIL_ENRICHMENT_KINDS:
            return
        if not company.request_options.get("detail_fetch", True):
            return
        max_jobs = int(company.request_options.get("detail_fetch_limit", 8))
        concurrency = int(company.request_options.get("detail_fetch_concurrency", 4))
        timeout = float(company.request_options.get("detail_fetch_timeout_seconds", 12))
        targets = [job for job in jobs if not job.description_text and job.apply_url][:max_jobs]
        if not targets:
            return
        limiter = asyncio.Semaphore(concurrency)

        async def _fetch(job) -> None:
            async with limiter:
                try:
                    response = await client.get(job.apply_url, headers=company.headers, timeout=timeout)
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type:
                        return
                    text = self._extract_text(response.text)
                    if text:
                        job.description_text = text[:12000]
                except Exception:
                    return

        await asyncio.gather(*[_fetch(job) for job in targets])

    @staticmethod
    def _extract_text(raw_html: str) -> str:
        without_scripts = _SCRIPT_STYLE_RE.sub(" ", raw_html)
        plain = _TAG_RE.sub(" ", without_scripts)
        return re.sub(r"\s+", " ", html.unescape(plain)).strip()
