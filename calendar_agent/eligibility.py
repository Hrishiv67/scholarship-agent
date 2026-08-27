"""Eligibility gates that still apply on the calendar.

Hrishiv: Green Hope HS, Cary NC, class of 2028, rising junior (grade 11),
male, US citizen, VEX (not FRC/FTC), already attended NCSSM Summer twice.
DOB is unknown — never invent one. Age-gated programs stay `verify`.
"""
from __future__ import annotations

_INELIGIBLE_PHRASES = (
    "women only", "women-only", "female students only", "for young women",
    "girls only", "women in stem only",
    "low-income only", "pell-eligible only", "must demonstrate financial need",
    "frc team", "ftc team", "first robotics competition required",
    "ncssm summer",
)
_SENIOR_PHRASES = (
    "high school seniors only", "seniors only", "class of 2027 only",
    "graduating seniors", "12th grade only", "current seniors",
)
_COST_PHRASES = (
    "application fee", "tuition of", "program fee", "cost to attend",
    "not a paid", "unpaid unless",
)


def classify_status(research: dict, program: dict) -> str:
    """eligible | seniors_later | ineligible | verify"""
    blob = " ".join(
        [
            str(research.get("eligibility") or ""),
            str(research.get("notes") or ""),
            str(program.get("notes") or ""),
            " ".join(research.get("requirements") or []),
        ]
    ).lower()

    if research.get("seniors_only") is True or any(p in blob for p in _SENIOR_PHRASES):
        return "seniors_later"
    if research.get("identity_restricted"):
        return "ineligible"
    if any(p in blob for p in _INELIGIBLE_PHRASES):
        return "ineligible"
    if research.get("grade_eligible") is False:
        return "ineligible"
    if research.get("grade_eligible") is True and not research.get("identity_restricted"):
        return "eligible"
    return "verify"


def costs_money(research: dict, program: dict) -> bool:
    if research.get("costs_money") is True:
        return True
    blob = f"{research.get('award_details', '')} {research.get('notes', '')} {program.get('award', '')}".lower()
    return any(p in blob for p in _COST_PHRASES)
