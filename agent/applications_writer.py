import re
from datetime import datetime, timezone
from pathlib import Path

from .logger import RunResult

APPLICATIONS_PATH = Path(__file__).parent.parent / "outputs" / "applications.md"
_MD_URL = re.compile(r"\]\((https?://[^)]+)\)")


def _row_url(line: str) -> str:
    match = _MD_URL.search(line or "")
    return match.group(1) if match else ""


def update(results: list[RunResult]) -> None:
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    existing_lines: list[str] = []
    if APPLICATIONS_PATH.exists():
        existing_lines = APPLICATIONS_PATH.read_text(encoding="utf-8").splitlines()

    new_by_url: dict[str, str] = {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in results:
        if r.outcome in ("submitted", "yours_manual", "tracked"):
            status_badge = {
                "submitted": "submitted",
                "yours_manual": "yours (elite)",
                "tracked": "needs you / tracked",
            }.get(r.outcome, r.outcome)
            row = (
                f"| {r.opportunity_id} | {now} | "
                f"[{r.title[:50]}]({r.url}) | "
                f"{r.application_type} | "
                f"{r.award_value or '—'} | "
                f"{status_badge} | "
                f"{r.notes[:80] if r.notes else '—'} |"
            )
            new_by_url[r.url] = row

    existing_rows = [l for l in existing_lines if l.startswith("| OPP-")]
    merged: list[str] = []
    seen_urls: set[str] = set()
    for line in existing_rows:
        url = _row_url(line)
        if url and url in new_by_url:
            merged.append(new_by_url[url])
            seen_urls.add(url)
        else:
            merged.append(line)
            if url:
                seen_urls.add(url)
    for url, row in new_by_url.items():
        if url not in seen_urls:
            merged.append(row)

    total = len(merged)
    updated_at = datetime.now(timezone.utc).isoformat()

    header = f"""# Application Log

_Last updated: {updated_at} | Total tracked: {total}_

## Summary
- Submitted (automated): see rows marked `submitted`
- Essay Pending: see rows marked `essay_pending`
- Semi-Apply Queue: see rows marked `semi_apply`

## Applications

| ID | Date | Opportunity | Type | Award | Status | Notes |
|----|------|-------------|------|-------|--------|-------|
"""

    content = header + "\n".join(merged) + "\n"
    APPLICATIONS_PATH.write_text(content, encoding="utf-8")
    print(f"[applications_writer] Updated applications.md ({total} total entries)")
