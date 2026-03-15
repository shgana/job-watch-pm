# Job Watch

`job-watch` scans official company career sources for early-career business analyst, product/program/project manager roles and syncs matches into a Google Sheet for review and application tracking.

## Features

- Public ATS connectors for Greenhouse, Lever, Ashby, SmartRecruiters, and Workday-style JSON feeds
- High-precision new-grad matching from title + description signals (internships excluded, rotational programs included)
- US + Remote location matching
- Google Sheets sync that preserves manual status, notes, and priority columns
- Cron-ready CLI plus a GitHub Actions workflow for twice-daily hosted runs
- Official-source policy checks for all configured companies
- A validated catalog of 240+ enabled companies backed by source checks
- Simple status dashboard output with green/red company health indicators

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Create Google credentials as a service account, share your target sheet with the service account email, and set:

```bash
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ...}'
export GOOGLE_SHEET_ID='your-sheet-id'
```

Run a scan:

```bash
job-watch scan
```

Export the tracker:

```bash
job-watch export --format csv --output jobs.csv
```

Validate configured sources without writing to the sheet:

```bash
job-watch sources-check
job-watch sources-check --format json --output exports/source-health.json
job-watch policy-check
job-watch cleanup-non-new-grad --output exports/cleanup-report.json
job-watch status-dashboard --output exports/status-dashboard.html
```

Run live source validation for every enabled company:

```bash
JOB_WATCH_RUN_LIVE_TESTS=1 python -m pytest -q tests/test_live_sources.py
```

## Hosted Schedule

The repo includes:

- `.github/workflows/job-watch.yml` for the twice-daily scan and default unit test suite
- `.github/workflows/source-health.yml` for daily live validation of every enabled company source
- Scheduled runs upload `artifacts/status-dashboard.html` as a downloadable health dashboard artifact

Required GitHub Actions secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHEET_ID`

## Config

- [`config/settings.toml`](/Users/shyam/Documents/job-watch-pm/config/settings.toml)
- [`config/companies.toml`](/Users/shyam/Documents/job-watch-pm/config/companies.toml)
- [`config/expansion_candidates.toml`](/Users/shyam/Documents/job-watch-pm/config/expansion_candidates.toml) (curated +50 expansion manifest)

The current enabled catalog was revalidated on March 13, 2026. Enabled sources are official company career pages or official ATS redirects, not aggregators.

Override them with:

```bash
export JOB_WATCH_SETTINGS_PATH=/absolute/path/to/settings.toml
export JOB_WATCH_COMPANIES_PATH=/absolute/path/to/companies.toml
```

## Tracker Columns

The Google Sheet tracker stores:

- `job_key`
- `status`
- `company`
- `title`
- `location`
- `metro`
- `freshness_status`
- `posted_at`
- `discovered_at`
- `apply_url`
- `career_page_url`
- `source`
- `notes`
- `manual_priority`
- `last_seen_at`

Rows that disappear from source feeds are automatically marked `stale` unless you have already moved them to a terminal manual status like `applied`, `archived`, or `rejected`.
