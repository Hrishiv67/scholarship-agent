"""Date honesty for the program calendar.

Rules:
- Never invent a deadline or copy last year's date.
- A date is only stored if it is a real YYYY-MM-DD in the current cycle
  AND the model quoted a sentence from the official page that contains it
  (or a clearly equivalent written date).
- Typical-month metadata from programs.json is never promoted to a deadline.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_CYCLE_START = date(2026, 1, 1)
_CYCLE_END = date(2028, 12, 31)

_VAGUE = (
    "typically", "usually", "around", "estimated", "last year",
    "prior year", "in the fall", "in the spring", "tba", "tbd",
    "check back", "to be announced", "coming soon",
)


def parse_iso(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    match = _ISO.match(text)
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None
    if parsed < _CYCLE_START or parsed > _CYCLE_END:
        return None
    return parsed.isoformat()


def quote_supports_date(quote: str, iso: str) -> bool:
    """The verbatim page quote must mention the date (ISO or a written form)."""
    if not quote or not iso:
        return False
    q = quote.lower()
    if any(w in q for w in _VAGUE) and iso not in quote:
        return False
    if iso in quote:
        return True
    year, month, day = iso.split("-")
    months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    month_name = months[int(month) - 1]
    day_i = str(int(day))
    if month_name in q and year in quote and (day_i in quote or day in quote):
        return True
    return False


def confirm_deadline(raw_deadline, confirmed_flag, quote: str, page_text: str) -> tuple[str | None, bool]:
    """Return (iso_or_none, confirmed). Confirmed only with a page quote."""
    iso = parse_iso(raw_deadline)
    if not iso:
        return None, False
    quote = (quote or "").strip()
    if confirmed_flag and quote_supports_date(quote, iso):
        return iso, True
    # If the ISO date itself appears on the fetched page, keep it unconfirmed
    # only when the model also claimed confirmation with a quote. Otherwise drop.
    if iso in (page_text or "") and quote_supports_date(quote, iso):
        return iso, True
    return None, False


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
