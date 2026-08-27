"""Find new official program pages via Tavily. Dates stay unconfirmed until research."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .categories import TRACKS
from .urls import normalize_url

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_SKIP_HOSTS = (
    "reddit.com", "quora.com", "tiktok.com", "youtube.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "collegevine.com", "collegeconfidential.com", "facebook.com", "x.com",
    "twitter.com", "pinterest.com", "medium.com", "ladderinternships.com",
    "deltainstitute.co", "teenlife.com", "internships.com",
)
_LISTICLE = re.compile(
    r"^\d+\s+.+(program|internship|scholarship|opportunit)",
    re.I,
)
_SKIP_PATH = (
    "/blog", "/blogs/", "/news/", "/article", "/list-of",
    "/dates", "/application-and-selection", "/apply-jpl", "/current-students/",
)
_GENERIC_TITLES = {
    "student employment", "internship program", "student opportunities",
    "internship programs", "summer internships for high school students -",
    "explore programs & apply",
}
_ALLOW_HOSTS = {
    "navalsteminterns.us", "about.bankofamerica.com", "bankofamerica.com",
    "cee.org", "societyforscience.org", "afrlscholars.usra.edu",
}

QUERIES = {
    "ai": [
        '"high school" "machine learning" OR "computer science" summer research 2027 site:.edu apply deadline',
        'site:stanford.edu OR site:mit.edu "high school" summer research internship apply',
        'site:nasa.gov OR site:nist.gov "high school" intern apply deadline',
    ],
    "engineering": [
        '"high school" engineering summer research 2027 site:.edu apply deadline',
        'SEAP OR "AFRL Scholars" OR "NIH SIP" high school apply site:.gov OR site:.edu',
        '"high school" paid internship NC State OR Duke OR UNC 2027 apply',
    ],
    "business": [
        '"Bank of America Student Leaders" 2027 apply',
        'DECA scholarship high school apply deadline site:deca.org',
        '"high school" entrepreneurship OR "student leaders" internship 2027 apply site:.edu',
    ],
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


def official_enough(url: str, title: str, existing_urls: set[str]) -> bool:
    title_l = (title or "").strip().lower()
    if _LISTICLE.search(title or ""):
        return False
    if len(title_l) < 12:
        return False
    if title_l in _GENERIC_TITLES:
        return False
    if not _host_ok(url):
        return False
    norm = normalize_url(url)
    for existing in existing_urls:
        if normalize_url(existing) == norm:
            return False
    return True


def discover(existing_urls: set[str], max_new: int = 15) -> list[dict]:
    key = _tavily_key()
    if not key:
        print("[discover] TAVILY_API_KEY not set — skipping web search")
        return []

    from tavily import TavilyClient

    client = TavilyClient(api_key=key)
    found: list[dict] = []
    seen = {normalize_url(u) for u in existing_urls if u}

    print("[discover] Tavily web search enabled")
    for category in TRACKS:
        for query in QUERIES[category]:
            if len(found) >= max_new:
                break
            try:
                print(f"[discover] {category}: {query[:70]}...")
                response = client.search(
                    query=query,
                    search_depth="basic",
                    max_results=5,
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
                seen.add(norm)
                found.append({
                    "slug": _slug(title),
                    "name": title[:120],
                    "url": url,
                    "type": "unknown",
                    "tier": "unknown",
                    "category": category,
                    "typical_open": "",
                    "typical_deadline": "",
                    "award": "",
                    "requires": [],
                    "notes": (
                        f"Discovered {datetime.now(timezone.utc).date().isoformat()} "
                        f"via Tavily ({category}). Pending official page verification."
                    ),
                    "source": "tavily",
                })
                if len(found) >= max_new:
                    break
        if len(found) >= max_new:
            break

    print(f"[discover] {len(found)} new official-looking pages")
    return found
