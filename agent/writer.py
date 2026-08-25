"""
Drafts application prose (emails, essays, short answers) in Hrishiv's voice,
grounded only in profile facts, and fitted to any stated word/character limit.
"""
import os
import re
from pathlib import Path

import anthropic

from .profile_loader import Profile

_MODEL = "claude-haiku-4-5-20251001"
_STYLE_PATH = Path(__file__).parent.parent / "profile" / "writing_style.md"


def load_style() -> str:
    if _STYLE_PATH.exists():
        return _STYLE_PATH.read_text(encoding="utf-8")
    # Minimal fallback if the style file is missing.
    return (
        "Write as Hrishiv Khatiwala. Earnest, specific, grounded in real numbers. "
        "No em-dashes, no exclamation marks, no contractions in formal writing, no jargon, "
        "no emoji. Do not invent facts. Close emails with 'Best wishes,\\nHrishiv Khatiwala'."
    )


def facts_block(profile: Profile) -> str:
    a = profile.academic
    acts = "; ".join(f"{x.role} — {x.name}: {x.description}" for x in profile.activities[:5])
    res = "; ".join(f"{x.role} at {x.institution}: {x.description}" for x in profile.research[:3])
    awards = "; ".join(profile.awards[:6])
    return (
        f"Name: {profile.personal.full_name}. School: {a.current_school} "
        f"(GPA {a.gpa_weighted}W/{a.gpa_unweighted}UW, rank {a.class_rank}/{a.class_size}, "
        f"SAT {a.sat_total}). Intended major: {a.intended_major}. "
        f"Activities: {acts}. Research: {res}. Awards: {awards}. "
        f"Bio: {profile.essay_snippets.bio_150}"
    )


def _limit_from_prompt(prompt: str) -> tuple[int | None, int | None]:
    """Detect a word or character limit from a prompt string."""
    words = re.search(r'(\d{2,4})\s*[- ]?\s*word', prompt, re.I)
    chars = re.search(r'(\d{2,4})\s*[- ]?\s*character', prompt, re.I)
    return (int(words.group(1)) if words else None,
            int(chars.group(1)) if chars else None)


def _sanitize(text: str) -> str:
    """Enforce the hard voice rules the model sometimes ignores."""
    text = text.replace("—", ", ").replace("–", ", ")   # em/en dash -> comma
    text = text.replace("…", ".").replace("...", ".")     # ellipsis -> period
    text = text.replace("!", ".")                          # no exclamation marks
    text = re.sub(r"\s+,", ",", text)                      # tidy ", " artifacts
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _trim_words(text: str, max_words: int) -> str:
    parts = text.split()
    if len(parts) <= max_words:
        return text
    return " ".join(parts[:max_words]).rstrip(",.;:") + "."


def draft(prompt: str, profile: Profile, opp_title: str = "",
          max_words: int | None = None, max_chars: int | None = None) -> str:
    """Draft an in-voice answer to `prompt`, fitted to any detected/passed limit."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return profile.essay_snippets.bio_150

    if max_words is None or max_chars is None:
        w, c = _limit_from_prompt(prompt)
        max_words = max_words or w
        max_chars = max_chars or c

    limit_note = ""
    if max_words:
        limit_note = f"\nHard limit: {max_words} words. Do not exceed it."
    elif max_chars:
        limit_note = f"\nHard limit: {max_chars} characters. Do not exceed it."

    style = load_style()
    facts = facts_block(profile)

    system = (
        f"{style}\n\nUse ONLY these facts about the applicant; never invent anything:\n{facts}"
    )
    user = (
        f"Program: {opp_title}\n"
        f"Write his response to this application prompt in his voice:\n\"{prompt}\"\n"
        f"{limit_note}\n"
        f"If the prompt asks for a specific experience with this program that is not in the "
        f"facts above, write only what is truthfully supported and keep it general rather than "
        f"inventing details. Return only the response text."
    )

    try:
        msg = anthropic.Anthropic(api_key=api_key).messages.create(
            model=_MODEL,
            max_tokens=1200,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:
        print(f"[writer] draft failed: {type(e).__name__}: {str(e)[:120]}")
        return profile.essay_snippets.bio_150

    # Enforce hard voice rules, then limits.
    text = _sanitize(text)
    if max_words:
        text = _trim_words(text, max_words)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text
