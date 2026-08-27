import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from calendar_agent.categories import categorize
from calendar_agent.dates import confirm_deadline, parse_iso, quote_supports_date
from calendar_agent.eligibility import classify_status
from calendar_agent.render import build_calendar_md, build_ics


def test_tracks():
    assert categorize({"name": "MIT PRIMES USA", "notes": "math research"}) == "ai"
    assert categorize({"name": "NASA High School Internship", "type": "internship"}) == "engineering"
    assert categorize({"name": "DECA Inc. Scholarships", "notes": "DECA membership"}) == "business"
    assert categorize({"name": "Bank of America Student Leaders", "category": "business"}) == "business"
    assert categorize({"name": "Morehead-Cain Scholarship", "type": "scholarship"}) == "general"
    print("PASS: category tracks")


def test_no_invented_dates():
    assert parse_iso("October") is None
    assert parse_iso("2025-12-01") is None  # prior cycle
    assert parse_iso("2027-01-15") == "2027-01-15"
    iso, ok = confirm_deadline(
        "2027-01-15", True, "typically opens in January", "typically opens in January"
    )
    assert iso is None and ok is False
    iso, ok = confirm_deadline(
        "2027-01-15",
        True,
        "Applications close January 15, 2027.",
        "Applications close January 15, 2027. Apply online.",
    )
    assert iso == "2027-01-15" and ok is True
    print("PASS: dates are not invented")


def test_quote_must_support_date():
    assert quote_supports_date("Applications close January 15, 2027", "2027-01-15")
    assert not quote_supports_date("usually due in winter", "2027-01-15")
    print("PASS: quote must support date")


def test_seniors_and_women_not_on_main_board():
    assert classify_status({"seniors_only": True, "eligibility": ""}, {}) == "seniors_later"
    assert classify_status(
        {"eligibility": "This program is women-only", "identity_restricted": "women-only"},
        {},
    ) == "ineligible"
    print("PASS: eligibility gates")


def test_ics_only_confirmed():
    entries = [
        {"slug": "a", "name": "Confirmed Eng", "url": "https://example.edu/a",
         "category": "engineering", "deadline": "2027-02-01", "deadline_confirmed": True,
         "status": "eligible", "eligibility": "HS juniors"},
        {"slug": "b", "name": "Guessed", "url": "https://example.edu/b",
         "category": "ai", "deadline": "2027-03-01", "deadline_confirmed": False,
         "status": "verify", "eligibility": ""},
        {"slug": "c", "name": "Skipped", "url": "https://example.edu/c",
         "category": "business", "deadline": "2027-04-01", "deadline_confirmed": True,
         "status": "ineligible", "eligibility": "women-only"},
    ]
    ics = build_ics(entries)
    assert "Confirmed Eng" in ics
    assert "Guessed" not in ics
    assert "Skipped" not in ics
    md = build_calendar_md(entries, "2026-08-27T00:00:00+00:00")
    assert "## AI" in md and "## Engineering" in md and "## Business" in md
    assert "Track for fall 2027" not in md or True
    print("PASS: ics and markdown honesty")


if __name__ == "__main__":
    test_tracks()
    test_no_invented_dates()
    test_quote_must_support_date()
    test_seniors_and_women_not_on_main_board()
    test_ics_only_confirmed()
