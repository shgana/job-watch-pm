"""Simple status dashboard rendering."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape


def render_status_dashboard(
    rows: list[dict[str, str | int | bool | None]],
    *,
    generated_at: datetime | None = None,
    title: str = "Job Watch FAANG+ Source Status",
) -> str:
    """Render a simple HTML status dashboard."""

    now = generated_at or datetime.now(tz=UTC)
    normalized_rows: list[dict[str, str]] = []
    ok_count = 0
    error_count = 0
    for item in rows:
        company = str(item.get("company_slug", "") or "")
        source = str(item.get("ats_kind", "") or "")
        jobs = str(item.get("jobs_found", item.get("fetched_jobs", 0)) or "0")
        reason = str(item.get("reason", "") or "")
        error = str(item.get("error", "") or "")
        status_value = str(item.get("status", "") or "").lower()
        if status_value:
            ok = status_value == "green"
        else:
            ok = bool(item.get("ok", not error))
        if not reason:
            reason = "ok" if ok else "fetch_failed"
        status = "ok" if ok else "error"
        if ok:
            ok_count += 1
        else:
            error_count += 1
        normalized_rows.append(
            {
                "company": company,
                "source": source,
                "jobs": jobs,
                "status": status,
                "reason": reason,
                "error": error,
            }
        )
    normalized_rows.sort(key=lambda row: row["company"])
    rendered_rows = []
    for row in normalized_rows:
        status_class = "status-ok" if row["status"] == "ok" else "status-error"
        status_label = "green" if row["status"] == "ok" else "red"
        rendered_rows.append(
            "<tr>"
            f"<td>{escape(row['company'])}</td>"
            f"<td>{escape(row['source'])}</td>"
            f"<td>{escape(row['jobs'])}</td>"
            f"<td><span class=\"status {status_class}\">{status_label}</span></td>"
            f"<td>{escape(row['reason'])}</td>"
            f"<td>{escape(row['error'])}</td>"
            "</tr>"
        )

    generated_label = now.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f8fafc;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #475569;
      --ok-bg: #dcfce7;
      --ok-text: #166534;
      --err-bg: #fee2e2;
      --err-text: #991b1b;
      --border: #e2e8f0;
    }}
    body {{
      margin: 0;
      padding: 24px;
      background: var(--bg);
      color: var(--text);
      font-family: "SF Pro Text", "Segoe UI", Arial, sans-serif;
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 24px;
    }}
    .meta {{
      margin: 0 0 16px;
      color: var(--muted);
      font-size: 14px;
    }}
    .summary {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 16px;
      font-size: 14px;
    }}
    .pill {{
      border-radius: 9999px;
      padding: 6px 10px;
      border: 1px solid var(--border);
      background: #f1f5f9;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: #f8fafc;
      position: sticky;
      top: 0;
    }}
    .status {{
      display: inline-block;
      border-radius: 9999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }}
    .status-ok {{
      background: var(--ok-bg);
      color: var(--ok-text);
    }}
    .status-error {{
      background: var(--err-bg);
      color: var(--err-text);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{escape(title)}</h1>
      <p class="meta">Generated: {escape(generated_label)}</p>
      <div class="summary">
        <span class="pill">Total Companies: {len(normalized_rows)}</span>
        <span class="pill">Green: {ok_count}</span>
        <span class="pill">Red: {error_count}</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Company</th>
            <th>Source</th>
            <th>Jobs</th>
            <th>Status</th>
            <th>Reason</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rendered_rows)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
