"""Weekly calendar pipeline: discover new pages, research official dates, write calendar."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from . import discover, research

_ROOT = Path(__file__).parent.parent
_PROGRAMS_DB = Path(__file__).parent / "programs.json"


def _load_programs() -> list[dict]:
    with open(_PROGRAMS_DB, encoding="utf-8") as f:
        return json.load(f)


def _save_programs(programs: list[dict]) -> None:
    with open(_PROGRAMS_DB, "w", encoding="utf-8") as f:
        json.dump(programs, f, indent=2)
        f.write("\n")


def _worth_keeping(program: dict, raw: dict, *, new_discovery: bool = False) -> bool:
    if new_discovery:
        # New finds must have a confirmed official deadline
        return bool(raw.get("deadline_confirmed"))
    if raw.get("deadline_confirmed"):
        return True
    if raw.get("confidence") in ("high", "medium"):
        return True
    if raw.get("page_had_useful_info"):
        elig = (raw.get("eligibility") or "").lower()
        if elig and "could not determine" not in elig:
            return True
    return False


def run() -> None:
    load_dotenv(_ROOT / ".env")
    programs = _load_programs()
    curated = [p for p in programs if p.get("source") != "tavily"]
    tavily_kept = [p for p in programs if p.get("source") == "tavily"]
    existing_urls = {p.get("url") for p in programs if p.get("url")}

    candidates = discover.discover(
        existing_urls,
        max_new=int(os.environ.get("DISCOVER_LIMIT", "8")),
    )

    raw_by_slug = research.main(
        programs=curated + tavily_kept + candidates,
        return_results=True,
    )

    # Drop unverified Tavily rows; keep validated discoveries
    validated_tavily = [
        p for p in tavily_kept
        if _worth_keeping(p, raw_by_slug.get(p["slug"], {}))
    ]
    new_validated = []
    existing_slugs = {p["slug"] for p in curated + validated_tavily}
    seen_urls = {p.get("url") for p in curated + validated_tavily if p.get("url")}
    for cand in candidates:
        raw = raw_by_slug.get(cand["slug"], {})
        if not _worth_keeping(cand, raw, new_discovery=True):
            print(f"[pipeline] skip unverified discovery: {cand['name'][:55]}")
            continue
        if cand.get("url") in seen_urls:
            continue
        slug = cand["slug"]
        n = 2
        while slug in existing_slugs:
            slug = f"{cand['slug']}-{n}"
            n += 1
        cand["slug"] = slug
        existing_slugs.add(slug)
        seen_urls.add(cand.get("url"))
        new_validated.append(cand)
        print(f"[pipeline] kept discovery: {cand['name'][:55]}")

    final = curated + validated_tavily + new_validated
    _save_programs(final)
    print(f"[pipeline] programs.json: {len(final)} entries ({len(curated)} curated)")


if __name__ == "__main__":
    run()
