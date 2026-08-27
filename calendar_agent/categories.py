"""Assign each program to AI, Engineering, or Business.

A program has one primary track so the calendar stays scannable.
Overrides in programs.json (`category`) always win. Otherwise keywords
on the name, URL, notes, and type decide. Anything that is not a field
program (generic merit scholarships, fly-ins) is `general` and listed
separately — never stuffed into a track it does not belong to.
"""
from __future__ import annotations

TRACKS = ("ai", "engineering", "business")
VALID = TRACKS + ("general",)

_AI = (
    "artificial intelligence", "machine learning", " deep learning",
    "computer science", "computer-science", "data science", "neural",
    "coding", "software", "app challenge", "hackathon", "primes",
    "informatics", "computational", "analytics scholarship", "cssi",
    "code.org", "programming",
)
_ENG = (
    "engineer", "nasa", "nih", "nist", "seap", "nreip", "afrl", "nrl",
    "rocketry", "robotics", "vex", "physics", "aerospace", "aiaa",
    "mechanical", "electrical", "biomedical", "bme", "grip", "beam",
    "clark scholar", "rsi", "cosmos", "simons", "doe ", "wdts",
    "lockheed", "noaa", "epa", "ssp", "science talent", "isef",
    "jshs", "governor's school", "mites", "mostec", "sams", "stem",
    "apprenticeship", "laboratory", "national lab",
)
_BUS = (
    "business", "deca", "entrepreneur", "finance", "economics",
    "bank of america", "student leaders", "accounting", "marketing",
    "consulting", "leadership in the business", "wharton",
    "young entrepreneurs", "junior achievement", "stock market",
    "fbbla", "fbla",
)


def categorize(program: dict) -> str:
    explicit = (program.get("category") or "").strip().lower()
    if explicit in VALID:
        return explicit

    blob = " ".join(
        str(program.get(k) or "")
        for k in ("name", "url", "notes", "type", "award", "slug")
    ).lower()

    scores = {
        "ai": sum(1 for k in _AI if k in blob),
        "engineering": sum(1 for k in _ENG if k in blob),
        "business": sum(1 for k in _BUS if k in blob),
    }
    # SAS analytics is AI/data, not generic business
    if "sas" in blob and "analytic" in blob:
        scores["ai"] += 2
    if "congressional app" in blob:
        scores["ai"] += 3

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    # Tie-break: AI over engineering when both match (CS research)
    if scores["ai"] == scores["engineering"] == scores[best] and scores["ai"] > 0:
        return "ai"
    return best


def label(category: str) -> str:
    return {
        "ai": "AI",
        "engineering": "Engineering",
        "business": "Business",
        "general": "General (not field-specific)",
    }.get(category, category.title())
