"""Eligibility gates: HS students, paid opportunities, no degree requirements."""
from __future__ import annotations

from .program_types import classify_type

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
_DEGREE_PHRASES = (
    "bachelor's degree", "bachelors degree", "bachelor degree required",
    "college degree required", "must have a degree", "degree required",
    "undergraduate student only", "undergraduate students only",
    "graduate student", "graduate students", "phd student", "doctoral student",
    "must be enrolled in college", "currently enrolled in a university",
    "currently enrolled in college", "college sophomore", "college junior",
    "college senior", "university student only", "post-baccalaureate",
    "associate degree required", "master's degree", "masters degree",
    "must be a college", "enrolled in an accredited college",
)
_COLLEGE_ONLY_PHRASES = (
    "college students only", "undergraduates only", "undergraduate only",
    "not open to high school", "no high school students",
    "college-level only",
)
_UNPAID_PHRASES = (
    "unpaid internship", "unpaid program", "no stipend", "without pay",
    "volunteer only", "without compensation", "not paid", "no compensation",
)
_PAID_POSITIVE = (
    "stipend", "paid", "scholarship", "award", "all-expenses", "all expenses",
    "travel covered", "fully funded", "free to attend", "no cost to students",
    "compensation", "$",
)


def _blob(research: dict, program: dict) -> str:
    return " ".join(
        [
            str(research.get("eligibility") or ""),
            str(research.get("notes") or ""),
            str(research.get("award_details") or ""),
            str(program.get("notes") or ""),
            str(program.get("award") or ""),
            " ".join(research.get("requirements") or []),
        ]
    ).lower()


def degree_required(research: dict, program: dict) -> bool:
    if research.get("degree_required") is True:
        return True
    if research.get("high_school_ok") is False:
        return True
    text = _blob(research, program)
    if any(p in text for p in _COLLEGE_ONLY_PHRASES):
        return True
    if any(p in text for p in _DEGREE_PHRASES):
        return True
    return False


def is_paid(research: dict, program: dict) -> bool | None:
    """True=paid/stipend/covered, False=clearly unpaid, None=unknown."""
    if research.get("is_paid") is True:
        return True
    if research.get("is_paid") is False:
        return False
    if research.get("costs_money") is True:
        return False

    ptype = classify_type(program, research)
    text = _blob(research, program)

    if any(p in text for p in _UNPAID_PHRASES):
        return False
    if ptype == "fly_in" and any(
        k in text for k in ("all-expenses", "all expenses", "travel covered", "free to attend", "no cost")
    ):
        return True
    if ptype == "scholarship" and ("$" in text or "scholarship" in text or "award" in text):
        return True
    if any(p in text for p in _PAID_POSITIVE):
        return True
    if ptype in ("internship", "research", "apprenticeship"):
        return None
    return None


def classify_status(research: dict, program: dict) -> str:
    """eligible | seniors_later | ineligible | verify"""
    text = _blob(research, program)

    if not research.get("url_ok", True):
        return "ineligible"

    if research.get("seniors_only") is True or any(p in text for p in _SENIOR_PHRASES):
        return "seniors_later"
    if research.get("identity_restricted"):
        return "ineligible"
    if any(p in text for p in _INELIGIBLE_PHRASES):
        return "ineligible"
    if degree_required(research, program):
        return "ineligible"
    if research.get("grade_eligible") is False:
        return "ineligible"

    paid = is_paid(research, program)
    ptype = classify_type(program, research)
    if paid is False and ptype in ("internship", "research", "apprenticeship"):
        return "ineligible"

    if research.get("grade_eligible") is True and not research.get("identity_restricted"):
        return "eligible"
    if paid is True and not degree_required(research, program):
        return "eligible"
    return "verify"


def costs_money(research: dict, program: dict) -> bool:
    if research.get("costs_money") is True:
        return True
    text = _blob(research, program)
    return any(
        p in text
        for p in ("application fee", "tuition of", "program fee", "cost to attend")
    )
