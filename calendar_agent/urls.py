"""Normalize program URLs for dedup and matching."""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse


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
