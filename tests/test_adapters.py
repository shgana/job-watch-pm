import asyncio
import json
from pathlib import Path

import httpx

from job_watch.adapters import (
    AshbyAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
)
from job_watch.models import CompanyConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _client_for(payload_name: str) -> httpx.AsyncClient:
    payload = json.loads((FIXTURES / payload_name).read_text(encoding="utf-8"))

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_greenhouse_adapter():
    async def run():
        async with _client_for("greenhouse.json") as client:
            jobs = await GreenhouseAdapter().fetch(
                client,
                CompanyConfig(
                    slug="asana",
                    name="Asana",
                    category="saas",
                    ats_kind="greenhouse",
                    board_token="asana",
                    career_url="https://boards.greenhouse.io/asana",
                ),
            )
        assert jobs[0].title == "Senior Project Manager"
        assert jobs[0].location_raw == "Seattle, WA"

    asyncio.run(run())


def test_lever_adapter():
    async def run():
        async with _client_for("lever.json") as client:
            jobs = await LeverAdapter().fetch(
                client,
                CompanyConfig(
                    slug="reddit",
                    name="Reddit",
                    category="consumer-tech",
                    ats_kind="lever",
                    site="reddit",
                    career_url="https://jobs.lever.co/reddit",
                ),
            )
        assert jobs[0].title == "Business Analyst"
        assert jobs[0].team == "BizOps"

    asyncio.run(run())


def test_ashby_adapter():
    async def run():
        async with _client_for("ashby.json") as client:
            jobs = await AshbyAdapter().fetch(
                client,
                CompanyConfig(
                    slug="openai",
                    name="OpenAI",
                    category="ai",
                    ats_kind="ashby",
                    board_token="openai",
                    career_url="https://jobs.ashbyhq.com/openai",
                ),
            )
        assert "McLean" in jobs[0].location_raw
        assert jobs[0].apply_url.endswith("/apply")

    asyncio.run(run())


def test_smartrecruiters_adapter():
    async def run():
        async with _client_for("smartrecruiters.json") as client:
            jobs = await SmartRecruitersAdapter().fetch(
                client,
                CompanyConfig(
                    slug="wise",
                    name="Wise",
                    category="fintech",
                    ats_kind="smartrecruiters",
                    company_identifier="Wise",
                    career_url="https://jobs.smartrecruiters.com/Wise",
                ),
            )
        assert jobs[0].title == "Project Manager"
        assert "Boston" in jobs[0].location_raw

    asyncio.run(run())


def test_smartrecruiters_adapter_falls_back_to_posting_url():
    async def run():
        payload = {
            "content": [
                {
                    "id": "744000114512232",
                    "name": "Project Manager",
                    "location": {"city": "Boston", "region": "MA", "country": "us"},
                    "department": {"label": "Operations"},
                    "releasedDate": "2026-03-12T00:00:00Z",
                    "typeOfEmployment": {"label": "Full-time"},
                }
            ]
        }

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            jobs = await SmartRecruitersAdapter().fetch(
                client,
                CompanyConfig(
                    slug="wise",
                    name="Wise",
                    category="fintech",
                    ats_kind="smartrecruiters",
                    company_identifier="Wise",
                    career_url="https://jobs.smartrecruiters.com/Wise",
                ),
            )
        assert jobs[0].apply_url == "https://jobs.smartrecruiters.com/Wise/744000114512232"

    asyncio.run(run())


def test_workday_adapter():
    async def run():
        async with _client_for("workday.json") as client:
            jobs = await WorkdayAdapter().fetch(
                client,
                CompanyConfig(
                    slug="okta",
                    name="Okta",
                    category="security",
                    ats_kind="workday",
                    career_url="https://www.okta.com/company/careers/",
                    feed_url="https://wd1.myworkdaysite.com/wday/cxs/okta/OktaCareers/jobs",
                ),
            )
        assert jobs[0].title == "Business Analyst"
        assert jobs[0].apply_url.endswith("JR-1001")

    asyncio.run(run())
