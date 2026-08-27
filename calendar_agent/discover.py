"""Find new official program pages via Tavily. Dates stay unconfirmed until research."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from .categories import TRACKS

_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

_SKIP_HOSTS = (
    "reddit.com", "www.reddit.com", "quora.com", "tiktok.com", "youtube.com",
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "collegevine.com", "collegeconfidential.com", "facebook.com", "x.com",
    "twitter.com", "pinterest.com", "medium.com",
)

QUERIES = {
    "ai": [
        '"high school" "artificial intelligence" OR "machine learning" internship OR research 2026 OR 2027 apply deadline -site:reddit.com',
        '"high school" "computer science" summer 2027 research OR internship paid OR stipend apply',
        'site:nasa.gov OR site:nist.gov "high school" intern 2027 computer OR data apply',
    ],
    "engineering": [
        '"high school" engineering internship "summer 2027" paid OR stipend apply deadline -site:indeed.com',
        'SEAP OR "AFRL Scholars" OR "NIH SIP" OR "NASA intern" high school 2027 apply',
        '"high school" research program engineering NC State OR Duke OR UNC 2027 apply',
    ],
    "business": [
        '"Bank of America Student Leaders" 2027 apply high school',
        '"high school" business internship OR "student leaders" OR entrepreneurship 2027 apply deadline',
        'DECA scholarship 2027 apply high school deadline',
    ],
}


def _tavily_key() -> str:
    load_dotenv(_ROOT / ".env")
    return (os.environ.get("TAVILY_API_KEY") or "").strip()


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] or "program"


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return not any(host == s or host.endswith("." + s) for s in _SKIP_HOSTS)


def discover(existing_urls: set[str], max_new: int = 15) -> list[dict]:
    key = _tavily_key()
    if not key:
        print("[discover] TAVILY_API_KEY not set — skipping web discovery")
        return []

    from tavily import TavilyClient

    client = TavilyClient(api_key=key)
    found: list[dict] = []
    seen = set(existing_urls)

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
                    max_results=6,
                    include_answer=False,
                )
            except Exception as e:
                print(f"[discover] query failed: {e}")
                continue
            for row in response.get("results") or []:
                url = (row.get("url") or "").strip()
                title = (row.get("title") or "").strip()
                if not url or url in seen or not _host_ok(url):
                    continue
                if not title:
                    continue
                seen.add(url)
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
                        f"via Tavily ({category}). Dates unconfirmed until official page research."
                    ),
                    "source": "tavily",
                })
                if len(found) >= max_new:
                    break
        if len(found) >= max_new:
            break

    print(f"[discover] {len(found)} new official-looking pages")
    return found
