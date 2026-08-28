"""Find new official program pages via Tavily. Dates stay unconfirmed until research."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .categories import TRACKS, categorize
from .program_types import PROGRAM_TYPES
from .urls import check_url, normalize_url

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_SKIP_HOSTS = (
    "reddit.com", "quora.com", "tiktok.com", "youtube.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "collegevine.com", "collegeconfidential.com", "facebook.com", "x.com",
    "twitter.com", "pinterest.com", "medium.com", "ladderinternships.com",
    "deltainstitute.co", "teenlife.com", "internships.com", "niche.com",
    "bold.org", "scholarships.com", "fastweb.com", "chegg.com",
)
_LISTICLE = re.compile(
    r"^\d+\s+.+(program|internship|scholarship|opportunit)",
    re.I,
)
_SKIP_PATH = (
    "/blog", "/blogs/", "/news/", "/article", "/list-of",
    "/dates", "/application-and-selection", "/apply-jpl", "/current-students/",
    "/careers/", "/jobs/", "/faculty/", "/staff/",
)
_GENERIC_TITLES = {
    "student employment", "internship program", "student opportunities",
    "internship programs", "summer internships for high school students -",
    "explore programs & apply", "careers", "job openings",
}
_SKIP_TITLE_FRAGMENTS = (
    "faq", "frequently asked", "internships -", "resources/internships",
    "for employers", "alumni", "graduate", "faculty",
)
_ALLOW_HOSTS = {
    "navalsteminterns.us", "about.bankofamerica.com", "bankofamerica.com",
    "cee.org", "societyforscience.org", "afrlscholars.usra.edu",
    "deca.org", "coca-colascholarsfoundation.org", "intern.nasa.gov",
}

TYPE_QUERIES: dict[str, list[str]] = {
    "internship": [
        '"high school" paid summer internship stipend site:.edu OR site:.gov apply',
        'NASA OR NIH OR NIST "high school" intern stipend apply deadline',
        '"high school" engineering internship paid NC OR Cary apply site:.edu',
    ],
    "scholarship": [
        '"high school" STEM scholarship apply deadline site:.edu OR site:.org',
        'DECA OR "science talent" OR Davidson scholarship high school apply',
        'merit scholarship high school junior apply site:.edu',
    ],
    "fly_in": [
        '"fly-in" OR "fly in" high school engineering diversity campus visit apply site:.edu',
        '"preview weekend" OR "open house" high school students engineering apply',
    ],
    "apprenticeship": [
        '"high school" apprenticeship paid STEM site:.gov OR site:.edu apply',
        'pre-apprenticeship high school paid manufacturing OR engineering',
    ],
    "research": [
        '"high school" summer research stipend paid site:.edu apply deadline',
        'RSI OR PRIMES OR "summer science" high school research apply site:.edu',
    ],
    "competition": [
        'Regeneron STS OR ISEF OR JSHS high school competition apply deadline',
        'high school science olympiad OR math competition scholarship apply',
    ],
}

TRACK_HINTS = {
    "ai": ("machine learning", "computer science", "artificial intelligence", "data science", "primes"),
    "engineering": ("engineering", "nasa", "physics", "robotics", "stem", "nist", "afrl"),
    "business": ("business", "deca", "entrepreneur", "finance", "student leaders"),
}


def _tavily_key() -> str:
    load_dotenv(_ROOT / ".env")
    return (os.environ.get("TAVILY_API_KEY") or "").strip()


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "program"


def _host_ok(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = (parsed.path or "").lower()
    if not host:
        return False
    if any(host == s or host.endswith("." + s) for s in _SKIP_HOSTS):
        return False
    if any(p in path for p in _SKIP_PATH):
        return False
    if host in _ALLOW_HOSTS:
        return True
    return host.endswith(".edu") or host.endswith(".gov")


def _infer_category(title: str, url: str, query_track: str = "") -> str:
    blob = f"{title} {url}".lower()
    for track, hints in TRACK_HINTS.items():
        if any(h in blob for h in hints):
            return track
    if query_track in TRACKS:
        return query_track
    return categorize({"name": title, "url": url, "type": "unknown"})


def official_enough(url: str, title: str, existing_urls: set[str]) -> bool:
    title_l = (title or "").strip().lower()
    if _LISTICLE.search(title or ""):
        return False
    if len(title_l) < 12:
        return False
    if title_l in _GENERIC_TITLES:
        return False
    if any(f in title_l for f in _SKIP_TITLE_FRAGMENTS):
        return False
    if not _host_ok(url):
        return False
    norm = normalize_url(url)
    for existing in existing_urls:
        if normalize_url(existing) == norm:
            return False
    link = check_url(url)
    if not link["url_ok"]:
        return False
    return True


def discover(existing_urls: set[str], max_new: int = 30) -> list[dict]:
    key = _tavily_key()
    if not key:
        print("[discover] TAVILY_API_KEY not set — skipping web search")
        return []

    from tavily import TavilyClient

    client = TavilyClient(api_key=key)
    found: list[dict] = []
    seen = {normalize_url(u) for u in existing_urls if u}
    depth = os.environ.get("TAVILY_DEPTH", "advanced")

    print(f"[discover] Tavily deep search enabled (depth={depth})")
    for ptype in PROGRAM_TYPES:
        for query in TYPE_QUERIES.get(ptype, []):
            if len(found) >= max_new:
                break
            try:
                print(f"[discover] {ptype}: {query[:70]}...")
                response = client.search(
                    query=query,
                    search_depth=depth,
                    max_results=6,
                    include_answer=False,
                )
            except Exception as e:
                print(f"[discover] query failed: {e}")
                continue
            for row in response.get("results") or []:
                url = (row.get("url") or "").strip()
                title = (row.get("title") or "").strip()
                norm = normalize_url(url)
                if not url or norm in seen:
                    continue
                if not official_enough(url, title, existing_urls):
                    continue
                link = check_url(url)
                final_url = link["url_final"] if link["url_ok"] else url
                seen.add(normalize_url(final_url))
                category = _infer_category(title, final_url)
                found.append({
                    "slug": _slug(title),
                    "name": title[:120],
                    "url": final_url,
                    "type": ptype,
                    "tier": "unknown",
                    "category": category,
                    "typical_open": "",
                    "typical_deadline": "",
                    "award": "",
                    "requires": [],
                    "notes": (
                        f"Discovered {datetime.now(timezone.utc).date().isoformat()} "
                        f"via Tavily ({ptype}). Pending official page verification."
                    ),
                    "source": "tavily",
                })
                if len(found) >= max_new:
                    break
        if len(found) >= max_new:
            break

    print(f"[discover] {len(found)} new official-looking pages (links verified)")
    return found
