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


def run() -> None:
    load_dotenv(_ROOT / ".env")
    programs = _load_programs()
    existing_urls = {p.get("url") for p in programs if p.get("url")}
    existing_slugs = {p.get("slug") for p in programs}

    new_rows = discover.discover(existing_urls, max_new=int(os.environ.get("DISCOVER_LIMIT", "12")))
    added = 0
    for row in new_rows:
        slug = row["slug"]
        n = 2
        while slug in existing_slugs:
            slug = f"{row['slug']}-{n}"
            n += 1
        row["slug"] = slug
        existing_slugs.add(slug)
        programs.append(row)
        added += 1
    if added:
        _save_programs(programs)
        print(f"[pipeline] saved {added} discovered programs to programs.json")

    research.main(programs=programs)


if __name__ == "__main__":
    run()
