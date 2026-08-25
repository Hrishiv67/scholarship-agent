"""
calendar_agent/scraper.py

Fetches a URL and returns cleaned readable text for Claude to analyze.
"""

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


def fetch_page(url: str, timeout: int = 15) -> str:
    """
    Fetch a URL and return its readable text, stripped of boilerplate.
    Returns empty string on any failure.
    Capped at MAX_CONTENT_CHARS to keep Claude prompt tokens predictable.
    """
    try:
        response = requests.get(url, headers=_HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"[scraper] TIMEOUT: {url}")
        return ""
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"[scraper] HTTP {code}: {url}")
        return ""
    except requests.exceptions.ConnectionError:
        print(f"[scraper] CONNECTION ERROR: {url}")
        return ""
    except Exception as e:
        print(f"[scraper] ERROR fetching {url}: {type(e).__name__}: {e}")
        return ""

    try:
        soup = BeautifulSoup(response.text, "lxml")
    except Exception:
        soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    raw_text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    text = "\n".join(lines)

    if not text:
        return "(page loaded but contained no readable text)"

    return text[:MAX_CONTENT_CHARS]
