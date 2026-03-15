"""Workday-style public feed adapter."""

from __future__ import annotations

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter


class WorkdayAdapter(SourceAdapter):
    """Fetch jobs from Workday-style JSON feeds."""

    ats_kind = "workday"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        if not company.feed_url:
            raise ValueError(f"Workday source {company.slug} requires feed_url")
        try:
            payload = await self.get_json(client, company.feed_url, headers=company.headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {400, 405, 422}:
                raise
            response = await client.post(
                company.feed_url,
                headers={"Content-Type": "application/json", **company.headers},
                json=company.request_options.get("post_body", {}),
            )
            response.raise_for_status()
            payload = response.json()
        items = payload.get("jobPostings") or payload.get("positions") or payload.get("jobs") or []
        jobs: list[JobRecord] = []
        for item in items:
            location = (
                item.get("locationsText")
                or item.get("location")
                or " | ".join(item.get("bulletFields", []))
            )
            external_path = item.get("externalPath", "")
            if external_path.startswith("/"):
                apply_url = company.career_url.rstrip("/") + external_path
            else:
                apply_url = item.get("applyUrl", "") or external_path or company.career_url
            jobs.append(
                JobRecord(
                    job_key=stable_job_key(company.slug, str(item.get("bulletFields", "")) + str(item.get("title", "")), item.get("title", ""), apply_url),
                    company_slug=company.slug,
                    company_name=company.name,
                    ats_kind=self.ats_kind,
                    source_job_id=str(item.get("externalPath", "") or item.get("id", "") or item.get("title", "")),
                    title=item.get("title", ""),
                    team="",
                    department=item.get("jobFamily", "") or "",
                    location_raw=location,
                    location_normalized=location,
                    posted_at=self.parse_date(item.get("postedOn") or item.get("postedOnDate")),
                    updated_at=self.parse_date(item.get("postedOn") or item.get("postedOnDate")),
                    apply_url=apply_url,
                    career_page_url=company.career_url,
                    employment_type=item.get("timeType", "") or "",
                    remote_flag="remote" in location.lower(),
                    description_text=item.get("jobDescription", "") or "",
                )
            )
        return jobs
