"""Adapter registry."""

from __future__ import annotations

from .adapters import (
    AshbyAdapter,
    GreenhouseAdapter,
    LeverAdapter,
    SmartRecruitersAdapter,
    WorkdayAdapter,
)
from .adapters.base import SourceAdapter


ADAPTERS: dict[str, SourceAdapter] = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
    "smartrecruiters": SmartRecruitersAdapter(),
    "workday": WorkdayAdapter(),
}


def get_adapter(ats_kind: str) -> SourceAdapter:
    """Return an adapter for the configured ATS kind."""

    try:
        return ADAPTERS[ats_kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported ATS kind: {ats_kind}") from exc
