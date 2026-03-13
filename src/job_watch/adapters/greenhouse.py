"""Greenhouse adapter."""

from __future__ import annotations

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter


class GreenhouseAdapter(SourceAdapter):
    """Fetch jobs from the Greenhouse Job Board API."""

    ats_kind = "greenhouse"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        board_token = company.board_token or company.slug
        url = company.feed_url or f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
        payload = await self.get_json(client, url, headers=company.headers)
        jobs: list[JobRecord] = []
        for item in payload.get("jobs", []):
            location = (item.get("location") or {}).get("name", "")
            department = ", ".join(
                part.get("name", "") for part in item.get("departments", []) if part.get("name")
            )
            jobs.append(
                JobRecord(
                    job_key=stable_job_key(company.slug, str(item.get("id", "")), item.get("title", ""), item.get("absolute_url", "")),
                    company_slug=company.slug,
                    company_name=company.name,
                    ats_kind=self.ats_kind,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("title", ""),
                    team="",
                    department=department,
                    location_raw=location,
                    location_normalized=location,
                    posted_at=self.parse_date(item.get("updated_at")),
                    updated_at=self.parse_date(item.get("updated_at")),
                    apply_url=item.get("absolute_url", ""),
                    career_page_url=company.career_url,
                    employment_type="",
                    remote_flag="remote" in location.lower(),
                    description_text=item.get("content", "") or "",
                )
            )
        return jobs
