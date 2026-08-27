import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.searcher import OPEN_NOW, SEARCH_QUERIES, SUMMER_2027, _ROOT, _tavily_api_key, load_calendar_sources


def test_summer_2027_sources():
    urls = [s["url"] for s in SUMMER_2027]
    assert any("sip" in u for u in urls)
    assert any("seap" in u.lower() or "navalsteminterns" in u for u in urls)
    assert any("grip.ncsu" in u for u in urls)
    assert all(s["type"] in ("internship", "research_program") for s in SUMMER_2027)
    print(f"PASS: {len(SUMMER_2027)} summer 2027 sources")


def test_search_queries_cover_summer_2027():
    blob = " ".join(SEARCH_QUERIES).lower()
    assert "summer 2027" in blob
    assert "paid internship" in blob or "stipend" in blob
    print("PASS: search queries include summer 2027 internships")


def test_open_now_still_present():
    assert any("sallie.com" in s["url"] for s in OPEN_NOW)
    assert any("bold.org" in s["url"] for s in OPEN_NOW)
    print("PASS: currently-open scholarships still seeded")


def test_calendar_surfaces_internships_without_dates():
    results = load_calendar_sources()
    intern = [r for r in results if "intern" in (r.title or "").lower() or "grip" in (r.title or "").lower()]
    assert intern, "calendar should still list internships when dates are null"
    print(f"PASS: calendar returned {len(results)} programs including internships")


def test_tavily_reads_same_env_file():
    key = _tavily_api_key()
    assert isinstance(key, str)
    if (_ROOT / ".env").exists():
        assert key.startswith("tvly-"), "Tavily should load TAVILY_API_KEY from the project .env"
    print("PASS: Tavily uses TAVILY_API_KEY from .env")


if __name__ == "__main__":
    test_summer_2027_sources()
    test_search_queries_cover_summer_2027()
    test_open_now_still_present()
    test_calendar_surfaces_internships_without_dates()
    test_tavily_reads_same_env_file()
