"""Base adapter implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from ..constants import DEFAULT_USER_AGENT
from ..models import CompanyConfig, JobRecord
from ..time_utils import parse_datetime


class SourceAdapter(ABC):
    """Abstract adapter for a public ATS."""

    ats_kind: str

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, company: CompanyConfig) -> list[JobRecord]:
        """Fetch normalized job records."""

    async def get_json(self, client: httpx.AsyncClient, url: str, *, headers: dict[str, str] | None = None) -> dict:
        """Perform an HTTP GET for JSON data."""

        response = await client.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT, **(headers or {})},
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def parse_date(value: object):
        return parse_datetime(value)
