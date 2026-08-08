import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile

RESUME_PATH = Path(__file__).parent.parent / "profile" / "resume.pdf"
CV_PATH = Path(__file__).parent.parent / "profile" / "cv_combined.txt"


def _generate_intro(opp: ClassifiedOpportunity, profile: Profile) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return f"I am writing to express my strong interest in the {opp.title} opportunity."

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": f"""Write exactly 2-3 sentences as the opening paragraph of a professional application email from Hrishiv Khatiwala (rising 11th grader, Green Hope High School, Cary NC) applying for this opportunity: "{opp.title}".

Opportunity description: {opp.snippet[:300]}

His strongest relevant credentials: {profile.academic.current_school}, GPA {profile.academic.gpa_weighted}W, research at Duke and NC State, 2nd of 1,001 teams at American Rocketry Challenge nationally, VEX Robotics top 150 worldwide, published paper.

Be specific to this opportunity. Do not start with "I". Do not use "I am writing to". Write naturally, not generically. Return only the sentences, no subject line."""}],
        )
        return msg.content[0].text.strip()
    except Exception:
        return f"I am writing to apply for the {opp.title} opportunity at your organization."


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

Sincerely,
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
    try:
        from fpdf import FPDF

        class PDF(FPDF):
            pass

        pdf = PDF()
        pdf.set_margins(20, 20, 20)
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)

        text = CV_PATH.read_text(encoding="utf-8")
        for line in text.split("\n"):
            line = line.rstrip()
            if not line:
                pdf.ln(2)
                continue
            # Detect section headers (all caps or contains ━)
            if line.isupper() or "━" in line:
                pdf.set_font("Helvetica", style="B", size=11)
                pdf.cell(0, 6, line.replace("━", ""), ln=True)
                pdf.set_font("Helvetica", size=10)
            else:
                # Wrap long lines
                pdf.multi_cell(0, 5, line)

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
    body = _build_email_body(opp, profile, intro)

    subject = f"Application for {opp.title} — {profile.personal.full_name}, Rising Junior, {profile.academic.current_school}"

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
