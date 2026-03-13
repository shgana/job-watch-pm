#!/usr/bin/env python3
"""Build a static HTML status dashboard from scan reports."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rows(payload: Any) -> list[dict[str, str | bool]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = []
        for key in ("companies", "results", "sources", "per_company"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                items = candidate
                break
    else:
        items = []

    rows: list[dict[str, str | bool]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        company = str(item.get("company") or item.get("company_slug") or "")
        if not company:
            continue
        source = str(item.get("ats_kind") or item.get("source") or "")
        jobs = str(
            item.get(
                "fetched_jobs",
                item.get("jobs_found", item.get("matched_jobs", 0)),
            )
        )
        error = str(item.get("error") or "")
        ok = bool(item.get("ok")) if "ok" in item else not error
        rows.append(
            {
                "company": company,
                "source": source,
                "jobs": jobs,
                "ok": ok,
                "error": error,
            }
        )
    rows.sort(key=lambda row: str(row["company"]))
    return rows


def _render(rows: list[dict[str, str | bool]], title: str) -> str:
    ok_count = sum(1 for row in rows if bool(row["ok"]))
    err_count = len(rows) - ok_count
    rendered_rows: list[str] = []
    for row in rows:
        status_ok = bool(row["ok"])
        status_class = "status-ok" if status_ok else "status-error"
        status_label = "green" if status_ok else "red"
        rendered_rows.append(
            "<tr>"
            f"<td>{escape(str(row['company']))}</td>"
            f"<td>{escape(str(row['source']))}</td>"
            f"<td>{escape(str(row['jobs']))}</td>"
            f"<td><span class='status {status_class}'>{status_label}</span></td>"
            f"<td>{escape(str(row['error']))}</td>"
            "</tr>"
        )

    generated = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; padding: 24px; background: #f8fafc; color: #0f172a; font-family: -apple-system, Segoe UI, Arial, sans-serif; }}
    .card {{ max-width: 1200px; margin: 0 auto; background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px; }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    .meta {{ margin: 0 0 16px; color: #475569; font-size: 14px; }}
    .summary {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; font-size: 14px; }}
    .pill {{ border-radius: 9999px; padding: 6px 10px; border: 1px solid #e2e8f0; background: #f1f5f9; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }}
    th {{ color: #475569; font-weight: 600; background: #f8fafc; }}
    .status {{ display: inline-block; border-radius: 9999px; padding: 3px 8px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
    .status-ok {{ background: #dcfce7; color: #166534; }}
    .status-error {{ background: #fee2e2; color: #991b1b; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{escape(title)}</h1>
    <p class="meta">Generated: {escape(generated)}</p>
    <div class="summary">
      <span class="pill">Total Companies: {len(rows)}</span>
      <span class="pill">Green: {ok_count}</span>
      <span class="pill">Red: {err_count}</span>
    </div>
    <table>
      <thead><tr><th>Company</th><th>Source</th><th>Jobs</th><th>Status</th><th>Error</th></tr></thead>
      <tbody>{''.join(rendered_rows)}</tbody>
    </table>
  </div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build status dashboard HTML")
    parser.add_argument("--scan-report", type=Path, required=False)
    parser.add_argument("--sources-report", type=Path, required=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Job Watch Source Status")
    args = parser.parse_args()

    rows: list[dict[str, str | bool]] = []
    source_label = ""

    if args.scan_report and args.scan_report.exists():
        rows = _normalize_rows(_load_json(args.scan_report))
        source_label = f"scan report: {args.scan_report}"

    if not rows and args.sources_report and args.sources_report.exists():
        rows = _normalize_rows(_load_json(args.sources_report))
        source_label = f"sources report: {args.sources_report}"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render(rows, args.title), encoding="utf-8")
    print(f"Wrote dashboard to {args.output}")
    if source_label:
        print(f"Rendered from {source_label}")
    else:
        print("Rendered with no input rows (no report file found).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
