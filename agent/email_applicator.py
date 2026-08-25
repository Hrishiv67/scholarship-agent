import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import writer

RESUME_PATH = Path(__file__).parent.parent / "profile" / "resume.pdf"
CV_PATH = Path(__file__).parent.parent / "profile" / "cv_combined.txt"


def _generate_intro(opp: ClassifiedOpportunity, profile: Profile) -> str:
    prompt = (
        f"Write the opening 2-3 sentences of a professional application email for this "
        f"opportunity: \"{opp.title}\". Context from the posting: {opp.snippet[:300]}. "
        f"State genuine, specific interest and why it fits before any ask. Do not start with "
        f"\"I am writing to\". Return only the sentences."
    )
    return writer.draft(prompt, profile, opp.title)


def _build_email_body(opp: ClassifiedOpportunity, profile: Profile, intro: str) -> str:
    activities_top3 = "\n".join(
        f"  - {a.role} at {a.name}: {a.description[:100]}"
        for a in profile.activities[:3]
    )
    research_top = "\n".join(
        f"  - {r.role} at {r.institution}: {r.description[:100]}"
        for r in profile.research[:2]
    )
    return f"""{intro}

As a rising junior at {profile.academic.current_school} (GPA {profile.academic.gpa_weighted} weighted, Class Rank {profile.academic.class_rank}/{profile.academic.class_size}), I have pursued STEM research and leadership extensively:

Research:
{research_top}

Leadership & Competitions:
{activities_top3}

I have attached my resume for your review. I would welcome the opportunity to contribute to your program and am available to discuss further.

Best wishes,
{profile.personal.full_name}
{profile.academic.current_school}, Class of {profile.academic.graduation_year}
{profile.personal.email} | {profile.personal.phone_formatted}
{profile.personal.linkedin}"""


def _build_pdf_resume(profile: Profile) -> bool:
    """Generate resume.pdf from cv_combined.txt using fpdf2. Returns True on success."""
    if RESUME_PATH.exists():
        return True
    if not CV_PATH.exists():
        print("[email] cv_combined.txt not found — cannot generate PDF")
        return False
    def _latin1(s: str) -> str:
        # Core fonts are latin-1 only; map common unicode then drop the rest.
        for a, b in (("—", "-"), ("–", "-"), ("•", "-"), ("…", "..."),
                     ("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
                     ("━", ""), ("─", ""), (" ", " ")):
            s = s.replace(a, b)
        s = s.encode("latin-1", "replace").decode("latin-1")
        # Break very long unbreakable tokens (e.g. URLs) so multi_cell can wrap.
        return " ".join(
            tok if len(tok) <= 60 else " ".join(tok[i:i + 60] for i in range(0, len(tok), 60))
            for tok in s.split(" ")
        )

    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.set_margins(20, 20, 20)
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)

        text = CV_PATH.read_text(encoding="utf-8")
        for raw_line in text.split("\n"):
            line = _latin1(raw_line.rstrip())
            if not line.strip():
                pdf.ln(2)
                continue
            is_header = raw_line.isupper() or "━" in raw_line
            pdf.set_font("Helvetica", style="B" if is_header else "", size=11 if is_header else 10)
            pdf.multi_cell(0, 6 if is_header else 5, line, new_x="LMARGIN", new_y="NEXT")

        pdf.output(str(RESUME_PATH))
        print(f"[email] Generated resume PDF at {RESUME_PATH}")
        return True
    except Exception as e:
        print(f"[email] PDF generation failed: {e}")
        return False


def send_application(opp: ClassifiedOpportunity, profile: Profile, to_email: str, dry_run: bool = False) -> bool:
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_address or not gmail_password:
        print("[email] Gmail credentials not set — skipping")
        return False

    _build_pdf_resume(profile)

    intro = _generate_intro(opp, profile)
    body = writer._sanitize(_build_email_body(opp, profile, intro))

    subject = f"Application for {opp.title} - {profile.personal.full_name}, Rising Junior, {profile.academic.current_school}"

    msg = MIMEMultipart()
    msg["From"] = f"{profile.personal.full_name} <{gmail_address}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach resume PDF if it exists
    if RESUME_PATH.exists():
        with open(RESUME_PATH, "rb") as f:
            attach = MIMEApplication(f.read(), _subtype="pdf")
            attach.add_header("Content-Disposition", "attachment", filename="Hrishiv_Khatiwala_Resume.pdf")
            msg.attach(attach)

    if dry_run:
        print(f"[email] DRY_RUN: would send to {to_email} — Subject: {subject[:60]}...")
        return True

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, to_email, msg.as_string())
        print(f"[email] Sent application email to {to_email} for: {opp.title}")
        return True
    except Exception as e:
        print(f"[email] Failed to send email: {e}")
        return False


def send_handoff(opp: ClassifiedOpportunity, reason: str, dry_run: bool = False) -> bool:
    """Immediately email a direct hand-off link when a human step blocks the agent
    (CAPTCHA, OAuth signup). The next run resumes from the saved session."""
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_address or not gmail_password:
        return False

    body = (
        f"The agent got everything ready for this application but needs you for one step "
        f"({reason}).\n\n"
        f"Program: {opp.title}\n"
        f"Open this page and complete the step:\n{opp.url}\n\n"
        f"Once done, the next run will resume and finish the rest.\n\n"
        f"Best wishes,\nScholarship Agent"
    )
    msg = MIMEMultipart()
    msg["From"] = f"Scholarship Agent <{gmail_address}>"
    msg["To"] = gmail_address
    msg["Subject"] = f"Action needed ({reason}): {opp.title[:60]}"
    msg.attach(MIMEText(body, "plain"))

    if dry_run:
        print(f"[email] DRY_RUN: would send hand-off for {opp.title[:50]} ({reason})")
        return True
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"[email] Hand-off email sent for {opp.title[:50]}")
        return True
    except Exception as e:
        print(f"[email] Hand-off email failed: {e}")
        return False


def send_test(profile: Profile) -> bool:
    """Send a test email to yourself to verify SMTP works."""
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_address or not gmail_password:
        print("[email] Gmail credentials not set in environment")
        return False

    msg = MIMEMultipart()
    msg["From"] = gmail_address
    msg["To"] = gmail_address
    msg["Subject"] = "Scholarship Agent — Email Test"
    msg.attach(MIMEText(
        f"Email test from scholarship agent.\n\nProfile loaded: {profile.personal.full_name}\nEmail: {profile.personal.email}",
        "plain"
    ))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"[email] Test email sent to {gmail_address}")
        return True
    except Exception as e:
        print(f"[email] Test email failed: {e}")
        return False
