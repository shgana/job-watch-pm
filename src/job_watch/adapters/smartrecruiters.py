"""SmartRecruiters adapter."""

from __future__ import annotations

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter


class SmartRecruitersAdapter(SourceAdapter):
    """Fetch jobs from the SmartRecruiters postings API."""

    ats_kind = "smartrecruiters"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        identifier = company.company_identifier or company.slug
        url = company.feed_url or f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
        payload = await self.get_json(client, url, headers=company.headers)
        jobs: list[JobRecord] = []
        for item in payload.get("content", []):
            job_id = str(item.get("id", ""))
            location = _format_location(item.get("location") or {})
            apply_url = item.get("applyUrl") or _posting_url(identifier, job_id)
            jobs.append(
                JobRecord(
                    job_key=stable_job_key(company.slug, job_id, item.get("name", ""), apply_url),
                    company_slug=company.slug,
                    company_name=company.name,
                    ats_kind=self.ats_kind,
                    source_job_id=job_id,
                    title=item.get("name", ""),
                    team="",
                    department=(item.get("department") or {}).get("label", ""),
                    location_raw=location,
                    location_normalized=location,
                    posted_at=self.parse_date(item.get("releasedDate")),
                    updated_at=self.parse_date(item.get("releasedDate")),
                    apply_url=apply_url,
                    career_page_url=company.career_url,
                    employment_type=(item.get("typeOfEmployment") or {}).get("label", ""),
                    remote_flag="remote" in location.lower(),
                    description_text=item.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", ""),
                )
            )
        return jobs


def _format_location(location: dict) -> str:
    city = location.get("city", "")
    region = location.get("region", "")
    country = location.get("country", "")
    return ", ".join(part for part in [city, region, country] if part)


def _posting_url(identifier: str, job_id: str) -> str:
    if not job_id:
        return ""
    return f"https://jobs.smartrecruiters.com/{identifier}/{job_id}"
