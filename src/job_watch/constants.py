"""Shared constants for Job Watch."""

SHEET_COLUMNS = [
    "job_key",
    "status",
    "company",
    "title",
    "location",
    "metro",
    "freshness_status",
    "posted_at",
    "discovered_at",
    "apply_url",
    "career_page_url",
    "source",
    "notes",
    "manual_priority",
    "last_seen_at",
]

DEFAULT_USER_AGENT = "job-watch/0.1 (+https://github.com/actions)"
TERMINAL_TRACKER_STATUSES = {"applied", "archived", "rejected"}

FAANG_PLUS_TARGET_SLUGS = (
    "amazon",
    "apple",
    "google",
    "meta",
    "netflix",
    "microsoft",
    "nvidia",
    "tesla",
    "uber",
    "airbnb",
    "linkedin",
    "salesforce",
    "adobe",
    "openai",
    "anthropic",
    "bytedance",
    "tiktok",
)
