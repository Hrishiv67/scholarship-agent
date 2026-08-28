"""Classify programs by opportunity type (internship, scholarship, etc.)."""
from __future__ import annotations

PROGRAM_TYPES = (
    "internship",
    "scholarship",
    "fly_in",
    "apprenticeship",
    "research",
    "competition",
)

TYPE_LABELS = {
    "internship": "Internships",
    "scholarship": "Scholarships",
    "fly_in": "Fly-ins & campus visits",
    "apprenticeship": "Apprenticeships",
    "research": "Research programs",
    "competition": "Competitions",
}

_TYPE_ALIASES = {
    "local_scholarship": "scholarship",
    "research_program": "research",
    "fly-in": "fly_in",
    "flyin": "fly_in",
    "campus_visit": "fly_in",
    "unknown": "research",
}

_INTERN = ("intern", "internship", "co-op", "coop")
_SCHOLAR = ("scholarship", "scholar", "merit award", "financial award")
_FLY = ("fly-in", "fly in", "flyin", "open house", "preview weekend", "campus visit", "diversity visit")
_APPREN = ("apprenticeship", "apprentice", "pre-apprentice")
_RESEARCH = ("research program", "summer research", "research institute", "research internship", "primes", "rsi", "simr", "shtem")
_COMP = ("competition", "contest", "olympiad", "talent search", "science fair", "isef", "sts", "deca", "jshs")


def label(program_type: str) -> str:
    return TYPE_LABELS.get(program_type, program_type.replace("_", " ").title())


def classify_type(program: dict, research: dict | None = None) -> str:
    research = research or {}
    explicit = (research.get("program_type") or program.get("type") or "").strip().lower()
    if explicit in PROGRAM_TYPES:
        return explicit
    if explicit in _TYPE_ALIASES:
        return _TYPE_ALIASES[explicit]

    blob = " ".join(
        str(program.get(k) or "") for k in ("name", "url", "notes", "type", "award", "slug")
    ).lower()
    blob += " " + str(research.get("award_details") or "").lower()
    blob += " " + str(research.get("eligibility") or "").lower()

    scores = {
        "fly_in": sum(1 for k in _FLY if k in blob),
        "apprenticeship": sum(1 for k in _APPREN if k in blob),
        "scholarship": sum(1 for k in _SCHOLAR if k in blob),
        "competition": sum(1 for k in _COMP if k in blob),
        "internship": sum(1 for k in _INTERN if k in blob),
        "research": sum(1 for k in _RESEARCH if k in blob),
    }
    if "student leaders" in blob and scores["internship"] < 2:
        scores["internship"] += 2
    if "regeneron" in blob or "science talent" in blob:
        scores["competition"] += 3

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        if "intern" in blob:
            return "internship"
        return "research"
    return best
