import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from tavily import TavilyClient

from calendar_agent.scraper import fetch_page

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")


def _tavily_api_key() -> str:
    """Same .env key the rest of the agent uses (TAVILY_API_KEY)."""
    load_dotenv(_ROOT / ".env")
    return (os.environ.get("TAVILY_API_KEY") or "").strip()


SEARCH_QUERIES = [
    # Summer 2027 paid internships / research (rising junior, class of 2028)
    '"summer 2027" "high school" internship OR "summer research" paid OR stipend apply OR "applications open" -site:reddit.com -site:indeed.com',
    '"high school" "summer 2027" paid internship NASA OR NIH OR NIST OR "national lab" OR SEAP OR AFRL apply',
    '"high school" internship "summer 2027" OR "summer 2027 internship" "apply now" OR "application opens" STEM -site:linkedin.com',
    'paid internship "high school students" "summer 2027" Raleigh OR Durham OR Cary OR "Research Triangle" apply -site:indeed.com',
    '"high school" "summer research" 2027 stipend OR paid "application deadline" OR "apply" NC State OR Duke OR UNC -site:reddit.com',
    '"rising junior" OR "class of 2028" "high school" "summer 2027" research OR internship paid apply',
    'site:nasa.gov OR site:stemgateway.nasa.gov "high school" internship 2027 apply',
    'site:training.nih.gov "summer internship" 2027 high school apply',
    'site:navalsteminterns.us SEAP OR NREIP 2027 apply high school',
    '"Bank of America Student Leaders" 2027 apply',
    '"Garcia program" OR "Simons Summer Research" Stony Brook 2027 apply',
    # Currently open scholarships (this month)
    '"no essay" scholarship apply 2026 "deadline" "August" OR "September" high school -site:reddit.com',
    'site:bold.org scholarship apply 2026 "no essay" OR "apply now"',
    'site:sallie.com "no essay" scholarship apply',
    '"high school" scholarship "apply now" 2026 "deadline" NC OR "North Carolina" -site:indeed.com',
    'paid internship "high school" "apply" site:ncsu.edu OR site:duke.edu OR site:unc.edu OR site:waketech.edu 2026 OR 2027',
    'paid internship "high school students" Raleigh OR Durham OR Cary NC 2026 OR 2027 "apply now" OR "applications open" -site:indeed.com -site:linkedin.com -site:ziprecruiter.com',
    '"high school" research program NC State OR Duke OR UNC 2026 OR 2027 "stipend" OR "paid" "application" -site:reddit.com -site:quora.com',
    '"high school" internship "Cary" OR "Research Triangle" OR "RTP" 2026 OR 2027 "apply" -site:indeed.com -site:glassdoor.com',
    '"high school" "summer research" "stipend" 2026 OR 2027 "application deadline" -site:reddit.com -site:collegevine.com',
    '"rising junior" OR "rising senior" "high school" research program 2026 OR 2027 "apply" "paid" -"college students" -"undergraduate"',
    'site:energy.gov OR site:noaa.gov "high school" intern OR student program 2026 OR 2027',
    '"fly-in" "high school" "class of 2028" OR "junior" 2026 OR 2027 apply -site:collegevine.com -site:reddit.com',
    '"no essay" scholarship "high school junior" OR "11th grade" OR "class of 2028" apply 2026 OR 2027 -"list of"',
    'scholarship "high school" "no application essay" OR "no essay required" 2026 2027 "apply" "open"',
    'paid apprenticeship "high school" STEM OR engineering OR software 2026 OR 2027 apply -site:indeed.com',
    'remote "high school" internship OR research "paid" OR "stipend" 2026 2027 apply flexible -site:indeed.com',
]

# Real apply pages that are open right now (checked every run, before web search).
OPEN_NOW = [
    {"name": "$25,000 Be Bold No-Essay Scholarship", "url": "https://bold.org/scholarships/the-be-bold-no-essay-scholarship/", "type": "scholarship"},
    {"name": "1000 Bold Points No-Essay Scholarship", "url": "https://bold.org/scholarships/bold-org-1000-points-no-essay-scholarship/", "type": "scholarship"},
    {"name": "$10,000 Scholarships360 No-Essay Scholarship", "url": "https://scholarships360.org/scholarships/search/10000-no-essay-scholarship/", "type": "scholarship"},
    {"name": "Niche $2,000 No-Essay Scholarship", "url": "https://www.niche.com/colleges/scholarships/no-essay-scholarship/", "type": "scholarship"},
    {"name": "College Board BigFuture Scholarships", "url": "https://bigfuture.collegeboard.org/pay-for-college/bigfuture-scholarships", "type": "scholarship"},
    {"name": "$2,000 Sallie No-Essay Scholarship", "url": "https://www.sallie.com/scholarships/no-essay", "type": "scholarship"},
]

# Paid summer 2027 internships / research — checked every run (many open in fall 2026).
SUMMER_2027 = [
    {"name": "NIH Summer Internship Program (SIP) 2027", "url": "https://www.training.nih.gov/research-training/pb/sip/", "type": "internship"},
    {"name": "Navy SEAP High School Internship 2027", "url": "https://www.navalsteminterns.us/seap/", "type": "internship"},
    {"name": "NIST Summer High School Internship Program", "url": "https://www.nist.gov/careers/summer-high-school-internship-program", "type": "internship"},
    {"name": "AFRL Scholars Program", "url": "https://afrlscholars.usra.edu/", "type": "internship"},
    {"name": "NASA Office of STEM Engagement Internships", "url": "https://intern.nasa.gov/", "type": "internship"},
    {"name": "NASA STEM Gateway Internships", "url": "https://stemgateway.nasa.gov/public/s/explore-opportunities", "type": "internship"},
    {"name": "NC State GRIP High School Research", "url": "https://grip.ncsu.edu/high-school/", "type": "research_program"},
    {"name": "Duke RISE Program", "url": "https://dukelife.duke.edu/programs/internships-and-research/rise/", "type": "research_program"},
    {"name": "GTRI High School Summer Internship 2027", "url": "https://gtri.gatech.edu/stem/high-school-summer-internship", "type": "internship"},
    {"name": "Bank of America Student Leaders 2027", "url": "https://about.bankofamerica.com/en/making-an-impact/student-leaders", "type": "internship"},
    {"name": "Garcia Summer Research Program (Stony Brook)", "url": "https://www.stonybrook.edu/commcms/garcia/", "type": "research_program"},
    {"name": "MIT PRIMES USA", "url": "https://math.mit.edu/research/highschool/primes/usa/", "type": "research_program"},
    {"name": "RSI Research Science Institute", "url": "https://www.cee.org/programs/research-science-institute", "type": "research_program"},
    {"name": "DOE WDTS Student Programs", "url": "https://science.osti.gov/wdts", "type": "internship"},
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
    {"name": "Niche $2,000 No-Essay Scholarship", "url": "https://www.niche.com/colleges/scholarships/no-essay-scholarship/", "type": "scholarship"},
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

        ptype = (program.get("type") or "").lower()
        if not include and ptype in ("internship", "research_program"):
            # Calendar dates are often still null; still surface summer research/internships.
            include = True

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
    seeds_only = os.environ.get("SEEDS_ONLY", "false").lower() == "true"
    api_key = _tavily_api_key()
    results: list[RawOpportunity] = []
    found_at = datetime.now(timezone.utc).isoformat()
    seen_urls: set[str] = set()

    def add_source(source: dict, source_query: str) -> None:
        url = (source.get("url") or "").strip()
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        page_text = "" if dry_run else fetch_page(url, timeout=12)
        snippet = page_text[:500] if page_text else f"Direct source: {source.get('type', '')}"
        results.append(RawOpportunity(
            title=source["name"],
            url=url,
            snippet=snippet,
            source_query=source_query,
            found_at=found_at,
            raw_content=page_text,
        ))

    print(f"[searcher] Checking {len(OPEN_NOW)} currently-open apply pages...")
    for source in OPEN_NOW:
        add_source(source, "open_now")

    print(f"[searcher] Checking {len(SUMMER_2027)} summer 2027 internship/research pages...")
    for source in SUMMER_2027:
        add_source(source, "summer_2027")

    if seeds_only:
        print(f"[searcher] SEEDS_ONLY: {len(results)} seed pages (skipping web search)")
        return results

    if not api_key:
        print("[searcher] WARNING: TAVILY_API_KEY not set in .env — skipping Tavily queries")
    else:
        client = TavilyClient(api_key=api_key)
        print("[searcher] Tavily web search enabled")
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
                    url = (r.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(RawOpportunity(
                        title=r.get("title", "").strip(),
                        url=url,
                        snippet=r.get("content", "").strip()[:500],
                        source_query=query,
                        found_at=found_at,
                        raw_content=r.get("content", ""),
                    ))
            except Exception as e:
                print(f"[searcher] Query failed: {e}")

    print(f"[searcher] Checking {len(DIRECT_SOURCES)} direct sources...")
    for source in DIRECT_SOURCES:
        add_source(source, "direct_source")

    calendar_results = load_calendar_sources()
    results.extend(calendar_results)

    print(f"[searcher] Found {len(results)} raw results total")
    return results
