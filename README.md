# Job Watch

`job-watch` scans public ATS job boards for business analyst and project manager roles at curated tech, SaaS, and fintech companies, then syncs matches into a Google Sheet for review and application tracking.

## Features

- Public ATS connectors for Greenhouse, Lever, Ashby, SmartRecruiters, and Workday-style JSON feeds
- Strict title and metro matching for BA/PM roles in Seattle, SF Bay Area, NYC, Boston, and Northern Virginia
- Google Sheets sync that preserves manual status, notes, and priority columns
- Cron-ready CLI plus a GitHub Actions workflow for twice-daily hosted runs

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
```

## Hosted Schedule

The repo includes [`job-watch.yml`](/Users/shyam/Documents/marketplaceflipper/.github/workflows/job-watch.yml), which runs twice daily on GitHub Actions and can also be triggered manually.

Required GitHub Actions secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_SHEET_ID`

## Config

- [`config/settings.toml`](/Users/shyam/Documents/marketplaceflipper/ba+pm role scraper/config/settings.toml)
- [`config/companies.toml`](/Users/shyam/Documents/marketplaceflipper/ba+pm role scraper/config/companies.toml)

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
