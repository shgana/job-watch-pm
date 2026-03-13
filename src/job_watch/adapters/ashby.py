"""Ashby adapter."""

from __future__ import annotations

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter


class AshbyAdapter(SourceAdapter):
    """Fetch jobs from the Ashby public job board API."""

    ats_kind = "ashby"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        board_token = company.board_token or company.slug
        url = company.feed_url or f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
        payload = await self.get_json(client, url, headers=company.headers)
        jobs: list[JobRecord] = []
        for item in payload.get("jobs", []):
            if item.get("isListed") is False:
                continue
            secondary = [entry.get("location", "") for entry in item.get("secondaryLocations", [])]
            primary = item.get("location", "") or _join_address(item.get("address", {}))
            combined = " | ".join(part for part in [primary, *secondary] if part)
            jobs.append(
                JobRecord(
                    job_key=stable_job_key(company.slug, item.get("jobUrl", ""), item.get("title", ""), item.get("applyUrl", "")),
                    company_slug=company.slug,
                    company_name=company.name,
                    ats_kind=self.ats_kind,
                    source_job_id=item.get("jobUrl", ""),
                    title=item.get("title", ""),
                    team=item.get("team", "") or "",
                    department=item.get("department", "") or "",
                    location_raw=combined,
                    location_normalized=combined,
                    posted_at=self.parse_date(item.get("publishedAt")),
                    updated_at=self.parse_date(item.get("publishedAt")),
                    apply_url=item.get("applyUrl", "") or item.get("jobUrl", ""),
                    career_page_url=company.career_url,
                    employment_type=item.get("employmentType", "") or "",
                    remote_flag=bool(item.get("isRemote")) or item.get("workplaceType") == "Remote",
                    description_text=item.get("descriptionPlain", "") or "",
                )
            )
        return jobs


def _join_address(address: dict) -> str:
    postal = address.get("postalAddress", {})
    parts = [
        postal.get("addressLocality", ""),
        postal.get("addressRegion", ""),
        postal.get("addressCountry", ""),
    ]
    return ", ".join(part for part in parts if part)
