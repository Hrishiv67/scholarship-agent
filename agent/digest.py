import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

from .classifier import ClassifiedOpportunity
from .logger import RunLog
from .profile_loader import Profile

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body { font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto; color: #333; }
h1 { color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 8px; }
h2 { color: #16213e; margin-top: 24px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th { background: #16213e; color: white; padding: 8px; text-align: left; }
td { padding: 7px 8px; border-bottom: 1px solid #eee; }
tr:hover td { background: #f9f9f9; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
.submitted { background: #d4edda; color: #155724; }
.essay { background: #fff3cd; color: #856404; }
.semi { background: #cce5ff; color: #004085; }
.skipped { background: #f8d7da; color: #721c24; }
.stat { display: inline-block; background: #f0f4ff; border-radius: 8px; padding: 12px 20px; margin: 6px; text-align: center; }
.stat .num { font-size: 28px; font-weight: bold; color: #e94560; }
.stat .label { font-size: 12px; color: #666; }
a { color: #e94560; }
</style></head>
<body>
<h1>Scholarship Agent — Run Report</h1>
<p>Run completed: <strong>{{ run_time }}</strong></p>

<h2>This Run at a Glance</h2>
<div>
  <div class="stat"><div class="num">{{ stats.submitted }}</div><div class="label">Auto-Submitted</div></div>
  <div class="stat"><div class="num">{{ stats.essay_saved }}</div><div class="label">Essays Needed</div></div>
  <div class="stat"><div class="num">{{ stats.semi_queued }}</div><div class="label">Semi-Apply Queue</div></div>
  <div class="stat"><div class="num">{{ stats.skipped }}</div><div class="label">Skipped</div></div>
</div>

{% if submitted %}
<h2>✅ Applied This Run</h2>
<table>
<tr><th>Opportunity</th><th>Type</th><th>Award</th></tr>
{% for r in submitted %}
<tr>
  <td><a href="{{ r.url }}">{{ r.title }}</a></td>
  <td>{{ r.application_type }}</td>
  <td>{{ r.award_value or '—' }}</td>
</tr>
{% endfor %}
</table>
{% endif %}

{% if essays %}
<h2>✍️ Essays Needed (Add to data/essay_responses/)</h2>
<table>
<tr><th>Opportunity</th><th>Deadline</th><th>Award</th><th>File to Create</th></tr>
{% for r in essays %}
<tr>
  <td><a href="{{ r.url }}">{{ r.title }}</a></td>
  <td>{{ r.deadline or '?' }}</td>
  <td>{{ r.award_value or '—' }}</td>
  <td><code>{{ r.id }}.md</code></td>
</tr>
{% endfor %}
</table>
<p><em>Write your essay response in <code>data/essay_responses/OPP-XXXXXXXX-XXX.md</code>, commit & push — the next run will finish the application.</em></p>
{% endif %}

{% if semi %}
<h2>🖱️ Semi-Apply Queue (1 Click Needed from You)</h2>
<p>These were pre-filled but need you to solve a CAPTCHA or create an account:</p>
<table>
<tr><th>Opportunity</th><th>Award</th><th>Action</th></tr>
{% for r in semi %}
<tr>
  <td>{{ r.title }}</td>
  <td>{{ r.award_value or '—' }}</td>
  <td><a href="{{ r.url }}">Open & Submit →</a></td>
</tr>
{% endfor %}
</table>
{% endif %}

<hr>
<p style="color:#999;font-size:12px;">Scholarship Agent running on GitHub Actions · Mon/Wed/Fri 9am ET · <a href="https://github.com/Hrishiv67/scholarship-agent">View repo</a></p>
</body>
</html>"""


def send(run_log: RunLog, results: list[ClassifiedOpportunity], profile: Profile, dry_run: bool = False) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_address or not gmail_password:
        print("[digest] Gmail credentials not set — skipping digest")
        return

    run_time = datetime.now(timezone.utc).strftime("%A, %B %d %Y at %I:%M %p UTC")

    submitted = [r for r in results if r.tier == "auto_apply"]
    essays = [r for r in results if r.tier == "essay_pending"]
    semi = [r for r in results if r.tier == "semi_apply"]

    stats = {
        "submitted": run_log.outcomes.get("submitted", 0),
        "essay_saved": run_log.outcomes.get("essay_saved", 0),
        "semi_queued": run_log.outcomes.get("semi_queued", 0),
        "skipped": run_log.outcomes.get("skipped", 0),
    }

    html = Template(_HTML_TEMPLATE).render(
        run_time=run_time,
        stats=stats,
        submitted=submitted,
        essays=essays,
        semi=semi,
    )

    subject = f"Scholarship Agent Report — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Scholarship Agent <{gmail_address}>"
    msg["To"] = gmail_address
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    if dry_run:
        print(f"[digest] DRY_RUN: would send digest to {gmail_address}")
        print(f"[digest]   submitted={stats['submitted']} essays={stats['essay_saved']} semi={stats['semi_queued']}")
        return

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"[digest] Digest email sent to {gmail_address}")
    except Exception as e:
        print(f"[digest] Failed to send digest: {e}")
