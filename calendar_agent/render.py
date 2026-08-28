"""Write CALENDAR.md and a confirmed-deadlines-only .ics file."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .categories import TRACKS, label as track_label
from .dates import today_utc

_ROOT_CALENDAR_TITLE = "Program Calendar — AI / Engineering / Business"


def _sort_key(entry: dict):
    return (entry.get("deadline") is None, entry.get("deadline") or "9999-99-99", entry.get("name") or "")


def _conf(entry: dict) -> str:
    if entry.get("deadline_confirmed"):
        return "✅ confirmed"
    if entry.get("deadline"):
        return "⚠️ unconfirmed"
    return "— no date on page"


def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_calendar_md(entries: list[dict], generated_at: str) -> str:
    today = today_utc().isoformat()
    lines = [
        f"# {_ROOT_CALENDAR_TITLE}",
        "",
        f"_Generated {generated_at[:10]} from official program pages. "
        "A date is listed as confirmed only when the page stated it for this cycle._",
        "",
        f"**Student:** Hrishiv Khatiwala · Green Hope HS · Class of 2028 (rising junior). "
        "Seniors-only programs are tracked for **fall 2027**, not this year. "
        "Women-only / need-only / FRC-FTC programs are skipped.",
        "",
        "> ✅ = date quoted from the official page this run. "
        "No emoji date = the page did not publish a 2026–2027 deadline — do not guess.",
        "",
    ]

    due_soon = _due_soon_confirmed(entries, days=90)
    if due_soon:
        lines += ["## Confirmed deadlines (next 90 days)", ""]
        for cat in TRACKS:
            group = [e for e in due_soon if e.get("category") == cat]
            if not group:
                continue
            lines.append(f"### {track_label(cat)}")
            for e in sorted(group, key=lambda x: x.get("deadline") or ""):
                lines.append(
                    f"- **{e['deadline']}** — [{e['name']}]({e['url']})"
                )
            lines.append("")
        general_due = [e for e in due_soon if e.get("category") not in TRACKS]
        if general_due:
            lines.append("### General")
            for e in sorted(general_due, key=lambda x: x.get("deadline") or ""):
                lines.append(f"- **{e['deadline']}** — [{e['name']}]({e['url']})")
            lines.append("")

    lines += [
        "## How to read this",
        "",
        "Programs are split into **AI**, **Engineering**, and **Business**. "
        "Inside each track they are sorted by due date. "
        "Generic merit scholarships that are not field programs sit at the bottom.",
        "",
    ]

    by_cat: dict[str, list] = {c: [] for c in TRACKS}
    general = []
    seniors = []
    ineligible = []
    for e in entries:
        status = e.get("status") or "verify"
        if status == "ineligible":
            ineligible.append(e)
            continue
        if status == "seniors_later":
            seniors.append(e)
            continue
        cat = e.get("category") or "general"
        if cat in TRACKS:
            by_cat[cat].append(e)
        else:
            general.append(e)

    for cat in TRACKS:
        group = sorted(by_cat[cat], key=_sort_key)
        lines += [f"## {track_label(cat)}", ""]
        if not group:
            lines += ["_No programs in this track yet._", ""]
            continue
        lines += [
            "| Deadline | Status | Program | Award | Eligibility |",
            "|----------|--------|---------|-------|-------------|",
        ]
        for e in group:
            award = (e.get("award") or "")[:60].replace("|", "/")
            elig = (e.get("eligibility") or e.get("status") or "")[:80].replace("|", "/")
            deadline = e.get("deadline") or "—"
            lines.append(
                f"| {deadline} | {_conf(e)} | [{e['name']}]({e['url']}) | {award} | {elig} |"
            )
        lines.append("")

    if general:
        lines += ["## General (not field-specific)", ""]
        lines += [
            "| Deadline | Status | Program | Award |",
            "|----------|--------|---------|-------|",
        ]
        for e in sorted(general, key=_sort_key):
            award = (e.get("award") or "")[:60].replace("|", "/")
            deadline = e.get("deadline") or "—"
            lines.append(
                f"| {deadline} | {_conf(e)} | [{e['name']}]({e['url']}) | {award} |"
            )
        lines.append("")

    if seniors:
        lines += ["## Track for fall 2027 (seniors-only)", ""]
        for e in sorted(seniors, key=_sort_key):
            lines.append(f"- [{e['name']}]({e['url']}) — {e.get('deadline') or 'date TBA'}")
        lines.append("")

    if ineligible:
        lines += ["## Skipped / ineligible", ""]
        for e in ineligible:
            reason = (e.get("notes") or "does not fit current eligibility")[:120]
            lines.append(f"- [{e['name']}]({e['url']}) — {reason}")
        lines.append("")

    lines += [
        "---",
        f"_Today: {today}. Import `outputs/calendar.ics` for confirmed deadlines only._",
        "",
    ]
    return "\n".join(lines)


def build_ics(entries: list[dict]) -> str:
    """Only confirmed deadlines. Unconfirmed dates never become calendar events."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Hrishiv Program Calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Hrishiv program deadlines (confirmed)",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for e in entries:
        if not e.get("deadline_confirmed") or not e.get("deadline"):
            continue
        if e.get("status") == "ineligible":
            continue
        day = e["deadline"].replace("-", "")
        uid = f"{e.get('slug', 'prog')}@scholarship-agent"
        cat = track_label(e.get("category") or "general")
        summary = _ics_escape(f"{e['name']} ({cat}) due")
        desc = _ics_escape(f"{e.get('url', '')}\n{e.get('eligibility', '')}")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day}",
            f"DTEND;VALUE=DATE:{day}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            f"URL:{e.get('url', '')}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _due_soon_confirmed(entries: list[dict], days: int = 90) -> list[dict]:
    today = today_utc()
    cutoff = today + timedelta(days=days)
    out = []
    for e in entries:
        if not e.get("deadline_confirmed") or not e.get("deadline"):
            continue
        if e.get("status") in ("ineligible", "seniors_later"):
            continue
        try:
            d = date.fromisoformat(e["deadline"])
        except ValueError:
            continue
        if today <= d <= cutoff:
            out.append(e)
    return out


def build_weekly_digest(entries: list[dict], generated_at: str) -> str:
    today = today_utc()
    lines = [
        f"# Weekly Program Digest — {today.isoformat()}",
        "",
        "_Only confirmed official-page deadlines. Seniors-only tracked separately._",
        "",
    ]
    for window, end, label_text in (
        (0, 14, "Apply this week (≤14 days)"),
        (15, 30, "Apply this month (15–30 days)"),
        (31, 60, "Coming up (31–60 days)"),
    ):
        bucket = []
        for e in entries:
            if not e.get("deadline_confirmed") or e.get("status") in ("ineligible", "seniors_later"):
                continue
            try:
                d = date.fromisoformat(e["deadline"])
            except (ValueError, TypeError):
                continue
            days_out = (d - today).days
            if window <= days_out <= end:
                bucket.append(e)
        lines += [f"## {label_text}", ""]
        if not bucket:
            lines += ["_None with confirmed deadlines in this window._", ""]
            continue
        for cat in TRACKS + ["general"]:
            group = [e for e in bucket if (e.get("category") or "general") == cat]
            if not group:
                continue
            title = track_label(cat) if cat != "general" else "General"
            lines.append(f"### {title}")
            for e in sorted(group, key=lambda x: x.get("deadline") or ""):
                lines.append(
                    f"- **{e['deadline']}** [{e['name']}]({e['url']}) — {(e.get('award') or '')[:80]}"
                )
            lines.append("")

    seniors = [e for e in entries if e.get("status") == "seniors_later"]
    if seniors:
        lines += ["## Track for fall 2027 (seniors-only)", ""]
        for e in sorted(seniors, key=_sort_key)[:20]:
            lines.append(f"- [{e['name']}]({e['url']})")
        lines.append("")

    confirmed = sum(1 for e in entries if e.get("deadline_confirmed"))
    lines += [
        "---",
        f"_Generated {generated_at[:10]}. {confirmed} confirmed deadlines across {len(entries)} programs._",
        "",
    ]
    return "\n".join(lines)
