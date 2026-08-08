import os
from dataclasses import dataclass
from datetime import datetime, timezone

from tavily import TavilyClient

SEARCH_QUERIES = [
    # Priority 1 — RDU / NC local
    "paid internship high school students RDU Raleigh Durham 2027",
    "paid internship high school junior STEM North Carolina summer 2027",
    "high school research internship NC State Duke UNC summer 2027 paid stipend",
    "engineering internship high school Cary NC 2027 application open",
    "NC scholarship high school junior STEM leadership 2027 no essay",
    # Priority 2 — National STEM programs
    "paid summer research program high school 2027 STEM engineering application",
    "research internship high school rising junior aerospace computer science 2027",
    "RSI PRIMES Clark Scholar Siemens high school summer program 2027",
    "NASA DOE NOAA high school internship program 2027 application",
    "SAS Cisco Red Hat Epic Games high school internship RDU 2027",
    # Priority 3 — Fly-in programs
    "fly-in program high school junior 2027 STEM engineering application open",
    "college fly-in program high school 2027 diversity STEM no essay",
    "diversity fly-in high school junior aerospace engineering computer science 2027",
    # Priority 4 — No-essay scholarships
    "no essay scholarship high school junior 2027 apply",
    "scholarship high school 11th grade no essay rolling 2026 2027",
]

# High-value direct sources checked every run
DIRECT_SOURCES = [
    {"name": "Scholarships360 No-Essay List", "url": "https://scholarships360.org/scholarships/no-essay-scholarships/", "type": "scholarship_listing"},
    {"name": "Going Merry Scholarships", "url": "https://www.goingmerry.com/scholarships", "type": "scholarship_listing"},
    {"name": "Triangle Community Foundation Scholarships", "url": "https://www.trianglecf.org/grants-scholarships/scholarships/", "type": "local_scholarship"},
    {"name": "NC State High School Outreach", "url": "https://www.ncsu.edu/admissions/undergraduate/explore/high-school/", "type": "program"},
    {"name": "College Board Opportunity Scholarships", "url": "https://opportunityscholarships.collegeboard.org/", "type": "scholarship"},
    {"name": "QuestBridge Programs", "url": "https://www.questbridge.org/high-school-students/scholar-program", "type": "fly_in_scholarship"},
    {"name": "Niche No-Essay Scholarship", "url": "https://www.niche.com/colleges/scholarships/no-essay/", "type": "scholarship"},
    # Fly-in programs
    {"name": "MIT Diversity Open House", "url": "https://mitadmissions.org/apply/experience/campus-preview-weekend/", "type": "fly_in"},
    {"name": "Stanford Engineering Diversity", "url": "https://engineering.stanford.edu/students-academics/equity-and-inclusion-initiatives/prospective-undergraduate-students/discover", "type": "fly_in"},
    {"name": "Carnegie Mellon Pre-College", "url": "https://www.cmu.edu/pre-college/", "type": "fly_in"},
    {"name": "Georgia Tech FOCUS", "url": "https://admission.gatech.edu/first-year/campus-visit/focus", "type": "fly_in"},
    {"name": "Duke Engineering Fly-In", "url": "https://pratt.duke.edu/undergrad/apply/diversity", "type": "fly_in"},
]


@dataclass
class RawOpportunity:
    title: str
    url: str
    snippet: str
    source_query: str
    found_at: str
    raw_content: str = ""


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
        results.append(RawOpportunity(
            title=source["name"],
            url=source["url"],
            snippet=f"Direct source: {source['type']}",
            source_query="direct_source",
            found_at=found_at,
        ))

    print(f"[searcher] Found {len(results)} raw results total")
    return results
