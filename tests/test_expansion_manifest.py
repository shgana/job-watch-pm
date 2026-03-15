from pathlib import Path

from job_watch.config import load_companies

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def test_expansion_manifest_exists_and_has_50_slugs():
    path = Path(__file__).resolve().parents[1] / "config" / "expansion_candidates.toml"
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    slugs = payload.get("slugs", [])
    assert len(slugs) == 50
    assert len(set(slugs)) == 50


def test_expansion_manifest_slugs_are_present_and_enabled():
    path = Path(__file__).resolve().parents[1] / "config" / "expansion_candidates.toml"
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    target_slugs = payload.get("slugs", [])
    companies = {company.slug: company for company in load_companies()}

    missing = [slug for slug in target_slugs if slug not in companies]
    assert missing == []

    disabled = [slug for slug in target_slugs if not companies[slug].enabled]
    assert disabled == []
