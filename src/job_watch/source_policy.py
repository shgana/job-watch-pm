"""Official-source policy validation helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import CompanyConfig

ALLOWED_SOURCE_POLICIES = {"company_site", "ats_redirect"}
ATS_REDIRECT_KINDS = {"greenhouse", "ashby", "lever", "smartrecruiters", "workday"}
ALLOWED_ATS_REDIRECT_DOMAINS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "api.ashbyhq.com",
    "jobs.lever.co",
    "api.lever.co",
    "jobs.smartrecruiters.com",
    "api.smartrecruiters.com",
    "myworkdayjobs.com",
    "wd1.myworkdaysite.com",
    "wd3.myworkdaysite.com",
    "wd5.myworkdaysite.com",
    "wd5.myworkdayjobs.com",
}
DISALLOWED_AGGREGATOR_DOMAINS = {
    "linkedin.com",
    "www.linkedin.com",
    "indeed.com",
    "www.indeed.com",
    "glassdoor.com",
    "www.glassdoor.com",
    "ziprecruiter.com",
    "www.ziprecruiter.com",
    "monster.com",
    "www.monster.com",
}


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _base_domain(host: str) -> str:
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def _domain_matches(host: str, reference: str) -> bool:
    if host == reference:
        return True
    return host.endswith("." + reference)


def _is_allowed_ats_host(host: str) -> bool:
    if host in ALLOWED_ATS_REDIRECT_DOMAINS:
        return True
    return any(host.endswith("." + domain) for domain in ALLOWED_ATS_REDIRECT_DOMAINS)


def is_disallowed_aggregator_url(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    if host in DISALLOWED_AGGREGATOR_DOMAINS:
        return True
    return any(host.endswith("." + domain) for domain in DISALLOWED_AGGREGATOR_DOMAINS)


def _is_disallowed_for_company(url: str, company: CompanyConfig) -> bool:
    host = _host(url)
    if company.slug == "linkedin" and host.endswith("linkedin.com"):
        return False
    return is_disallowed_aggregator_url(url)


def validate_company_source_policy(company: CompanyConfig) -> list[str]:
    """Return policy violations for one company source."""

    errors: list[str] = []
    policy = company.source_policy or (
        "ats_redirect" if company.ats_kind in ATS_REDIRECT_KINDS else "company_site"
    )
    if policy not in ALLOWED_SOURCE_POLICIES:
        errors.append(f"invalid source_policy '{policy}'")
        return errors

    official_url = company.official_career_site_url or company.career_url
    if not official_url:
        errors.append("missing official_career_site_url")
        return errors
    if _is_disallowed_for_company(official_url, company):
        errors.append("official_career_site_url uses a disallowed aggregator domain")
        return errors

    official_host = _host(official_url)
    official_base = _base_domain(official_host)
    brand_token = company.slug.split("-")[0]
    candidate_urls = [company.career_url, company.listing_url or "", company.feed_url or ""]
    for url in candidate_urls:
        if not url:
            continue
        if _is_disallowed_for_company(url, company):
            errors.append(f"disallowed aggregator source url: {url}")
            continue
        host = _host(url)
        if not host:
            errors.append(f"invalid source url: {url}")
            continue
        if policy == "company_site":
            brand_match = brand_token and brand_token in host and brand_token in official_host
            if not _domain_matches(host, official_base) and not brand_match:
                errors.append(
                    "company_site source must stay on company domain "
                    f"(got {host}, expected {official_base})"
                )
        elif policy == "ats_redirect":
            if not (_domain_matches(host, official_base) or _is_allowed_ats_host(host)):
                errors.append(
                    "ats_redirect source must be company domain or approved ATS host "
                    f"(got {host})"
                )
    return errors


_DIRECT_APPLY_RE = re.compile(r"/(apply|jobapply|application)(?:/|$)")


def looks_like_direct_apply_url(url: str) -> bool:
    """Best-effort guard for direct apply-submit links."""

    parsed = urlparse(url)
    path = parsed.path.lower()
    if not path:
        return False
    if _DIRECT_APPLY_RE.search(path):
        if "/job/" in path or "/jobs/" in path or "/position/" in path:
            return False
        return True
    return False
