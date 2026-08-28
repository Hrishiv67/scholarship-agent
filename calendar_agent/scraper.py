"""
calendar_agent/scraper.py

Fetches URLs and returns cleaned readable text for Claude to analyze.
Deep mode follows apply/deadline subpages on the same domain.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

_STRIP_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "iframe", "svg", "form", "button",
]

MAX_CONTENT_CHARS = 8000
DEEP_MAX_CHARS = 14000

_LINK_KEYWORDS = re.compile(
    r"apply|application|deadline|eligib|dates?|admission|how.to|faq|requirements",
    re.I,
)


def _extract_text(soup: BeautifulSoup) -> str:
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    raw_text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(lines)


def _get_html(url: str, timeout: int) -> tuple[str, BeautifulSoup] | tuple[None, None]:
    try:
        response = requests.get(url, headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"[scraper] TIMEOUT: {url}")
        return None, None
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"[scraper] HTTP {code}: {url}")
        return None, None
    except requests.exceptions.ConnectionError:
        print(f"[scraper] CONNECTION ERROR: {url}")
        return None, None
    except Exception as e:
        print(f"[scraper] ERROR fetching {url}: {type(e).__name__}: {e}")
        return None, None

    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:
        soup = BeautifulSoup(response.text, "html.parser")
    return response.text, soup


def _same_site(base: str, link: str) -> bool:
    base_host = (urlparse(base).hostname or "").lower().removeprefix("www.")
    link_host = (urlparse(link).hostname or "").lower().removeprefix("www.")
    return bool(base_host and link_host and base_host == link_host)


def _related_links(soup: BeautifulSoup, base_url: str, limit: int = 4) -> list[str]:
    seen: set[str] = set()
    found: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        full = urljoin(base_url, href)
        if not _same_site(base_url, full):
            continue
        norm = full.split("#")[0].rstrip("/")
        if norm == base_url.split("#")[0].rstrip("/") or norm in seen:
            continue
        label = f"{a.get_text(' ', strip=True)} {href}"
        if not _LINK_KEYWORDS.search(label):
            continue
        seen.add(norm)
        found.append(full)
        if len(found) >= limit:
            break
    return found


def fetch_page(url: str, timeout: int = 15, *, max_chars: int = MAX_CONTENT_CHARS) -> str:
    """Fetch a URL and return readable text. Empty string on failure."""
    _, soup = _get_html(url, timeout)
    if soup is None:
        return ""
    text = _extract_text(soup)
    if not text:
        return "(page loaded but contained no readable text)"
    return text[:max_chars]


def fetch_deep(url: str, timeout: int = 15, *, max_extra: int = 2) -> str:
    """Fetch main page plus apply/deadline subpages for deeper research."""
    _, soup = _get_html(url, timeout)
    if soup is None:
        return ""

    main = _extract_text(soup)
    if not main:
        return "(page loaded but contained no readable text)"

    parts = [f"=== Main page: {url} ===\n{main[:7000]}"]
    for link in _related_links(soup, url, limit=max_extra + 2)[:max_extra]:
        print(f"  [scraper] deep follow: {link[:80]}")
        extra = fetch_page(link, timeout=timeout, max_chars=3500)
        if extra and extra != "(page loaded but contained no readable text)":
            parts.append(f"=== Related page: {link} ===\n{extra}")

    combined = "\n\n".join(parts)
    return combined[:DEEP_MAX_CHARS]
