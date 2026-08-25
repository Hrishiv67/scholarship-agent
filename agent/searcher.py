import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tavily import TavilyClient

from calendar_agent.scraper import fetch_page

SEARCH_QUERIES = [
    # Priority 1 — RDU / NC local (direct program pages, not job boards)
    'paid internship "high school" "apply" site:ncsu.edu OR site:duke.edu OR site:unc.edu OR site:waketech.edu 2027',
    'paid internship "high school students" Raleigh OR Durham OR Cary NC 2027 "apply now" OR "applications open" -site:indeed.com -site:linkedin.com -site:ziprecruiter.com',
    '"high school" research program NC State OR Duke OR UNC 2027 "stipend" OR "paid" "application" -site:reddit.com -site:quora.com',
    '"high school" internship "Cary" OR "Research Triangle" OR "RTP" 2027 "apply" -site:indeed.com -site:glassdoor.com',
    # Priority 2 — National STEM programs (actual program pages)
    '"high school" "summer research" "stipend" 2027 "application deadline" -site:reddit.com -site:collegevine.com -site:niche.com',
    '"rising junior" OR "rising senior" "high school" research program 2027 "apply" "paid" -"college students" -"undergraduate"',
    '"Clark Scholar" OR "PRIMES" OR "RSI" OR "SSTP" 2027 application -site:reddit.com',
    'site:nasa.gov "high school" internship OR program 2027 apply',
    'site:energy.gov OR site:noaa.gov "high school" intern OR student program 2027',
    # Priority 3 — Fly-in programs (actual college fly-in pages)
    '"fly-in" "high school" "class of 2028" OR "junior" 2027 apply -site:collegevine.com -site:niche.com -site:reddit.com',
    'site:mit.edu OR site:stanford.edu OR site:cmu.edu OR site:gatech.edu "fly-in" OR "diversity visit" "high school" apply',
    '"all expenses paid" "high school" visit OR "fly in" OR "fly-in" engineering OR STEM 2027 apply',
    # Priority 4 — No-essay scholarships (actual apply pages)
    '"no essay" scholarship "high school junior" OR "11th grade" OR "class of 2028" apply 2027 -site:fastweb.com -site:scholarships.com -"list of"',
    'scholarship "high school" "no application essay" OR "no essay required" 2026 2027 "apply" "open"',
    '"Niche" OR "Bold.org" OR "Going Merry" scholarship "no essay" apply 2027',
    # Priority 5 — Paid apprenticeships & narrative-building programs
    'paid apprenticeship "high school" STEM OR engineering OR software 2027 apply -site:indeed.com -site:ziprecruiter.com',
    '"high school" "paid" research OR lab assistant OR intern university 2027 "stipend" apply -site:reddit.com',
    'pre-college OR "summer program" "high school" engineering OR computer science "paid" OR "stipend" OR "free" 2027 apply',
]

# Individual program application pages — checked every run
# These are real application/info pages, not listing aggregators
DIRECT_SOURCES = [
    # NC / local programs
    {"name": "NC State GRIP High School Research", "url": "https://grip.ncsu.edu/high-school/", "type": "research_program"},
    {"name": "Duke RISE Program", "url": "https://dukelife.duke.edu/rise", "type": "research_program"},
    {"name": "UNC BEAM High School", "url": "https://beam.unc.edu/high-school-programs/", "type": "research_program"},
    {"name": "Triangle Community Foundation Scholarships", "url": "https://www.trianglecf.org/grants-scholarships/scholarships/", "type": "local_scholarship"},
    {"name": "NCSU College of Engineering HS Programs", "url": "https://www.engr.ncsu.edu/k-12/high-school-programs/", "type": "program"},
    # National research programs
    {"name": "Clark Scholars Program", "url": "https://www.clarkscholars.ttu.edu/", "type": "research_program"},
    {"name": "MIT PRIMES USA", "url": "https://math.mit.edu/research/highschool/primes/usa/", "type": "research_program"},
    {"name": "RSI Application", "url": "https://www.cee.org/programs/research-science-institute", "type": "research_program"},
    {"name": "NASA Glenn HS Engineering Institute", "url": "https://www.nasa.gov/learning-resources/internship-programs/", "type": "internship"},
    {"name": "NOAA Student Opportunities", "url": "https://www.noaa.gov/education/opportunities/students", "type": "internship"},
    {"name": "DOE Science Undergraduate Lab Internships", "url": "https://science.osti.gov/wdts/suli", "type": "internship"},
    # Fly-in programs
    {"name": "MIT Campus Preview Weekend", "url": "https://mitadmissions.org/apply/experience/campus-preview-weekend/", "type": "fly_in"},
    {"name": "Stanford FEST Fly-In", "url": "https://engineering.stanford.edu/students-academics/equity-and-inclusion-initiatives/prospective-undergraduate-students/discover", "type": "fly_in"},
    {"name": "Georgia Tech FOCUS Fly-In", "url": "https://admission.gatech.edu/first-year/campus-visit/focus", "type": "fly_in"},
    {"name": "Duke Engineering Diversity Fly-In", "url": "https://pratt.duke.edu/undergrad/apply/diversity", "type": "fly_in"},
    {"name": "Harvey Mudd WAVE Fellows", "url": "https://www.hmc.edu/admission/fast/", "type": "fly_in"},
    # No-essay scholarships — direct apply pages
    {"name": "Niche $25k No-Essay Scholarship", "url": "https://www.niche.com/colleges/scholarships/no-essay/", "type": "scholarship"},
    {"name": "Bold.org No-Essay Scholarships", "url": "https://bold.org/scholarships/by-type/no-essay-scholarships/", "type": "scholarship"},
    {"name": "College Board BigFuture Scholarships", "url": "https://bigfuture.collegeboard.org/pay-for-college/bigfuture-scholarships-2027", "type": "scholarship"},
    {"name": "QuestBridge College Prep Scholar", "url": "https://www.questbridge.org/high-school-students/scholar-program", "type": "fly_in_scholarship"},
]


_CALENDAR_PATH = Path(__file__).parent.parent / "outputs" / "program_calendar.json"


@dataclass
class RawOpportunity:
    title: str
    url: str
    snippet: str
    source_query: str
    found_at: str
    raw_content: str = ""
    tier: str = ""      # elite | competitive | accessible (from program DB), else ""
    slug: str = ""


def load_calendar_sources(
    days_until_deadline: int = 30,
    days_since_open: int = 7,
) -> list[RawOpportunity]:
    """
    Read outputs/program_calendar.json (produced by calendar_agent/research.py)
    and return RawOpportunity objects for programs whose deadline is within
    `days_until_deadline` days OR that opened within `days_since_open` days.
    Safe no-op if the calendar file hasn't been generated yet.
    """
    if not _CALENDAR_PATH.exists():
        return []

    try:
        with open(_CALENDAR_PATH, encoding="utf-8") as f:
            calendar = json.load(f)
    except Exception as e:
        print(f"[searcher] WARNING: Could not read program_calendar.json: {e}")
        return []

    now = datetime.now(timezone.utc)
    found_at = now.isoformat()
    results = []

    for program in calendar.get("programs", []):
        deadline_str = program.get("deadline")
        open_date_str = program.get("open_date")
        include = False

        if deadline_str:
            try:
                dt_str = deadline_str + "T00:00:00+00:00" if len(deadline_str) == 10 else deadline_str
                deadline_dt = datetime.fromisoformat(dt_str)
                days_left = (deadline_dt - now).days
                if 0 <= days_left <= days_until_deadline:
                    include = True
            except ValueError:
                pass

        if not include and open_date_str:
            try:
                dt_str = open_date_str + "T00:00:00+00:00" if len(open_date_str) == 10 else open_date_str
                open_dt = datetime.fromisoformat(dt_str)
                days_ago = (now - open_dt).days
                if 0 <= days_ago <= days_since_open:
                    include = True
            except ValueError:
                pass

        if include:
            confirmed_tag = "[CONFIRMED]" if program.get("deadline_confirmed") else "[UNCONFIRMED DEADLINE]"
            deadline_info = f"Deadline: {deadline_str}" if deadline_str else "Deadline: check site"
            snippet = (
                f"[CALENDAR] {confirmed_tag} {deadline_info}. "
                f"Award: {program.get('award', 'see program')}. "
                f"Tier: {program.get('tier', 'unknown')}. "
                f"{program.get('notes', '')}".strip()
            )
            eligibility = program.get("eligibility", "")
            results.append(RawOpportunity(
                title=program["name"],
                url=program["url"],
                snippet=snippet[:500],
                source_query="program_calendar",
                found_at=found_at,
                raw_content=f"{snippet} Eligibility: {eligibility}".strip(),
                tier=program.get("tier", ""),
                slug=program.get("slug", ""),
            ))

    if results:
        print(f"[searcher] Calendar: {len(results)} programs active (due soon or recently opened)")
    else:
        print(f"[searcher] Calendar: no programs due within {days_until_deadline} days or opened in last {days_since_open} days")

    return results


def search(dry_run: bool = False) -> list[RawOpportunity]:
    api_key = os.environ.get("TAVILY_API_KEY", "")
    results: list[RawOpportunity] = []
    found_at = datetime.now(timezone.utc).isoformat()

    if not api_key:
        print("[searcher] WARNING: TAVILY_API_KEY not set — skipping Tavily queries, checking direct sources only")
    else:
        client = TavilyClient(api_key=api_key)
        print(f"[searcher] Running {len(SEARCH_QUERIES)} search queries...")
        for i, query in enumerate(SEARCH_QUERIES):
            try:
                print(f"[searcher] Query {i+1}/{len(SEARCH_QUERIES)}: {query[:60]}...")
                if dry_run:
                    print("[searcher] DRY_RUN: skipping actual API call")
                    continue
                response = client.search(
                    query=query,
                    search_depth="basic",
                    max_results=8,
                    include_answer=False,
                )
                for r in response.get("results", []):
                    results.append(RawOpportunity(
                        title=r.get("title", "").strip(),
                        url=r.get("url", "").strip(),
                        snippet=r.get("content", "").strip()[:500],
                        source_query=query,
                        found_at=found_at,
                        raw_content=r.get("content", ""),
                    ))
            except Exception as e:
                print(f"[searcher] Query failed: {e}")

    # Direct source scrapes (always run, even if Tavily key is missing)
    print(f"[searcher] Checking {len(DIRECT_SOURCES)} direct sources...")
    for source in DIRECT_SOURCES:
        page_text = "" if dry_run else fetch_page(source["url"], timeout=12)
        snippet = page_text[:500] if page_text else f"Direct source: {source['type']}"
        results.append(RawOpportunity(
            title=source["name"],
            url=source["url"],
            snippet=snippet,
            source_query="direct_source",
            found_at=found_at,
            raw_content=page_text,
        ))

    # Calendar sources (pre-researched programs — checked passively every run)
    calendar_results = load_calendar_sources()
    results.extend(calendar_results)

    print(f"[searcher] Found {len(results)} raw results total")
    return results
