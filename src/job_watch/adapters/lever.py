"""Lever adapter."""

from __future__ import annotations

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter


class LeverAdapter(SourceAdapter):
    """Fetch jobs from the Lever postings API."""

    ats_kind = "lever"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        site = company.site or company.slug
        url = company.feed_url or f"https://api.lever.co/v0/postings/{site}?mode=json"
        payload = await self.get_json(client, url, headers=company.headers)
        jobs: list[JobRecord] = []
        for item in payload:
            categories = item.get("categories", {})
            location = categories.get("location", "") or ""
            jobs.append(
                JobRecord(
                    job_key=stable_job_key(company.slug, str(item.get("id", "")), item.get("text", ""), item.get("hostedUrl", "")),
                    company_slug=company.slug,
                    company_name=company.name,
                    ats_kind=self.ats_kind,
                    source_job_id=str(item.get("id", "")),
                    title=item.get("text", ""),
                    team=categories.get("team", "") or "",
                    department="",
                    location_raw=location,
                    location_normalized=location,
                    posted_at=self.parse_date(item.get("createdAt")),
                    updated_at=self.parse_date(item.get("updatedAt") or item.get("createdAt")),
                    apply_url=item.get("hostedUrl", ""),
                    career_page_url=company.career_url,
                    employment_type=categories.get("commitment", "") or "",
                    remote_flag="remote" in location.lower(),
                    description_text=item.get("descriptionPlain", "") or "",
                )
            )
        return jobs
