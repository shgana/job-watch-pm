import asyncio
import json

import httpx

from job_watch.adapters import (
    AdobeJobsAdapter,
    AmazonJobsAdapter,
    AppleJobsAdapter,
    LinkedInJobsAdapter,
    MicrosoftJobsAdapter,
    NetflixJobsAdapter,
    SalesforceJobsAdapter,
    TikTokJobsAdapter,
    UberJobsAdapter,
)
from job_watch.models import CompanyConfig


def test_amazon_adapter_paginates():
    async def run():
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if "offset=0" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "jobs": [
                            {
                                "id_icims": 3171930,
                                "job_path": "/en/jobs/3171930/project-manager",
                                "title": "Project Manager",
                                "normalized_location": "Seattle, WA, USA",
                                "posted_date": "Feb 18, 2026",
                                "description": "Lead projects",
                            }
                        ]
                    },
                )
            return httpx.Response(200, json={"jobs": []})

        company = CompanyConfig(
            slug="amazon",
            name="Amazon",
            category="tech",
            ats_kind="amazon_jobs",
            career_url="https://amazon.jobs/en/",
            listing_url="https://amazon.jobs/en/search?base_query=project%20manager",
            request_options={"page_size": 1, "max_pages": 2},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await AmazonJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].title == "Project Manager"
        assert jobs[0].apply_url.endswith("/en/jobs/3171930/project-manager")
        assert calls["count"] >= 2

    asyncio.run(run())


def test_microsoft_adapter_reads_positions():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            parsed = dict(request.url.params)
            start = parsed.get("start", "0")
            if start != "0":
                return httpx.Response(200, json={"data": {"positions": []}})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "positions": [
                            {
                                "id": 1970393556627455,
                                "displayJobId": "200007562",
                                "name": "Project Manager",
                                "locations": ["Redmond, WA, United States"],
                                "postedTs": 1769950800,
                                "creationTs": 1763583917,
                                "department": "PMO",
                                "workLocationOption": "onsite",
                                "positionUrl": "/careers/job/1970393556627455",
                            }
                        ]
                    }
                },
            )

        company = CompanyConfig(
            slug="microsoft",
            name="Microsoft",
            category="tech",
            ats_kind="microsoft_jobs",
            career_url="https://apply.careers.microsoft.com/careers",
            listing_url="https://apply.careers.microsoft.com/careers/v2/search",
            request_options={"query": "project manager", "max_pages": 2},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await MicrosoftJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "200007562"
        assert "Redmond" in jobs[0].location_raw

    asyncio.run(run())


def test_uber_adapter_builds_apply_url():
    async def run():
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "results": [
                            {
                                "id": 152341,
                                "title": "Lead Project Manager, Auto Insurance Forms",
                                "description": "Manage forms",
                                "department": "Legal",
                                "team": "CLO",
                                "location": {
                                    "city": "San Francisco",
                                    "region": "California",
                                    "countryName": "United States",
                                },
                                "creationDate": "2025-12-15T20:37:00.000Z",
                                "updatedDate": "2026-01-01T00:00:00.000Z",
                                "timeType": "Full-time",
                            }
                        ]
                    }
                },
            )

        company = CompanyConfig(
            slug="uber",
            name="Uber",
            category="tech",
            ats_kind="uber_jobs",
            career_url="https://www.uber.com/us/en/careers/",
            listing_url="https://www.uber.com/us/en/careers/list/?query=project%20manager",
            request_options={"query": "project manager", "max_pages": 1},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await UberJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].apply_url.endswith("/careers/list/152341")
        assert jobs[0].team == "CLO"

    asyncio.run(run())


def test_tiktok_adapter_reads_job_posts():
    async def run():
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "job_post_list": [
                            {
                                "id": "7543927573417265426",
                                "title": "Global Legal Compliance Project Manager",
                                "description": "Compliance work",
                                "requirement": "5+ years",
                                "city_info": {
                                    "en_name": "New York",
                                    "parent": {"en_name": "New York", "parent": {"en_name": "United States"}},
                                },
                                "job_category": {"en_name": "Operations"},
                                "recruit_type": {"en_name": "Regular"},
                                "job_post_info": {"update_time": "2026-03-10T00:00:00Z"},
                            }
                        ]
                    },
                },
            )

        company = CompanyConfig(
            slug="tiktok",
            name="TikTok",
            category="tech",
            ats_kind="tiktok_jobs",
            career_url="https://lifeattiktok.com/",
            listing_url="https://lifeattiktok.com/search?keyword=project%20manager",
            request_options={"query": "project manager", "max_pages": 1},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await TikTokJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].apply_url.endswith("/search/7543927573417265426")
        assert jobs[0].employment_type == "Regular"

    asyncio.run(run())


def test_adobe_adapter_parses_embedded_payload():
    async def run():
        embedded = {
            "status": 200,
            "hits": 1,
            "totalHits": 1,
            "data": {
                "jobs": [
                    {
                        "jobSeqNo": "ADOBUSR162296EXTERNALENUS",
                        "reqId": "R162296",
                        "title": "Project Manager",
                        "cityStateCountry": "Tokyo, Tokyo, Japan",
                        "postedDate": "2025-11-19T00:00:00.000+0000",
                        "applyUrl": "https://adobe.wd5.myworkdayjobs.com/job/Tokyo/Project-Manager_R162296/apply",
                        "multi_category": ["Sales"],
                        "type": "Full time",
                        "descriptionTeaser": "Lead projects.",
                    }
                ]
            },
            "eid": "abc",
        }
        html_payload = f'<script>window.phApp={{"eagerLoadRefineSearch":{json.dumps(embedded)}}};</script>'

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html_payload)

        company = CompanyConfig(
            slug="adobe",
            name="Adobe",
            category="tech",
            ats_kind="adobe_jobs",
            career_url="https://careers.adobe.com/us/en/",
            listing_url="https://careers.adobe.com/us/en/search-results?keywords=project%20manager",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await AdobeJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "ADOBUSR162296EXTERNALENUS"
        assert jobs[0].title == "Project Manager"

    asyncio.run(run())


def test_salesforce_adapter_parses_card_html():
    async def run():
        html_payload = """
<div class="card card-job">
  <div class="card-body">
    <p class="card-subtitle">Customer Success</p>
    <h3 class="card-title"><a class="stretched-link js-view-job" href="/en/jobs/jr326284/salesforce-project-manager/">Salesforce Project Manager</a></h3>
    <ul class="list-inline job-meta"><li class="list-inline-item"><ul class="list-inline locations"><li class="list-inline-item">United States - Remote</li></ul></li></ul>
  </div>
</div>
        """

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html_payload)

        company = CompanyConfig(
            slug="salesforce",
            name="Salesforce",
            category="tech",
            ats_kind="salesforce_jobs",
            career_url="https://careers.salesforce.com/en/jobs/",
            listing_url="https://careers.salesforce.com/en/jobs/",
            request_options={"query": "project manager", "max_pages": 1},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await SalesforceJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "jr326284"
        assert "Remote" in jobs[0].location_raw

    asyncio.run(run())


def test_linkedin_adapter_parses_job_cards():
    async def run():
        html_payload = """
<a href="https://www.linkedin.com/jobs/view/transformation-project-manager-global-talent-organization-at-linkedin-4371204227?position=1">
  <span class="sr-only">Transformation Project Manager, Global Talent Organization</span>
</a>
<span class="job-search-card__location">Sunnyvale, CA</span>
<time datetime="2026-03-11"></time>
        """

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html_payload)

        company = CompanyConfig(
            slug="linkedin",
            name="LinkedIn",
            category="tech",
            ats_kind="linkedin_jobs",
            career_url="https://careers.linkedin.com/",
            listing_url="https://www.linkedin.com/jobs/search/?keywords=project%20manager&f_C=1337",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await LinkedInJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "4371204227"
        assert jobs[0].title.startswith("Transformation Project Manager")

    asyncio.run(run())


def test_netflix_adapter_uses_detail_api():
    async def run():
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/careers"):
                return httpx.Response(200, text='{"jobs":["/job/790314815900"]}')
            if "/api/apply/v2/jobs/790314815900" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "name": "Project Manager- Ads Marketing [EMEA]",
                        "display_job_id": "JR39458",
                        "location": "London,United Kingdom",
                        "department": "Marketing",
                        "type": "ATS",
                        "t_create": 1773360000,
                        "t_update": 1773419658,
                        "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790314815900?microsite=netflix.com",
                        "job_description": "<p>Lead EMEA projects</p>",
                    },
                )
            return httpx.Response(404)

        company = CompanyConfig(
            slug="netflix",
            name="Netflix",
            category="tech",
            ats_kind="netflix_jobs",
            career_url="https://jobs.netflix.com/",
            listing_url="https://explore.jobs.netflix.net/careers?query=project%20manager",
            request_options={"query": "project manager", "max_jobs": 5},
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await NetflixJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "JR39458"
        assert jobs[0].apply_url.startswith("https://explore.jobs.netflix.net/careers/job/")

    asyncio.run(run())


def test_apple_adapter_parses_search_html():
    async def run():
        html_payload = """
<h3><a href="/en-us/details/200647718-0157/construction-project-manager?team=CORSV">Construction Project Manager</a></h3>
<span class="team-name mt-0">Corporate Functions</span>
<span class="job-posted-date">Feb 18, 2026</span>
<span id="search-store-name-container-1">Austin</span>
        """

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=html_payload)

        company = CompanyConfig(
            slug="apple",
            name="Apple",
            category="tech",
            ats_kind="apple_jobs",
            career_url="https://jobs.apple.com/en-us/search",
            listing_url="https://jobs.apple.com/en-us/search?search=project%20manager",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await AppleJobsAdapter().fetch(client, company)
        assert len(jobs) == 1
        assert jobs[0].source_job_id == "200647718-0157"
        assert jobs[0].location_raw == "Austin"

    asyncio.run(run())
