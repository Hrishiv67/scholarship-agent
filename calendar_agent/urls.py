"""Normalize program URLs for dedup, matching, and link checks."""
from __future__ import annotations

import requests
from urllib.parse import urlparse, urlunparse

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip().lower())
    host = (parsed.hostname or "").removeprefix("www.")
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme or "https", host, path, "", "", ""))


def same_program(a: str, b: str) -> bool:
    na, nb = normalize_url(a), normalize_url(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    pa, pb = urlparse(na), urlparse(nb)
    if pa.hostname != pb.hostname:
        return False
    return pa.path.startswith(pb.path) or pb.path.startswith(pa.path)


def dedupe_entries(entries: list[dict], curated_slugs: set[str]) -> list[dict]:
    """One row per program. Prefer curated slugs; merge confirmed deadlines from dupes."""
    from urllib.parse import urlparse

    merged: list[dict] = []
    used: set[int] = set()

    def score(e: dict) -> tuple:
        return (
            e.get("slug") in curated_slugs,
            e.get("deadline_confirmed", False),
            e.get("confidence") in ("high", "medium"),
            len(e.get("name") or ""),
        )

    for i, a in enumerate(entries):
        if i in used:
            continue
        best = dict(a)
        for j, b in enumerate(entries):
            if j <= i or j in used:
                continue
            if not same_program(a.get("url", ""), b.get("url", "")):
                continue
            used.add(j)
            if score(b) > score(best):
                winner, loser = b, best
            else:
                winner, loser = best, b
            best = dict(winner)
            if loser.get("deadline_confirmed") and not best.get("deadline_confirmed"):
                best["deadline"] = loser.get("deadline")
                best["deadline_confirmed"] = True
                best["deadline_quote"] = loser.get("deadline_quote") or best.get("deadline_quote")
        merged.append(best)
        used.add(i)

    # Second pass: exact URL normalize dedup
    by_url: dict[str, dict] = {}
    for e in merged:
        key = normalize_url(e.get("url", ""))
        if not key:
            continue
        prev = by_url.get(key)
        if not prev or score(e) > score(prev):
            by_url[key] = e
    return list(by_url.values())


def check_url(url: str, timeout: int = 12) -> dict:
    """Return url_ok, url_status, url_final. Uses GET if HEAD is rejected."""
    if not url or not url.startswith("http"):
        return {"url_ok": False, "url_status": 0, "url_final": url or ""}
    try:
        r = requests.head(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400 or r.status_code == 405:
            r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True, stream=True)
            r.close()
        ok = r.status_code < 400
        return {"url_ok": ok, "url_status": r.status_code, "url_final": r.url or url}
    except requests.RequestException:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True, stream=True)
            r.close()
            return {"url_ok": r.status_code < 400, "url_status": r.status_code, "url_final": r.url or url}
        except requests.RequestException:
            return {"url_ok": False, "url_status": 0, "url_final": url}
