"""First-party career site adapters."""

from __future__ import annotations

import asyncio
import html
import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse, urlunparse

import httpx

from ..matching import stable_job_key
from ..models import CompanyConfig, JobRecord
from .base import SourceAdapter

_WHITESPACE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def _normalize_space(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _strip_tags(value: str) -> str:
    if not value:
        return ""
    return _normalize_space(html.unescape(_TAG_RE.sub(" ", value)))


def _parse_text_date(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = _normalize_space(value).replace("Sept ", "Sep ")
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _extract_json_object_after(text: str, marker: str) -> dict[str, Any] | None:
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    start = text.find("{", marker_index)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                raw = text[start : index + 1]
                return json.loads(raw)
    return None


def _build_record(
    *,
    company: CompanyConfig,
    ats_kind: str,
    source_id: str,
    title: str,
    location: str,
    apply_url: str,
    posted_at: object = None,
    updated_at: object = None,
    team: str = "",
    department: str = "",
    employment_type: str = "",
    description: str = "",
) -> JobRecord:
    location_clean = _normalize_space(location)
    title_clean = _normalize_space(title)
    apply_url_clean = apply_url.strip()
    return JobRecord(
        job_key=stable_job_key(company.slug, source_id, title_clean, apply_url_clean),
        company_slug=company.slug,
        company_name=company.name,
        ats_kind=ats_kind,
        source_job_id=source_id,
        title=title_clean,
        team=_normalize_space(team),
        department=_normalize_space(department),
        location_raw=location_clean,
        location_normalized=location_clean,
        posted_at=SourceAdapter.parse_date(posted_at),
        updated_at=SourceAdapter.parse_date(updated_at if updated_at is not None else posted_at),
        apply_url=apply_url_clean,
        career_page_url=company.career_url,
        employment_type=_normalize_space(employment_type),
        remote_flag="remote" in location_clean.lower(),
        description_text=_strip_tags(description),
    )


class AmazonJobsAdapter(SourceAdapter):
    """Amazon first-party search API adapter."""

    ats_kind = "amazon_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        endpoint = company.request_options.get("search_api_url", "https://amazon.jobs/en/search.json")
        query = company.request_options.get("query", "project manager")
        max_pages = int(company.request_options.get("max_pages", 5))
        page_size = int(company.request_options.get("page_size", 10))
        base_params: dict[str, Any] = {
            "radius": company.request_options.get("radius", "24km"),
            "sort": company.request_options.get("sort", "relevant"),
            "latitude": "",
            "longitude": "",
            "loc_group_id": "",
            "loc_query": company.request_options.get("loc_query", ""),
            "base_query": query,
            "city": "",
            "country": "",
            "region": "",
            "county": "",
            "query_options": "",
            "facets[]": company.request_options.get(
                "facets",
                [
                    "normalized_country_code",
                    "normalized_state_name",
                    "normalized_city_name",
                    "location",
                    "business_category",
                    "category",
                    "schedule_type_id",
                    "employee_class",
                    "normalized_location",
                    "job_function_id",
                    "is_manager",
                    "is_intern",
                ],
            ),
        }
        headers = {
            "Referer": company.listing_url or company.career_url,
            **company.headers,
        }
        jobs: list[JobRecord] = []
        for page in range(max_pages):
            params = dict(base_params)
            params["offset"] = str(page * page_size)
            params["result_limit"] = str(page_size)
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            items = payload.get("jobs", [])
            if not items:
                break
            for item in items:
                source_id = str(item.get("id_icims") or item.get("id") or item.get("job_path") or "")
                title = item.get("title") or item.get("job_title") or ""
                if not source_id or not title:
                    continue
                job_path = item.get("job_path") or ""
                apply_url = urljoin("https://amazon.jobs", job_path) if job_path else company.career_url
                posted_at = _parse_text_date(item.get("posted_date")) or item.get("posted_date")
                team = (item.get("team") or {}).get("title") or (item.get("team") or {}).get("label") or ""
                location = (
                    item.get("normalized_location")
                    or item.get("location")
                    or ", ".join(part for part in [item.get("city"), item.get("state"), item.get("country_code")] if part)
                )
                jobs.append(
                    _build_record(
                        company=company,
                        ats_kind=self.ats_kind,
                        source_id=source_id,
                        title=title,
                        location=location,
                        apply_url=apply_url,
                        posted_at=posted_at,
                        team=team,
                        department=item.get("business_category") or "",
                        employment_type=item.get("employment_type") or "",
                        description=item.get("description") or item.get("description_short") or "",
                    )
                )
            if len(items) < page_size:
                break
        return jobs


class AppleJobsAdapter(SourceAdapter):
    """Apple careers HTML adapter."""

    ats_kind = "apple_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        url = company.listing_url or company.career_url
        response = await client.get(url, headers=company.headers)
        response.raise_for_status()
        content = response.text
        jobs: list[JobRecord] = []
        seen: set[str] = set()
        for match in re.finditer(r'href="(?P<href>/en-us/details/[^"]+)"[^>]*>(?P<title>[^<]+)</a>', content):
            href = html.unescape(match.group("href"))
            if href in seen:
                continue
            seen.add(href)
            title = html.unescape(match.group("title"))
            source_match = re.search(r"/details/([^/]+)/", href)
            source_id = source_match.group(1) if source_match else href
            tail = content[match.end() : match.end() + 1600]
            location_match = re.search(r'id="search-store-name-container-[^"]*">([^<]+)</span>', tail)
            posted_match = re.search(r'class="job-posted-date"[^>]*>([^<]+)</span>', tail)
            team_match = re.search(r'class="team-name[^"]*"[^>]*>([^<]+)</span>', tail)
            posted = _parse_text_date(posted_match.group(1) if posted_match else None)
            jobs.append(
                _build_record(
                    company=company,
                    ats_kind=self.ats_kind,
                    source_id=source_id,
                    title=title,
                    location=location_match.group(1) if location_match else "",
                    apply_url=urljoin("https://jobs.apple.com", href),
                    posted_at=posted,
                    team=team_match.group(1) if team_match else "",
                    description="",
                )
            )
        return jobs


class MicrosoftJobsAdapter(SourceAdapter):
    """Microsoft careers API adapter."""

    ats_kind = "microsoft_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        endpoint = company.request_options.get("search_api_url", "https://apply.careers.microsoft.com/api/pcsx/search")
        domain = company.request_options.get("domain", "microsoft.com")
        query = company.request_options.get("query", "project manager")
        location = company.request_options.get("location", "")
        page_size = int(company.request_options.get("page_size", 10))
        max_pages = int(company.request_options.get("max_pages", 5))
        headers = {
            "Referer": company.listing_url or company.career_url,
            **company.headers,
        }
        jobs: list[JobRecord] = []
        for page in range(max_pages):
            params = {
                "domain": domain,
                "query": query,
                "start": str(page * page_size),
            }
            if location:
                params["location"] = location
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
            positions = payload.get("data", {}).get("positions", [])
            if not positions:
                break
            for item in positions:
                source_id = str(item.get("displayJobId") or item.get("id") or "")
                title = item.get("name") or ""
                if not source_id or not title:
                    continue
                position_url = item.get("positionUrl") or ""
                apply_url = urljoin(company.career_url.rstrip("/") + "/", position_url)
                location_text = ", ".join(item.get("locations") or item.get("standardizedLocations") or [])
                jobs.append(
                    _build_record(
                        company=company,
                        ats_kind=self.ats_kind,
                        source_id=source_id,
                        title=title,
                        location=location_text,
                        apply_url=apply_url,
                        posted_at=item.get("postedTs"),
                        updated_at=item.get("creationTs"),
                        department=item.get("department") or "",
                        employment_type=item.get("workLocationOption") or "",
                        description="",
                    )
                )
            if len(positions) < page_size:
                break
        return jobs


class UberJobsAdapter(SourceAdapter):
    """Uber careers API adapter."""

    ats_kind = "uber_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        endpoint = company.request_options.get(
            "search_api_url",
            "https://www.uber.com/api/loadSearchJobsResults?localeCode=en",
        )
        query = company.request_options.get("query", "project manager")
        page_size = int(company.request_options.get("page_size", 10))
        max_pages = int(company.request_options.get("max_pages", 5))
        headers = {
            "Content-Type": "application/json",
            "x-csrf-token": company.request_options.get("csrf", "x"),
            "Referer": company.listing_url or company.career_url,
            **company.headers,
        }
        jobs: list[JobRecord] = []
        for page in range(max_pages):
            payload = {
                "limit": page_size,
                "page": page,
                "params": {"query": query},
            }
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            items = response.json().get("data", {}).get("results", [])
            if not items:
                break
            for item in items:
                source_id = str(item.get("id") or "")
                title = item.get("title") or ""
                if not source_id or not title:
                    continue
                location = item.get("location") or {}
                location_text = ", ".join(
                    part for part in [location.get("city"), location.get("region"), location.get("countryName")] if part
                )
                jobs.append(
                    _build_record(
                        company=company,
                        ats_kind=self.ats_kind,
                        source_id=source_id,
                        title=title,
                        location=location_text,
                        apply_url=urljoin("https://www.uber.com", f"/careers/list/{source_id}"),
                        posted_at=item.get("creationDate"),
                        updated_at=item.get("updatedDate"),
                        team=item.get("team") or "",
                        department=item.get("department") or "",
                        employment_type=item.get("timeType") or "",
                        description=item.get("description") or "",
                    )
                )
            if len(items) < page_size:
                break
        return jobs


class TikTokJobsAdapter(SourceAdapter):
    """TikTok careers API adapter."""

    ats_kind = "tiktok_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        endpoint = company.request_options.get(
            "search_api_url",
            "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts",
        )
        query = company.request_options.get("query", "project manager")
        page_size = int(company.request_options.get("page_size", 12))
        max_pages = int(company.request_options.get("max_pages", 5))
        payload_base: dict[str, Any] = {
            "keyword": query,
            "job_category_id_list": [],
            "tag_id_list": [],
            "location_code_list": [],
            "subject_id_list": [],
            "recruitment_id_list": [],
            "portal_type": 2,
            "job_function_id_list": [],
            "storefront_id_list": [],
            "portal_entrance": 1,
        }
        headers = {
            "Content-Type": "application/json",
            "website-path": company.request_options.get("website_path", "tiktok"),
            "Referer": company.listing_url or company.career_url,
            "Accept-Language": company.request_options.get("accept_language", "en-US"),
            **company.headers,
        }
        jobs: list[JobRecord] = []
        for page in range(max_pages):
            payload = dict(payload_base)
            payload["limit"] = page_size
            payload["offset"] = page * page_size
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            decoded = response.json()
            if decoded.get("code") not in (0, "0", None):
                raise ValueError(f"unexpected tiktok response code: {decoded.get('code')}")
            items = decoded.get("data", {}).get("job_post_list", [])
            if not items:
                break
            for item in items:
                source_id = str(item.get("id") or "")
                title = item.get("title") or ""
                if not source_id or not title:
                    continue
                city_info = item.get("city_info") or {}
                parent = city_info.get("parent") or {}
                grandparent = parent.get("parent") or {}
                location = ", ".join(
                    value
                    for value in [
                        city_info.get("en_name") or city_info.get("i18n_name"),
                        parent.get("en_name") or parent.get("i18n_name"),
                        grandparent.get("en_name") or grandparent.get("i18n_name"),
                    ]
                    if value
                )
                description = "\n".join(part for part in [item.get("description"), item.get("requirement")] if part)
                jobs.append(
                    _build_record(
                        company=company,
                        ats_kind=self.ats_kind,
                        source_id=source_id,
                        title=title,
                        location=location,
                        apply_url=urljoin("https://lifeattiktok.com", f"/search/{source_id}"),
                        posted_at=((item.get("job_post_info") or {}).get("update_time")),
                        department=((item.get("job_category") or {}).get("en_name") or ""),
                        employment_type=((item.get("recruit_type") or {}).get("en_name") or ""),
                        description=description,
                    )
                )
            if len(items) < page_size:
                break
        return jobs


class AdobeJobsAdapter(SourceAdapter):
    """Adobe careers embedded JSON adapter."""

    ats_kind = "adobe_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        response = await client.get(company.listing_url or company.career_url, headers=company.headers)
        response.raise_for_status()
        content = response.text
        payload = _extract_json_object_after(content, '"eagerLoadRefineSearch"')
        if payload is None:
            raise ValueError("unable to parse adobe search payload")
        items = payload.get("data", {}).get("jobs", [])
        jobs: list[JobRecord] = []
        for item in items:
            source_id = str(item.get("jobSeqNo") or item.get("reqId") or item.get("jobId") or "")
            title = item.get("title") or ""
            if not source_id or not title:
                continue
            location = (
                item.get("cityStateCountry")
                or item.get("location")
                or ", ".join(item.get("multi_location") or [])
                or ", ".join(part for part in [item.get("city"), item.get("state"), item.get("country")] if part)
            )
            jobs.append(
                _build_record(
                    company=company,
                    ats_kind=self.ats_kind,
                    source_id=source_id,
                    title=title,
                    location=location,
                    apply_url=item.get("applyUrl") or company.career_url,
                    posted_at=item.get("postedDate"),
                    department=", ".join(item.get("multi_category") or []),
                    employment_type=item.get("type") or "",
                    description=item.get("descriptionTeaser") or "",
                )
            )
        return jobs


class SalesforceJobsAdapter(SourceAdapter):
    """Salesforce careers HTML adapter."""

    ats_kind = "salesforce_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        base_url = company.listing_url or company.career_url
        query = company.request_options.get("query", "project manager")
        max_pages = int(company.request_options.get("max_pages", 5))
        jobs: list[JobRecord] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            params = {"search": query}
            if page > 1:
                params["page"] = str(page)
            response = await client.get(base_url, params=params, headers=company.headers)
            response.raise_for_status()
            content = response.text
            matches = list(
                re.finditer(
                    r'<p class="card-subtitle">(?P<dept>[^<]*)</p>\s*'
                    r'<h3 class="card-title"><a[^>]+href="(?P<href>/en/jobs/[^"]+)"[^>]*>(?P<title>.*?)</a></h3>',
                    content,
                    re.S,
                )
            )
            if not matches:
                break
            for match in matches:
                href = html.unescape(match.group("href"))
                if href in seen:
                    continue
                seen.add(href)
                title = _strip_tags(match.group("title"))
                source_match = re.search(r"/en/jobs/([^/]+)/", href)
                source_id = source_match.group(1) if source_match else href
                window = content[match.end() : match.end() + 900]
                location_match = re.search(r'<ul class="list-inline locations">.*?<li[^>]*>([^<]+)</li>', window, re.S)
                jobs.append(
                    _build_record(
                        company=company,
                        ats_kind=self.ats_kind,
                        source_id=source_id,
                        title=title,
                        location=location_match.group(1).strip() if location_match else "",
                        apply_url=urljoin("https://careers.salesforce.com", href),
                        department=_strip_tags(match.group("dept")),
                    )
                )
        return jobs


class LinkedInJobsAdapter(SourceAdapter):
    """LinkedIn jobs page adapter for LinkedIn company postings."""

    ats_kind = "linkedin_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        response = await client.get(company.listing_url or company.career_url, headers=company.headers)
        response.raise_for_status()
        content = response.text
        jobs: list[JobRecord] = []
        seen: set[str] = set()
        pattern = re.compile(
            r'href="(?P<href>https://www\.linkedin\.com/jobs/view/[^"]*linkedin-(?P<job_id>\d+)[^"]*)"[^>]*>'
            r'.*?<span class="sr-only">\s*(?P<title>.*?)\s*</span>',
            re.S,
        )
        for match in pattern.finditer(content):
            href = html.unescape(match.group("href"))
            job_id = match.group("job_id")
            if job_id in seen:
                continue
            seen.add(job_id)
            title = _normalize_space(html.unescape(match.group("title")))
            window = content[match.end() : match.end() + 800]
            location_match = re.search(r'class="job-search-card__location">\s*([^<]+)\s*</span>', window)
            posted_match = re.search(r'<time[^>]*datetime="([^"]+)"', window)
            jobs.append(
                _build_record(
                    company=company,
                    ats_kind=self.ats_kind,
                    source_id=job_id,
                    title=title,
                    location=html.unescape(location_match.group(1)) if location_match else "",
                    apply_url=href.split("?")[0],
                    posted_at=posted_match.group(1) if posted_match else None,
                    department="LinkedIn",
                )
            )
        return jobs


class NetflixJobsAdapter(SourceAdapter):
    """Netflix careers adapter using search HTML and official job details API."""

    ats_kind = "netflix_jobs"

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        listing_url = company.listing_url or company.career_url
        query = company.request_options.get("query", "project manager")
        max_jobs = int(company.request_options.get("max_jobs", 25))
        response = await client.get(listing_url, headers=company.headers)
        response.raise_for_status()
        body = html.unescape(response.text)
        job_ids: list[str] = []
        for match in re.findall(r"/job/([0-9]{9,})", body):
            if match not in job_ids:
                job_ids.append(match)
            if len(job_ids) >= max_jobs:
                break
        jobs: list[JobRecord] = []
        if not job_ids:
            return jobs
        for job_id in job_ids:
            detail_url = (
                "https://explore.jobs.netflix.net/api/apply/v2/jobs/"
                f"{job_id}?domain=netflix.com&query={quote_plus(query)}"
            )
            detail_response = await client.get(detail_url, headers={"Referer": listing_url, **company.headers})
            detail_response.raise_for_status()
            item = detail_response.json()
            title = item.get("name") or item.get("posting_name") or ""
            if not title:
                continue
            apply_url = item.get("canonicalPositionUrl") or urljoin(
                "https://explore.jobs.netflix.net",
                f"/careers/job/{job_id}?microsite=netflix.com",
            )
            jobs.append(
                _build_record(
                    company=company,
                    ats_kind=self.ats_kind,
                    source_id=str(item.get("display_job_id") or job_id),
                    title=title,
                    location=item.get("location") or ", ".join(item.get("locations") or []),
                    apply_url=apply_url,
                    posted_at=item.get("t_create"),
                    updated_at=item.get("t_update"),
                    department=item.get("department") or "",
                    employment_type=item.get("type") or "",
                    description=item.get("job_description") or "",
                )
            )
        return jobs


class BrowserSourceAdapter(SourceAdapter):
    """Playwright-backed first-party adapter base class."""

    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        del client  # Browser-backed adapters do not use the shared httpx client.
        return await asyncio.to_thread(self._fetch_with_browser, company)

    def _fetch_with_browser(self, company: CompanyConfig) -> list[JobRecord]:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional runtime env
            raise RuntimeError("playwright is required for browser-backed sources") from exc

        jobs_data: list[dict[str, str]] = []
        max_pages = int(company.request_options.get("max_pages", 1))
        wait_ms = int(company.request_options.get("wait_ms", 3500))
        listing_url = company.listing_url or company.career_url
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                for page_number in range(1, max_pages + 1):
                    target_url = self._page_url(listing_url, page_number)
                    page.goto(target_url, wait_until="networkidle", timeout=90000)
                    page.wait_for_timeout(wait_ms)
                    jobs_data.extend(self._extract_jobs(page))
            finally:
                browser.close()

        deduped: dict[str, dict[str, str]] = {}
        for item in jobs_data:
            source_id = item.get("source_id") or item.get("apply_url") or item.get("title", "")
            if source_id and source_id not in deduped:
                deduped[source_id] = item
        jobs: list[JobRecord] = []
        for source_id, item in deduped.items():
            if not item.get("title") or not item.get("apply_url"):
                continue
            jobs.append(
                _build_record(
                    company=company,
                    ats_kind=self.ats_kind,
                    source_id=source_id,
                    title=item.get("title", ""),
                    location=item.get("location", ""),
                    apply_url=item.get("apply_url", ""),
                    posted_at=item.get("posted_at"),
                    updated_at=item.get("updated_at"),
                    team=item.get("team", ""),
                    department=item.get("department", ""),
                    employment_type=item.get("employment_type", ""),
                    description=item.get("description", ""),
                )
            )
        if not jobs:
            raise ValueError("no jobs found from browser-backed source")
        return jobs

    def _page_url(self, listing_url: str, page_number: int) -> str:
        if page_number <= 1:
            return listing_url
        parsed = urlparse(listing_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["page"] = [str(page_number)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def _extract_jobs(self, page: Any) -> list[dict[str, str]]:  # pragma: no cover - subclassed
        raise NotImplementedError


class GoogleJobsBrowserAdapter(BrowserSourceAdapter):
    """Google careers browser adapter."""

    ats_kind = "google_jobs_browser"

    def _extract_jobs(self, page: Any) -> list[dict[str, str]]:
        rows = page.eval_on_selector_all(
            "div.VfPpkd-WsjYwc",
            """
            (cards) => cards.map((card) => {
              const title = card.querySelector("h3")?.textContent?.trim() || "";
              const anchor = card.querySelector('a.WpHeLc[href]') || card.querySelector('a[href]');
              const href = anchor?.getAttribute("href") || "";
              const link = href ? new URL(href, window.location.href).href : "";
              const location = card.querySelector(".pwO9Dc")?.textContent?.trim() || "";
              return { title, apply_url: link, location };
            }).filter((row) => row.title && row.apply_url)
            """,
        )
        jobs: list[dict[str, str]] = []
        for row in rows:
            apply_url = row.get("apply_url", "").replace("/results/jobs/results/", "/results/")
            source_match = re.search(r"/results/([0-9]+)-", apply_url)
            jobs.append(
                {
                    "source_id": source_match.group(1) if source_match else apply_url,
                    "title": row.get("title", ""),
                    "apply_url": apply_url,
                    "location": row.get("location", ""),
                }
            )
        return jobs


class MetaJobsBrowserAdapter(BrowserSourceAdapter):
    """Meta careers browser adapter."""

    ats_kind = "meta_jobs_browser"

    def _extract_jobs(self, page: Any) -> list[dict[str, str]]:
        rows = page.eval_on_selector_all(
            'a[href*="/profile/job_details/"]',
            """
            (links) => links.map((link) => {
              const href = link.href || "";
              const title = link.querySelector("h3")?.textContent?.trim()
                || (link.textContent || "").trim();
              return { href, title };
            }).filter((row) => row.href && row.title)
            """,
        )
        jobs: list[dict[str, str]] = []
        for row in rows:
            source_match = re.search(r"/job_details/([0-9]+)", row.get("href", ""))
            title = _normalize_space(row.get("title", "").split("⋅")[0])
            jobs.append(
                {
                    "source_id": source_match.group(1) if source_match else row.get("href", ""),
                    "title": title,
                    "apply_url": row.get("href", ""),
                    "location": row.get("title", ""),
                }
            )
        return jobs


class ByteDanceJobsBrowserAdapter(BrowserSourceAdapter):
    """ByteDance careers browser adapter."""

    ats_kind = "bytedance_jobs_browser"

    def _extract_jobs(self, page: Any) -> list[dict[str, str]]:
        rows = page.eval_on_selector_all(
            'a[href*="/experienced/position/"][href*="/detail"]',
            """
            (links) => links.map((link) => ({
              href: link.href || "",
              title: (link.textContent || "").trim(),
            })).filter((row) => row.href && row.title)
            """,
        )
        jobs: list[dict[str, str]] = []
        for row in rows:
            source_match = re.search(r"/position/([0-9]+)/detail", row.get("href", ""))
            title_text = _normalize_space(row.get("title", ""))
            title = title_text.split("职位 ID")[0].strip() if "职位 ID" in title_text else title_text
            jobs.append(
                {
                    "source_id": source_match.group(1) if source_match else row.get("href", ""),
                    "title": title,
                    "apply_url": row.get("href", ""),
                    "location": title_text,
                }
            )
        return jobs


class TeslaJobsBrowserAdapter(BrowserSourceAdapter):
    """Tesla careers browser adapter."""

    ats_kind = "tesla_jobs_browser"

    def _extract_jobs(self, page: Any) -> list[dict[str, str]]:
        rows = page.eval_on_selector_all(
            "a[href]",
            """
            (links) => links
              .map((link) => ({ href: link.href || "", title: (link.textContent || "").trim() }))
              .filter((row) => (
                (row.href.includes("/careers/search/job/") || row.href.includes("/careers/list/"))
                && row.title
              ))
            """,
        )
        jobs: list[dict[str, str]] = []
        for row in rows:
            href = row.get("href", "")
            title = _normalize_space(row.get("title", ""))
            source_match = re.search(r"/(\\d+)(?:$|\\?)", href)
            source_id = source_match.group(1) if source_match else href
            jobs.append(
                {
                    "source_id": source_id,
                    "title": title,
                    "apply_url": href,
                    "location": "",
                }
            )
        return jobs
