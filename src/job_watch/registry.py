"""Adapter registry."""

from __future__ import annotations

from .adapters import (
    AdobeJobsAdapter,
    AmazonJobsAdapter,
    AppleJobsAdapter,
    AshbyAdapter,
    ByteDanceJobsBrowserAdapter,
    GreenhouseAdapter,
    GoogleJobsBrowserAdapter,
    LeverAdapter,
    LinkedInJobsAdapter,
    MetaJobsBrowserAdapter,
    MicrosoftJobsAdapter,
    NetflixJobsAdapter,
    SalesforceJobsAdapter,
    SmartRecruitersAdapter,
    TeslaJobsBrowserAdapter,
    TikTokJobsAdapter,
    UberJobsAdapter,
    WorkdayAdapter,
)
from .adapters.base import SourceAdapter


ADAPTERS: dict[str, SourceAdapter] = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "workday": WorkdayAdapter(),
    "adobe_jobs": AdobeJobsAdapter(),
    "amazon_jobs": AmazonJobsAdapter(),
    "apple_jobs": AppleJobsAdapter(),
    "bytedance_jobs_browser": ByteDanceJobsBrowserAdapter(),
    "google_jobs_browser": GoogleJobsBrowserAdapter(),
    "linkedin_jobs": LinkedInJobsAdapter(),
    "meta_jobs_browser": MetaJobsBrowserAdapter(),
    "microsoft_jobs": MicrosoftJobsAdapter(),
    "netflix_jobs": NetflixJobsAdapter(),
    "salesforce_jobs": SalesforceJobsAdapter(),
    "tesla_jobs_browser": TeslaJobsBrowserAdapter(),
    "tiktok_jobs": TikTokJobsAdapter(),
    "uber_jobs": UberJobsAdapter(),
}


def get_adapter(ats_kind: str) -> SourceAdapter:
    """Return an adapter for the configured ATS kind."""

    try:
        return ADAPTERS[ats_kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported ATS kind: {ats_kind}") from exc
