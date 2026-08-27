"""
Confirm program dates from official pages and write the calendar.

Never invent a deadline. Typical-month metadata is not a date.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from . import categories, dates, eligibility, render
from .scraper import fetch_page

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_PROGRAMS_DB = Path(__file__).parent / "programs.json"
_CALENDAR_OUTPUT = _ROOT / "outputs" / "program_calendar.json"
_CALENDAR_MD = _ROOT / "outputs" / "CALENDAR.md"
_CALENDAR_ICS = _ROOT / "outputs" / "calendar.ics"
_RESEARCH_DIR = _ROOT / "outputs" / "program_research"

_RESEARCH_MODEL = "claude-haiku-4-5-20251001"
_API_DELAY_SECONDS = 2


def _build_research_prompt(program: dict, page_content: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    has_content = bool(page_content) and page_content != "(page loaded but contained no readable text)"
    content_block = page_content if has_content else "(could not fetch)"
    no_content_note = "" if has_content else (
        "\n\nNOTE: Page could not be fetched. You MUST set both dates to null "
        "and confirmed=false. Do not use typical months from metadata as dates."
    )

    return f"""Extract facts for a high school program calendar. Today is {today}.

Student (do not invent extra facts): Class of 2028, rising junior / 11th grade, male,
US citizen, Green Hope High School, Cary NC. Date of birth is unknown.

Program metadata (NOT a source of dates):
  Name: {program['name']}
  URL: {program['url']}
  Type: {program.get('type', 'unknown')}
  Suggested track: {categories.categorize(program)}
  Typical open (unconfirmed): {program.get('typical_open', 'unknown')}
  Typical deadline (unconfirmed): {program.get('typical_deadline', 'unknown')}

Official page text:
---
{content_block}
---{no_content_note}

HARD RULES:
1. open_date and deadline must be YYYY-MM-DD for the 2026, 2027, or 2028 cycle
   AND must appear on the official page. If the page only says "typically October"
   or uses a prior year, both dates are null and confirmed is false.
2. deadline_quote must be a verbatim sentence from the page that contains that date.
   If you cannot quote the sentence, deadline is null.
3. Do not copy typical_deadline from metadata into deadline.
4. seniors_only=true if the page is for graduating seniors / class of 2027 / 12th grade only.
5. identity_restricted is a short label (e.g. "women-only") or empty string.
6. costs_money=true only for application fees or tuition to attend — not a stipend paid TO the student.
7. category is exactly one of: ai, engineering, business, general.

Return ONLY JSON:
{{
  "open_date": "YYYY-MM-DD or null",
  "open_date_confirmed": false,
  "deadline": "YYYY-MM-DD or null",
  "deadline_confirmed": false,
  "deadline_quote": "",
  "eligibility": "who can apply this cycle",
  "grade_eligible": true,
  "seniors_only": false,
  "identity_restricted": "",
  "costs_money": false,
  "category": "engineering",
  "essay_prompts": [],
  "award_details": "",
  "requirements": [],
  "notes": "",
  "confidence": "high or medium or low or none",
  "page_had_useful_info": false
}}"""


def _fallback_result(program: dict, error_message: str) -> dict:
    return {
        "open_date": None,
        "open_date_confirmed": False,
        "deadline": None,
        "deadline_confirmed": False,
        "deadline_quote": "",
        "eligibility": "Could not determine — check program website",
        "grade_eligible": None,
        "seniors_only": False,
        "identity_restricted": "",
        "costs_money": False,
        "category": categories.categorize(program),
        "essay_prompts": [],
        "award_details": program.get("award", ""),
        "requirements": program.get("requires", []),
        "notes": f"Research failed: {error_message}. Check {program['url']} manually.",
        "confidence": "none",
        "page_had_useful_info": False,
    }


def _research_program(program: dict, client: anthropic.Anthropic) -> dict:
    url = program["url"]
    name = program["name"]
    print(f"  Fetching: {url}")
    page_content = fetch_page(url)
    if not page_content:
        print(f"  WARNING: fetch failed for {name} — no date will be stored")
        return _fallback_result(program, "official page could not be fetched")

    prompt = _build_research_prompt(program, page_content)
    try:
        print(f"  Calling Claude ({_RESEARCH_MODEL})...")
        message = client.messages.create(
            model=_RESEARCH_MODEL,
            max_tokens=1600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) >= 2 else text
            if text.startswith("json"):
                text = text[4:].strip()
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: non-JSON response for {name}: {e}")
        return _fallback_result(program, f"Claude returned non-JSON: {e}")
    except Exception as e:
        print(f"  ERROR: API call failed for {name}: {e}")
        return _fallback_result(program, f"API call failed: {e}")

    deadline, d_ok = dates.confirm_deadline(
        result.get("deadline"),
        result.get("deadline_confirmed"),
        result.get("deadline_quote") or "",
        page_content,
    )
    open_iso = dates.parse_iso(result.get("open_date"))
    if open_iso and open_iso in page_content:
        open_date, o_ok = open_iso, bool(result.get("open_date_confirmed"))
    else:
        open_date, o_ok = None, False

    result["deadline"] = deadline
    result["deadline_confirmed"] = d_ok
    result["open_date"] = open_date
    result["open_date_confirmed"] = o_ok
    if result.get("category") not in categories.VALID:
        result["category"] = categories.categorize(program)
    print(f"  Done -- deadline: {deadline} (confirmed: {d_ok})")
    return result


def _is_failed(research: dict) -> bool:
    return research.get("confidence") == "none" or not research.get("page_had_useful_info")


def _build_calendar_entry(program: dict, research: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    category = research.get("category") or categories.categorize(program)
    entry = {
        "slug": program["slug"],
        "name": program["name"],
        "url": program["url"],
        "type": program.get("type", ""),
        "tier": program.get("tier", ""),
        "category": category,
        "open_date": research.get("open_date"),
        "open_date_confirmed": research.get("open_date_confirmed", False),
        "deadline": research.get("deadline"),
        "deadline_confirmed": research.get("deadline_confirmed", False),
        "deadline_quote": research.get("deadline_quote") or "",
        "last_verified": now_iso,
        "award": research.get("award_details") or program.get("award", ""),
        "requires": research.get("requirements") or program.get("requires", []),
        "eligibility": research.get("eligibility", ""),
        "confidence": research.get("confidence", "none"),
        "notes": research.get("notes", ""),
        "seniors_only": bool(research.get("seniors_only")),
        "identity_restricted": research.get("identity_restricted") or "",
        "costs_money": bool(research.get("costs_money")),
    }
    entry["status"] = eligibility.classify_status(research, program)
    return entry


def _keep_confirmed_if_failed(old: dict | None, new: dict) -> dict:
    if not old:
        return new
    if new.get("confidence") != "none":
        return new
    if old.get("deadline_confirmed") and old.get("deadline"):
        print(f"  Keeping previously confirmed deadline for {new.get('name')}")
        kept = dict(new)
        for key in (
            "deadline", "deadline_confirmed", "deadline_quote",
            "open_date", "open_date_confirmed", "eligibility", "award",
            "category", "status",
        ):
            if old.get(key) not in (None, "", False) or key.endswith("confirmed"):
                kept[key] = old.get(key)
        kept["notes"] = (
            f"{new.get('notes', '')} Prior confirmed deadline kept because this fetch failed."
        ).strip()
        return kept
    return new


def _load_existing() -> dict[str, dict]:
    if not _CALENDAR_OUTPUT.exists():
        return {}
    try:
        data = json.loads(_CALENDAR_OUTPUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {p["slug"]: p for p in data.get("programs") or [] if p.get("slug")}


def _priority(program: dict, existing: dict[str, dict]) -> tuple:
    old = existing.get(program["slug"], {})
    failed = (old.get("confidence") == "none") or not old
    no_date = not old.get("deadline")
    unconfirmed = bool(old.get("deadline") and not old.get("deadline_confirmed"))
    return (not failed, not no_date, not unconfirmed, program.get("name") or "")


def _research_limit() -> int:
    raw = os.environ.get("RESEARCH_LIMIT", "40")
    try:
        return max(1, int(raw))
    except ValueError:
        return 40


def _build_markdown_doc(program: dict, research: dict) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    deadline = research.get("deadline") or "Not stated on official page"
    conf = "confirmed from official page quote" if research.get("deadline_confirmed") else "not confirmed"
    quote = research.get("deadline_quote") or "(no quote)"
    return f"""# {program['name']}

**URL:** {program['url']}
**Track:** {categories.label(research.get('category') or categories.categorize(program))}
**Deadline:** {deadline} ({conf})
**Deadline quote:** {quote}
**Opens:** {research.get('open_date') or 'Not stated on official page'}
**Award:** {research.get('award_details') or program.get('award') or 'See program website'}
**Eligibility:** {research.get('eligibility') or 'See program website'}
**Status:** {eligibility.classify_status(research, program)}
**Last verified:** {now_str}
**Confidence:** {research.get('confidence', 'none')}

## Notes
{research.get('notes') or ''}

---
*Dates are stored only when the official page states them for this cycle.*
"""


def _maybe_email(md: str, stats: dict) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_address or not gmail_password:
        print("[research] Gmail not set — skipping calendar email")
        return
    import smtplib
    import ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject = (
        f"Program calendar — {stats['confirmed_count']} confirmed dates "
        f"({datetime.now(timezone.utc).strftime('%b %d, %Y')})"
    )
    body = (
        f"Confirmed deadlines: {stats['confirmed_count']}\n"
        f"Unconfirmed / not on page: {stats['not_found_count']}\n"
        f"Programs: {stats['program_count']}\n\n"
        "Full calendar: outputs/CALENDAR.md in the repo.\n"
        "Import outputs/calendar.ics for confirmed dates only.\n"
    )
    msg = MIMEMultipart("alternative")
    msg["From"] = f"Program Calendar <{gmail_address}>"
    msg["To"] = gmail_address
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"[research] Calendar email sent to {gmail_address}")
    except Exception as e:
        print(f"[research] Failed to send email: {e}")


def main(programs: list[dict] | None = None) -> None:
    load_dotenv(_ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[research] ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    if programs is None:
        if not _PROGRAMS_DB.exists():
            print(f"[research] ERROR: programs.json not found at {_PROGRAMS_DB}")
            sys.exit(1)
        with open(_PROGRAMS_DB, encoding="utf-8") as f:
            programs = json.load(f)

    existing = _load_existing()
    limit = _research_limit()
    ordered = sorted(programs, key=lambda p: _priority(p, existing))
    to_run = ordered[:limit]
    print(f"[research] {len(programs)} programs, researching {len(to_run)} (RESEARCH_LIMIT={limit})")
    print(f"[research] Model: {_RESEARCH_MODEL}")

    _CALENDAR_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic(api_key=api_key)
    updated: dict[str, dict] = dict(existing)

    for i, program in enumerate(to_run, 1):
        print(f"\n[{i:2d}/{len(to_run)}] {program['name']}")
        raw = _research_program(program, client)
        entry = _build_calendar_entry(program, raw)
        entry = _keep_confirmed_if_failed(existing.get(program["slug"]), entry)
        updated[program["slug"]] = entry
        md_path = _RESEARCH_DIR / f"{program['slug']}.md"
        md_path.write_text(_build_markdown_doc(program, raw), encoding="utf-8")
        if i < len(to_run):
            time.sleep(_API_DELAY_SECONDS)

    # Include programs not researched this run (keep prior rows; add stubs for brand new)
    for program in programs:
        if program["slug"] in updated:
            continue
        updated[program["slug"]] = {
            "slug": program["slug"],
            "name": program["name"],
            "url": program["url"],
            "type": program.get("type", ""),
            "tier": program.get("tier", ""),
            "category": categories.categorize(program),
            "open_date": None,
            "open_date_confirmed": False,
            "deadline": None,
            "deadline_confirmed": False,
            "deadline_quote": "",
            "last_verified": None,
            "award": program.get("award", ""),
            "requires": program.get("requires", []),
            "eligibility": "",
            "confidence": "none",
            "notes": "Not yet verified from official page this cycle.",
            "status": "verify",
            "seniors_only": False,
            "identity_restricted": "",
            "costs_money": False,
        }

    entries = list(updated.values())
    calendar_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "program_count": len(entries),
        "confirmed_count": sum(1 for e in entries if e.get("deadline_confirmed")),
        "unconfirmed_count": sum(1 for e in entries if e.get("deadline") and not e.get("deadline_confirmed")),
        "not_found_count": sum(1 for e in entries if not e.get("deadline")),
        "programs": entries,
    }
    _CALENDAR_OUTPUT.write_text(json.dumps(calendar_data, indent=2), encoding="utf-8")
    md = render.build_calendar_md(entries, calendar_data["generated_at"])
    _CALENDAR_MD.write_text(md, encoding="utf-8")
    _CALENDAR_ICS.write_text(render.build_ics(entries), encoding="utf-8")

    print(f"\nConfirmed: {calendar_data['confirmed_count']}")
    print(f"No date on page: {calendar_data['not_found_count']}")
    print(f"Calendar: {_CALENDAR_MD}")
    print(f"ICS (confirmed only): {_CALENDAR_ICS}")
    _maybe_email(md, calendar_data)


if __name__ == "__main__":
    main()
