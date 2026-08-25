"""
calendar_agent/research.py

Deep pre-research pipeline. Runs once manually to research known programs,
confirm 2026-2027 deadlines from official pages, and produce:
  - outputs/program_calendar.json  (calendar the main agent checks each run)
  - outputs/program_research/{slug}.md  (per-program research docs)

Usage:
    python -m calendar_agent.research

Takes ~15-20 minutes. Requires ANTHROPIC_API_KEY in .env or environment.
Refresh monthly: re-run and re-commit the outputs.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from .scraper import fetch_page

_ROOT = Path(__file__).parent.parent
_PROGRAMS_DB = Path(__file__).parent / "programs.json"
_CALENDAR_OUTPUT = _ROOT / "outputs" / "program_calendar.json"
_CALENDAR_MD = _ROOT / "outputs" / "CALENDAR.md"
_RESEARCH_DIR = _ROOT / "outputs" / "program_research"

_RESEARCH_MODEL = "claude-sonnet-4-5-20251015"
_API_DELAY_SECONDS = 2


def _build_research_prompt(program: dict, page_content: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    has_content = bool(page_content) and page_content != "(page loaded but contained no readable text)"
    content_block = page_content if has_content else "(could not fetch)"
    no_content_note = "" if has_content else "\n\nNOTE: Page could not be fetched. Research from program metadata only."

    return f"""You are researching scholarship and internship programs for a high school student applying in the 2026-2027 cycle. Today is {today}.

Program metadata:
  Name: {program['name']}
  URL: {program['url']}
  Type: {program.get('type', 'unknown')}
  Typical application open: {program.get('typical_open', 'unknown')}
  Typical deadline: {program.get('typical_deadline', 'unknown')}
  Known award: {program.get('award', 'unknown')}
  Known requirements: {', '.join(program.get('requires', []))}
  Notes: {program.get('notes', '')}

Page content from official site:
---
{content_block}
---{no_content_note}

Your task: extract accurate, actionable information for this student for the 2026-2027 application cycle.

CRITICAL RULES:
1. Only report SPECIFIC dates (open_date, deadline) that are EXPLICITLY stated on the page for the 2026 or 2026-2027 cycle. Do NOT guess from prior years.
2. "Typically opens in October" without a year = NOT confirmed. Set confirmed=false.
3. "Applications open October 15, 2026" = confirmed. Set confirmed=true.
4. If the page has no 2026-2027 dates, set both date fields to null and both confirmed fields to false.
5. essay_prompts: list only verbatim prompts shown on this page for the current cycle.
6. what_strong_app_looks_like and prep_timeline: use your general knowledge about this specific program — these do NOT need to come from the page.
7. If there is an important eligibility issue (e.g., college-students-only, gender requirement), state it clearly in eligibility and notes.

Return ONLY a valid JSON object with exactly these fields — no preamble, no markdown fences:
{{
  "open_date": "YYYY-MM-DD or null",
  "open_date_confirmed": true or false,
  "deadline": "YYYY-MM-DD or null",
  "deadline_confirmed": true or false,
  "eligibility": "Who can apply — grade, age, citizenship, income, identity requirements",
  "essay_prompts": ["verbatim prompt 1", "verbatim prompt 2"],
  "award_details": "Full description of award/benefit",
  "requirements": ["requirement 1", "requirement 2"],
  "what_strong_app_looks_like": "2-4 sentences on what makes a competitive applicant for this specific program",
  "prep_timeline": "Specific month-by-month prep given the typical deadline",
  "notes": "Important caveats, eligibility warnings, or check-URL instructions",
  "confidence": "high or medium or low or none",
  "page_had_useful_info": true or false
}}"""


def _research_program(program: dict, client: anthropic.Anthropic) -> dict:
    slug = program["slug"]
    url = program["url"]
    name = program["name"]

    print(f"  Fetching: {url}")
    page_content = fetch_page(url)

    if not page_content:
        print(f"  WARNING: fetch failed for {name} — metadata only")
        page_content = "(page could not be fetched)"

    prompt = _build_research_prompt(program, page_content)

    try:
        print(f"  Calling Claude ({_RESEARCH_MODEL})...")
        message = client.messages.create(
            model=_RESEARCH_MODEL,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()

        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) >= 2 else text
            if text.startswith("json"):
                text = text[4:].strip()

        result = json.loads(text)
        deadline = result.get("deadline")
        confirmed = result.get("deadline_confirmed")
        print(f"  Done -- deadline: {deadline} (confirmed: {confirmed})")
        return result

    except json.JSONDecodeError as e:
        print(f"  ERROR: non-JSON response for {name}: {e}")
        return _fallback_result(program, f"Claude returned non-JSON: {e}")
    except Exception as e:
        print(f"  ERROR: API call failed for {name}: {e}")
        return _fallback_result(program, f"API call failed: {e}")


def _fallback_result(program: dict, error_message: str) -> dict:
    return {
        "open_date": None,
        "open_date_confirmed": False,
        "deadline": None,
        "deadline_confirmed": False,
        "eligibility": "Could not determine -- check program website",
        "essay_prompts": [],
        "award_details": program.get("award", ""),
        "requirements": program.get("requires", []),
        "what_strong_app_looks_like": "",
        "prep_timeline": "",
        "notes": f"Research failed: {error_message}. Check {program['url']} manually.",
        "confidence": "none",
        "page_had_useful_info": False,
    }


def _build_calendar_md(entries: list[dict]) -> str:
    """Build a human-readable CALENDAR.md sorted by deadline date."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Separate by whether deadline is known
    with_dates = [e for e in entries if e.get("deadline")]
    without_dates = [e for e in entries if not e.get("deadline")]

    # Sort by deadline ascending
    with_dates.sort(key=lambda e: e["deadline"])

    # Group into sections by type
    TYPE_LABELS = {
        "internship": "Paid Internships",
        "research_program": "Research Programs",
        "fly_in": "Fly-In Programs",
        "competition": "Competitions",
        "scholarship": "Scholarships",
        "local_scholarship": "Local / NC Scholarships",
        "fly_in_scholarship": "Scholarships",
        "competition_scholarship": "Competitions",
        "senate_program": "Scholarships",
        "governor_program": "Research Programs",
    }

    lines = [
        "# Application Calendar 2026-2027",
        "",
        f"_Generated {now_str} by `calendar_agent`. Re-run `python -m calendar_agent.research` to refresh._",
        "",
        "> **How to read this:** Deadlines marked ✅ are confirmed from the official site this cycle.",
        "> Deadlines marked ⚠️ are estimates from prior years — verify before the application opens.",
        "> The GitHub Actions agent checks this calendar every run and auto-queues programs when their deadline is within 30 days.",
        "",
    ]

    # Chronological master table
    lines += [
        "## All Programs by Deadline",
        "",
        "| Deadline | Program | Type | Award | Confirmed? |",
        "|----------|---------|------|-------|------------|",
    ]
    for e in with_dates:
        conf = "✅" if e.get("deadline_confirmed") else "⚠️"
        ptype = TYPE_LABELS.get(e.get("type", ""), e.get("type", ""))
        award = e.get("award", "")[:50]
        lines.append(f"| {e['deadline']} | [{e['name']}]({e['url']}) | {ptype} | {award} | {conf} |")

    if without_dates:
        lines += [
            "",
            "### Deadline Not Yet Confirmed (check sites manually)",
            "",
            "| Program | Type | Typical Deadline | Award |",
            "|---------|------|-----------------|-------|",
        ]
        for e in without_dates:
            ptype = TYPE_LABELS.get(e.get("type", ""), e.get("type", ""))
            award = e.get("award", "")[:50]
            notes = e.get("notes", "")[:60]
            lines.append(f"| [{e['name']}]({e['url']}) | {ptype} | {notes} | {award} |")

    # Section by category
    sections = {}
    for e in entries:
        label = TYPE_LABELS.get(e.get("type", ""), "Other")
        sections.setdefault(label, []).append(e)

    lines += ["", "---", ""]
    for section_name in ["Paid Internships", "Research Programs", "Fly-In Programs", "Competitions", "Scholarships", "Local / NC Scholarships"]:
        section_entries = sections.get(section_name, [])
        if not section_entries:
            continue
        # Sort: confirmed deadlines first, then by date, then no-date at end
        section_entries.sort(key=lambda e: (not bool(e.get("deadline")), e.get("deadline") or "9999"))
        lines += [f"## {section_name}", ""]
        for e in section_entries:
            tier_tag = {"elite": "🔥 Elite", "competitive": "⭐ Competitive", "accessible": "✓ Accessible"}.get(e.get("tier", ""), "")
            deadline_str = e.get("deadline", "TBD")
            conf_str = " ✅" if e.get("deadline_confirmed") else (" ⚠️" if e.get("deadline") else "")
            lines.append(f"### {e['name']} {tier_tag}")
            lines.append(f"- **URL:** {e['url']}")
            lines.append(f"- **Deadline:** {deadline_str}{conf_str}")
            if e.get("open_date"):
                open_conf = " ✅" if e.get("open_date_confirmed") else " ⚠️"
                lines.append(f"- **Opens:** {e['open_date']}{open_conf}")
            lines.append(f"- **Award:** {e.get('award', 'see site')}")
            if e.get("eligibility"):
                lines.append(f"- **Eligibility:** {e['eligibility']}")
            if e.get("notes"):
                lines.append(f"- **Notes:** {e['notes']}")
            lines.append("")

    return "\n".join(lines)


def _build_calendar_entry(program: dict, research: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "slug": program["slug"],
        "name": program["name"],
        "url": program["url"],
        "type": program.get("type", ""),
        "tier": program.get("tier", ""),
        "open_date": research.get("open_date"),
        "open_date_confirmed": research.get("open_date_confirmed", False),
        "deadline": research.get("deadline"),
        "deadline_confirmed": research.get("deadline_confirmed", False),
        "last_verified": now_iso,
        "award": research.get("award_details") or program.get("award", ""),
        "requires": research.get("requirements") or program.get("requires", []),
        "eligibility": research.get("eligibility", ""),
        "confidence": research.get("confidence", "none"),
        "notes": research.get("notes", ""),
    }


def _build_markdown_doc(program: dict, research: dict) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    name = program["name"]
    url = program["url"]
    tier = program.get("tier", "").capitalize()

    if research.get("deadline"):
        status = "confirmed from official site" if research.get("deadline_confirmed") else "UNCONFIRMED -- check site"
        deadline_line = f"{research['deadline']} ({status})"
    else:
        deadline_line = f"Not found -- check {url}"

    if research.get("open_date"):
        open_status = "confirmed" if research.get("open_date_confirmed") else "unconfirmed"
        open_line = f"{research['open_date']} ({open_status})"
    else:
        typical = program.get("typical_open", "")
        open_line = "Not found on page" + (f" -- typically {typical}" if typical else "")

    essay_prompts = research.get("essay_prompts", [])
    prompts_content = (
        "\n".join(f"- {p}" for p in essay_prompts)
        if essay_prompts
        else "Not listed on official page -- check the application portal directly."
    )

    requirements = research.get("requirements") or program.get("requires", [])
    req_content = "\n".join(f"- {r}" for r in requirements) if requirements else "- See program website"

    return f"""# {name}

**URL:** {url}
**Application Opens:** {open_line}
**Deadline:** {deadline_line}
**Award:** {research.get('award_details') or program.get('award', 'See program website')}
**Tier:** {tier}
**Last Verified:** {now_str}
**Research Confidence:** {research.get('confidence', 'none')}

## Eligibility
{research.get('eligibility') or 'See program website.'}

## Requirements
{req_content}

## Essay Prompts (2026-2027 cycle)
{prompts_content}

## What a Strong Application Looks Like
{research.get('what_strong_app_looks_like') or 'See program website for selection criteria.'}

## Recommended Prep Timeline
{research.get('prep_timeline') or f"Begin preparation 2-3 months before the {program.get('typical_deadline', 'application')} deadline."}

## Notes
{research.get('notes') or ''}

---
*Researched by `calendar_agent` on {now_str}. Re-run `python -m calendar_agent.research` to refresh.*
"""


def main() -> None:
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[research] ERROR: ANTHROPIC_API_KEY not set")
        print("[research]   Add it to .env or set it as an environment variable")
        sys.exit(1)

    if not _PROGRAMS_DB.exists():
        print(f"[research] ERROR: programs.json not found at {_PROGRAMS_DB}")
        sys.exit(1)

    with open(_PROGRAMS_DB, encoding="utf-8") as f:
        programs: list[dict] = json.load(f)

    print(f"[research] Loaded {len(programs)} programs")
    print(f"[research] Calendar output: {_CALENDAR_OUTPUT}")
    print(f"[research] Research docs:   {_RESEARCH_DIR}/")
    print(f"[research] Model: {_RESEARCH_MODEL}")
    estimated_min = len(programs) * (_API_DELAY_SECONDS + 20) // 60 + 1
    print(f"[research] Estimated time: ~{estimated_min} minutes\n")

    _CALENDAR_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic(api_key=api_key)

    calendar_entries: list[dict] = []
    summary_rows: list[dict] = []
    failed_programs: list[str] = []

    for i, program in enumerate(programs, 1):
        name = program["name"]
        slug = program["slug"]
        print(f"\n[{i:2d}/{len(programs)}] {name}")

        research = _research_program(program, client)

        entry = _build_calendar_entry(program, research)
        calendar_entries.append(entry)

        markdown = _build_markdown_doc(program, research)
        md_path = _RESEARCH_DIR / f"{slug}.md"
        md_path.write_text(markdown, encoding="utf-8")

        summary_rows.append({
            "name": name[:40],
            "deadline": entry.get("deadline") or "NOT FOUND",
            "confirmed": entry.get("deadline_confirmed", False),
            "confidence": research.get("confidence", "none"),
        })

        if not research.get("deadline"):
            failed_programs.append(name)

        if i < len(programs):
            time.sleep(_API_DELAY_SECONDS)

    calendar_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program_count": len(calendar_entries),
        "confirmed_count": sum(1 for e in calendar_entries if e.get("deadline_confirmed")),
        "unconfirmed_count": sum(1 for e in calendar_entries if e.get("deadline") and not e.get("deadline_confirmed")),
        "not_found_count": sum(1 for e in calendar_entries if not e.get("deadline")),
        "programs": calendar_entries,
    }
    with open(_CALENDAR_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(calendar_data, f, indent=2)

    # Also write human-readable CALENDAR.md
    calendar_md = _build_calendar_md(calendar_entries)
    _CALENDAR_MD.write_text(calendar_md, encoding="utf-8")

    print(f"\n\n{'=' * 70}")
    print("CALENDAR AGENT RESEARCH COMPLETE")
    print(f"{'=' * 70}")
    print(f"{'Program':<42} {'Deadline':<14} {'Conf?':<6} {'Confidence'}")
    print(f"{'-' * 70}")
    for row in summary_rows:
        conf = "YES" if row["confirmed"] else "no"
        print(f"{row['name']:<42} {row['deadline']:<14} {conf:<6} {row['confidence']}")

    print(f"\nTotal programs: {len(calendar_entries)}")
    print(f"Confirmed from site:   {calendar_data['confirmed_count']}")
    print(f"Found but unconfirmed: {calendar_data['unconfirmed_count']}")
    print(f"Not found on page:     {calendar_data['not_found_count']}")

    if failed_programs:
        print(f"\nCheck these manually (deadline not found on page):")
        for n in failed_programs:
            print(f"  - {n}")

    print(f"\nCalendar JSON: {_CALENDAR_OUTPUT}")
    print(f"Calendar MD:   {_CALENDAR_MD}")
    print(f"Research docs: {_RESEARCH_DIR}/")
    print("\nNext steps:")
    print("  1. Review outputs/CALENDAR.md -- check ⚠️ unconfirmed entries manually")
    print("  2. git add outputs/program_calendar.json outputs/CALENDAR.md outputs/program_research/")
    print("  3. git commit -m 'calendar: research run' && git push")
    print("  4. Re-run monthly to refresh deadlines")


if __name__ == "__main__":
    main()
