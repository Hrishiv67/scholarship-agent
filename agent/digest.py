import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Template

from .classifier import ClassifiedOpportunity
from .logger import RunLog
from .profile_loader import Profile

_CALENDAR_PATH = Path(__file__).parent.parent / "outputs" / "program_calendar.json"
_MY_STATUS_PATH = Path(__file__).parent.parent / "outputs" / "my_status.json"

_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body { font-family: Arial, sans-serif; max-width: 720px; margin: 0 auto; color: #333; }
h1 { color: #1a1a2e; border-bottom: 2px solid #e94560; padding-bottom: 8px; }
h2 { color: #16213e; margin-top: 24px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th { background: #16213e; color: white; padding: 8px; text-align: left; font-size: 13px; }
td { padding: 7px 8px; border-bottom: 1px solid #eee; font-size: 13px; }
tr:hover td { background: #f9f9f9; }
.warn { background: #fff3cd; border: 1px solid #ffe08a; padding: 12px; border-radius: 6px; }
.yours { background: #ffe0e6; color: #8a1c34; font-weight: bold; padding: 2px 6px; border-radius: 4px; }
.due-soon { color: #c0392b; font-weight: bold; }
.stat { display: inline-block; background: #f0f4ff; border-radius: 8px; padding: 12px 18px; margin: 6px; text-align: center; }
.stat .num { font-size: 26px; font-weight: bold; color: #e94560; }
.stat .label { font-size: 12px; color: #666; }
a { color: #e94560; }
</style></head>
<body>
<h1>Scholarship Agent — Run Report</h1>
<p>Run completed: <strong>{{ run_time }}</strong></p>

{% if errors %}
<div class="warn">
<strong>{{ errors|length }} issue(s) this run</strong> — some items could not be classified and were tracked so they are not lost:
<ul>{% for e in errors %}<li>{{ e.error }}</li>{% endfor %}</ul>
</div>
{% endif %}

<h2>This Run at a Glance</h2>
<div>
  <div class="stat"><div class="num">{{ stats.submitted }}</div><div class="label">Auto-Submitted</div></div>
  <div class="stat"><div class="num">{{ stats.yours_manual }}</div><div class="label">Yours (Elite)</div></div>
  <div class="stat"><div class="num">{{ stats.tracked }}</div><div class="label">Needs You / Tracked</div></div>
  <div class="stat"><div class="num">{{ stats.skipped }}</div><div class="label">Skipped</div></div>
</div>

{% if deadlines %}
<h2>📅 Upcoming Deadlines</h2>
<table>
<tr><th>Deadline</th><th>Days Left</th><th>Program</th><th>Who</th><th>Confirmed?</th></tr>
{% for d in deadlines %}
<tr>
  <td class="{{ 'due-soon' if d.days_left <= 21 else '' }}">{{ d.deadline }}</td>
  <td class="{{ 'due-soon' if d.days_left <= 21 else '' }}">{{ d.days_left }}</td>
  <td><a href="{{ d.url }}">{{ d.name }}</a></td>
  <td>{% if d.elite %}<span class="yours">APPLY YOURSELF</span>{% else %}Auto{% endif %}</td>
  <td>{{ '✅' if d.confirmed else '⚠️' }}</td>
</tr>
{% endfor %}
</table>
{% endif %}

{% if submitted %}
<h2>✅ Applied This Run</h2>
<table>
<tr><th>Opportunity</th><th>Type</th><th>Award</th></tr>
{% for r in submitted %}
<tr><td><a href="{{ r.url }}">{{ r.title }}</a></td><td>{{ r.application_type }}</td><td>{{ r.award_value or '—' }}</td></tr>
{% endfor %}
</table>
{% endif %}

{% if yours %}
<h2>🎓 Reserved For You (Elite — Apply Yourself)</h2>
<table>
<tr><th>Opportunity</th><th>Deadline</th><th>Award</th></tr>
{% for r in yours %}
<tr><td><a href="{{ r.url }}">{{ r.title }}</a></td><td>{{ r.deadline or '?' }}</td><td>{{ r.award_value or '—' }}</td></tr>
{% endfor %}
</table>
{% endif %}

{% if account_setup %}
<h2>🔑 Needs a one-time Google/OAuth signup</h2>
<p>The agent creates accounts and solves CAPTCHA itself. These few sites only offer Sign in with Google (or similar), which you have to do once. After that the saved session is reused.</p>
<table>
<tr><th>Portal</th><th>Step</th><th>Link</th></tr>
{% for r in account_setup %}
<tr><td>{{ r.title }}</td><td>{{ r.notes }}</td><td><a href="{{ r.url }}">Sign up →</a></td></tr>
{% endfor %}
</table>
{% endif %}

{% if other_tracked %}
<h2>🖐️ Also Tracking</h2>
<table>
<tr><th>Opportunity</th><th>Why</th><th>Link</th></tr>
{% for r in other_tracked %}
<tr><td>{{ r.title }}</td><td>{{ r.notes }}</td><td><a href="{{ r.url }}">Open →</a></td></tr>
{% endfor %}
</table>
{% endif %}

<hr>
<p style="color:#999;font-size:12px;">Scholarship Agent on GitHub Actions · runs weekly · <a href="https://github.com/Hrishiv67/scholarship-agent">View repo</a></p>
</body>
</html>"""


def _load_my_status() -> dict:
    if _MY_STATUS_PATH.exists():
        try:
            return json.load(open(_MY_STATUS_PATH, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _upcoming_deadlines(limit: int = 40) -> list[dict]:
    """Build the deadline board from program_calendar.json, silencing handled ones."""
    if not _CALENDAR_PATH.exists():
        return []
    try:
        cal = json.load(open(_CALENDAR_PATH, encoding="utf-8"))
    except Exception:
        return []

    my_status = _load_my_status()
    now = datetime.now(timezone.utc)
    rows = []
    for p in cal.get("programs", []):
        deadline = p.get("deadline")
        if not deadline:
            continue
        if my_status.get(p.get("slug", "")) in ("applied", "skip"):
            continue
        try:
            dt = datetime.fromisoformat(deadline + "T00:00:00+00:00" if len(deadline) == 10 else deadline)
        except ValueError:
            continue
        days_left = (dt - now).days
        if days_left < 0:
            continue
        rows.append({
            "name": p.get("name", ""),
            "url": p.get("url", ""),
            "deadline": deadline,
            "days_left": days_left,
            "confirmed": bool(p.get("deadline_confirmed")),
            "elite": p.get("tier") == "elite",
        })
    rows.sort(key=lambda r: r["days_left"])
    return rows[:limit]


def send(run_log: RunLog, results: list[ClassifiedOpportunity], profile: Profile, dry_run: bool = False) -> None:
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_address or not gmail_password:
        print("[digest] Gmail credentials not set — skipping digest")
        return

    run_time = datetime.now(timezone.utc).strftime("%A, %B %d %Y at %I:%M %p UTC")

    submitted = [r for r in run_log.results if r.outcome == "submitted"]
    yours = [r for r in run_log.results if r.outcome == "yours_manual"]
    needs_you = [r for r in run_log.results if r.outcome == "tracked"]
    _setup_kw = ("oauth", "google sign", "sign in with", "continue with google")
    account_setup = [r for r in needs_you if any(k in (r.notes or "").lower() for k in _setup_kw)]
    other_tracked = [r for r in needs_you if r not in account_setup]

    stats = {
        "submitted": run_log.outcomes.get("submitted", 0),
        "yours_manual": run_log.outcomes.get("yours_manual", 0),
        "tracked": run_log.outcomes.get("tracked", 0),
        "skipped": run_log.outcomes.get("skipped", 0),
    }

    html = Template(_HTML_TEMPLATE).render(
        run_time=run_time,
        stats=stats,
        errors=run_log.errors,
        deadlines=_upcoming_deadlines(),
        submitted=submitted,
        yours=yours,
        account_setup=account_setup,
        other_tracked=other_tracked,
    )

    subject = f"Scholarship Agent Report — {datetime.now(timezone.utc).strftime('%b %d, %Y')}"

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Scholarship Agent <{gmail_address}>"
    msg["To"] = gmail_address
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    if dry_run:
        print(f"[digest] DRY_RUN: would send digest to {gmail_address}")
        print(f"[digest]   submitted={stats['submitted']} yours={stats['yours_manual']} "
              f"tracked={stats['tracked']} deadlines={len(_upcoming_deadlines())}")
        return

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(gmail_address, gmail_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"[digest] Digest email sent to {gmail_address}")
    except Exception as e:
        print(f"[digest] Failed to send digest: {e}")
