from datetime import datetime, timezone
from pathlib import Path

from .logger import RunResult

APPLICATIONS_PATH = Path(__file__).parent.parent / "data" / "applications.md"


def update(results: list[RunResult]) -> None:
    APPLICATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing
    existing_lines: list[str] = []
    total_existing = 0
    if APPLICATIONS_PATH.exists():
        existing_lines = APPLICATIONS_PATH.read_text(encoding="utf-8").splitlines()
        for line in existing_lines:
            if line.startswith("| OPP-"):
                total_existing += 1

    new_rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for r in results:
        if r.outcome in ("submitted", "essay_saved", "semi_queued"):
            status_badge = {
                "submitted": "submitted",
                "essay_saved": "essay_pending",
                "semi_queued": "semi_apply",
            }.get(r.outcome, r.outcome)
            row = (
                f"| {r.opportunity_id} | {now} | "
                f"[{r.title[:50]}]({r.url}) | "
                f"{r.application_type} | "
                f"{r.award_value or '—'} | "
                f"{status_badge} | "
                f"{r.notes[:60] if r.notes else '—'} |"
            )
            new_rows.append(row)

    total_new = len(new_rows)
    total = total_existing + total_new
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

    # Preserve existing data rows
    existing_rows = [l for l in existing_lines if l.startswith("| OPP-")]

    all_rows = existing_rows + new_rows
    content = header + "\n".join(all_rows) + "\n"
    APPLICATIONS_PATH.write_text(content, encoding="utf-8")
    print(f"[applications_writer] Updated applications.md ({total} total entries)")
