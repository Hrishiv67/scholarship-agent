"""
A registry of portal accounts, as a spreadsheet (outputs/accounts.csv).

Records both accounts the agent creates and the ones the user must create
manually (CAPTCHA/OAuth signups). Never stores the actual password: every
agent-created account uses the single PORTAL_PASSWORD, so the registry just
notes "your portal password".
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ACCOUNTS_PATH = Path(__file__).parent.parent / "outputs" / "accounts.csv"
_HEADER = ["Portal", "URL", "Login Email", "Password", "Created By", "Date", "Status", "Notes"]


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return url


def _load() -> dict:
    rows: dict[str, dict] = {}
    if ACCOUNTS_PATH.exists():
        with open(ACCOUNTS_PATH, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows[_domain(row.get("URL", ""))] = row
    return rows


def _save(rows: dict) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNTS_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_HEADER)
        w.writeheader()
        for row in sorted(rows.values(), key=lambda r: r.get("Portal", "")):
            w.writerow(row)


def record(portal: str, url: str, login_email: str, created_by: str,
           status: str, notes: str = "") -> None:
    """Upsert one account row, keyed by domain. Never downgrades a 'created' status."""
    rows = _load()
    key = _domain(url)
    existing = rows.get(key)
    # Do not overwrite a real created/verified account with a later "needs signup".
    if existing and "created" in existing.get("Status", "").lower() and "created" not in status.lower():
        return
    rows[key] = {
        "Portal": portal or key,
        "URL": url,
        "Login Email": login_email,
        "Password": "your portal password",
        "Created By": created_by,
        "Date": (existing or {}).get("Date") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "Status": status,
        "Notes": notes[:120],
    }
    _save(rows)
