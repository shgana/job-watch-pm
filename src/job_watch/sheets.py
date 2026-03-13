"""Google Sheets tracking support."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from .constants import SHEET_COLUMNS, TERMINAL_TRACKER_STATUSES
from .matching import record_to_sheet_row
from .models import JobRecord, TrackerSyncResult
from .time_utils import utc_now

GOOGLE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetGateway(Protocol):
    """Gateway interface for sheet storage."""

    def read_rows(self) -> list[dict[str, str]]:
        """Return existing tracker rows."""

    def write_rows(self, rows: list[dict[str, str]]) -> None:
        """Persist all tracker rows."""


class GoogleSheetGateway:
    """Google Sheets gateway implementation."""

    def __init__(self, sheet_id: str, worksheet_name: str) -> None:
        import gspread

        creds = _load_credentials()
        client = gspread.authorize(creds.with_scopes(GOOGLE_SCOPES))
        spreadsheet = client.open_by_key(sheet_id)
        try:
            self.worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
            self.worksheet.update(range_name="A1:O1", values=[SHEET_COLUMNS])

    def read_rows(self) -> list[dict[str, str]]:
        values = self.worksheet.get_all_values()
        if not values:
            return []
        header = values[0]
        rows: list[dict[str, str]] = []
        for raw in values[1:]:
            padded = raw + [""] * (len(header) - len(raw))
            row = dict(zip(header, padded, strict=False))
            if row.get("job_key"):
                rows.append({column: row.get(column, "") for column in SHEET_COLUMNS})
        return rows

    def write_rows(self, rows: list[dict[str, str]]) -> None:
        values = [SHEET_COLUMNS]
        for row in rows:
            values.append([row.get(column, "") for column in SHEET_COLUMNS])
        self.worksheet.clear()
        self.worksheet.update(range_name="A1", values=values)


def _load_credentials():
    from google.oauth2.service_account import Credentials

    raw_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if raw_json:
        info = json.loads(raw_json)
        return Credentials.from_service_account_info(info)
    if credentials_path:
        return Credentials.from_service_account_file(credentials_path)
    raise ValueError(
        "Google service account credentials are required. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_APPLICATION_CREDENTIALS."
    )


@dataclass(slots=True)
class SheetTracker:
    """Synchronize matched jobs into a sheet."""

    gateway: SheetGateway

    def sync(self, records: list[JobRecord]) -> TrackerSyncResult:
        """Upsert matched jobs into the tracker."""

        now = utc_now()
        current_rows = self.gateway.read_rows()
        row_map = {row["job_key"]: row for row in current_rows}
        inserted_keys: set[str] = set()
        updated_keys: set[str] = set()
        seen_keys: set[str] = set()

        for record in records:
            existing = row_map.get(record.job_key)
            row_map[record.job_key] = record_to_sheet_row(record, now, existing_row=existing)
            seen_keys.add(record.job_key)
            if existing is None:
                inserted_keys.add(record.job_key)
            else:
                updated_keys.add(record.job_key)

        for job_key, row in list(row_map.items()):
            if job_key in seen_keys:
                continue
            status = row.get("status", "").strip().lower()
            if status in TERMINAL_TRACKER_STATUSES or status == "stale":
                continue
            updated_row = row.copy()
            updated_row["status"] = "stale"
            row_map[job_key] = updated_row
            updated_keys.add(job_key)

        ordered_rows = list(row_map.values())
        ordered_rows.sort(
            key=lambda row: (row.get("status", "") != "new", row.get("discovered_at", ""), row.get("company", "")),
        )
        self.gateway.write_rows(ordered_rows)
        return TrackerSyncResult(
            inserted_keys=inserted_keys,
            updated_keys=updated_keys,
            all_rows=ordered_rows,
        )

    def rows(self) -> list[dict[str, str]]:
        """Return all tracker rows."""

        return self.gateway.read_rows()
