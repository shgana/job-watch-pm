#!/usr/bin/env python3
"""Build a static HTML status dashboard from JSON reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from job_watch.constants import FAANG_PLUS_TARGET_SLUGS
from job_watch.dashboard import render_status_dashboard


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rows(payload: Any) -> list[dict[str, str | int | bool | None]]:
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
    elif isinstance(payload, dict) and isinstance(payload.get("company_results"), list):
        items = payload["company_results"]
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    rows: list[dict[str, str | int | bool | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        company_slug = str(item.get("company_slug", "") or item.get("company", "") or "")
        if not company_slug:
            continue
        jobs = int(item.get("jobs_found", item.get("fetched_jobs", item.get("matched_jobs", 0))) or 0)
        status = str(item.get("status", "") or "").lower()
        ok = bool(item.get("ok", not bool(item.get("error"))))
        if not status:
            status = "green" if ok else "red"
        reason = str(item.get("reason", "") or ("ok" if status == "green" else "fetch_failed"))
        rows.append(
            {
                "company_slug": company_slug,
                "ats_kind": str(item.get("ats_kind", "") or item.get("source", "") or ""),
                "jobs_found": jobs,
                "status": status,
                "reason": reason,
                "error": str(item.get("error", "") or ""),
            }
        )
    row_map = {str(row["company_slug"]): row for row in rows}
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
    return [row_map[slug] for slug in FAANG_PLUS_TARGET_SLUGS]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build status dashboard HTML")
    parser.add_argument("--scan-report", type=Path, required=False)
    parser.add_argument("--sources-report", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Job Watch FAANG+ Source Status")
    args = parser.parse_args()

    rows: list[dict[str, str | int | bool | None]] = []
    source_label = ""

    if args.scan_report and args.scan_report.exists():
        rows = _normalize_rows(_load_json(args.scan_report))
        source_label = f"scan report: {args.scan_report}"

    if not rows and args.sources_report and args.sources_report.exists():
        rows = _normalize_rows(_load_json(args.sources_report))
        source_label = f"sources report: {args.sources_report}"

    html = render_status_dashboard(rows, title=args.title)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote dashboard to {args.output}")
    if source_label:
        print(f"Rendered from {source_label}")
    else:
        print("Rendered with no input rows (no report file found).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
