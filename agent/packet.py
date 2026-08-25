"""
Writes a copy-paste application packet for any program the agent could not fully
submit itself. This is the durable output the user actually reuses: account login,
the direct link, every field value, and the essays drafted in their voice - saved
to a file so nothing has to be redone.
"""
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import writer

PACKETS_DIR = Path(__file__).parent.parent / "outputs" / "application_packets"


def _fields(profile: Profile) -> str:
    p, a = profile.personal, profile.academic
    lines = [
        f"- Full name: {p.full_name}",
        f"- Email: {p.email}",
        f"- Phone: {p.phone_formatted}",
        f"- Address: {p.address.line1}, {p.address.city}, {p.address.state} {p.address.zip}",
        f"- School: {a.current_school} (Class of {a.graduation_year}, grade {a.current_grade})",
        f"- GPA: {a.gpa_weighted} weighted / {a.gpa_unweighted} unweighted",
        f"- Class rank: {a.class_rank} of {a.class_size}",
        f"- SAT: {a.sat_total or 'n/a'}",
        f"- Intended major: {a.intended_major}",
        f"- LinkedIn: {p.linkedin}",
    ]
    if profile.guardians:
        g = next((x for x in profile.guardians if x.primary), profile.guardians[0])
        lines.append(f"- Parent/guardian: {g.full_name}, {g.email}, {g.phone_formatted}")
    return "\n".join(lines)


def _essays(opp: ClassifiedOpportunity, profile: Profile) -> str:
    prompts = list(opp.essay_prompts or [])
    if not prompts:
        prompts = [f"Why do you want to join {opp.title}? (about 250 words)"]
    out = []
    for prompt in prompts[:2]:
        answer = writer.draft(prompt, profile, opp.title)
        out.append(f"**Prompt:** {prompt}\n\n{answer}\n")
    return "\n---\n\n".join(out)


def write(opp: ClassifiedOpportunity, profile: Profile, login_note: str) -> str:
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    path = PACKETS_DIR / f"{opp.id}.md"
    content = f"""# Application Packet - {opp.title}

**Apply here:** {opp.url}
**Deadline:** {opp.deadline or 'check the page'}
**Award:** {opp.award_value or 'see page'}
**Account:** {login_note}
**Status:** {opp.reason or 'needs you to finish'}

Log in, paste these in, solve the CAPTCHA, and submit. The essays are written in your voice and fitted to the prompt.

## Your details
{_fields(profile)}

## Your essays (ready to paste)
{_essays(opp, profile)}
"""
    path.write_text(content, encoding="utf-8")
    return str(path)
