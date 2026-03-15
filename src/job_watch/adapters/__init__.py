"""ATS adapters."""

from .ashby import AshbyAdapter
from .first_party import (
    AdobeJobsAdapter,
    AmazonJobsAdapter,
    AppleJobsAdapter,
    ByteDanceJobsBrowserAdapter,
    GoogleJobsBrowserAdapter,
    LinkedInJobsAdapter,
    MetaJobsBrowserAdapter,
    MicrosoftJobsAdapter,
    NetflixJobsAdapter,
    SalesforceJobsAdapter,
    TeslaJobsBrowserAdapter,
    TikTokJobsAdapter,
    UberJobsAdapter,
)
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .smartrecruiters import SmartRecruitersAdapter
from .workday import WorkdayAdapter

__all__ = [
    "AdobeJobsAdapter",
    "AmazonJobsAdapter",
    "AppleJobsAdapter",
    "AshbyAdapter",
    "ByteDanceJobsBrowserAdapter",
    "GreenhouseAdapter",
    "GoogleJobsBrowserAdapter",
    "LeverAdapter",
    "LinkedInJobsAdapter",
    "MetaJobsBrowserAdapter",
    "MicrosoftJobsAdapter",
    "NetflixJobsAdapter",
    "SalesforceJobsAdapter",
    "SmartRecruitersAdapter",
    "TeslaJobsBrowserAdapter",
    "TikTokJobsAdapter",
    "UberJobsAdapter",
    "WorkdayAdapter",
]
