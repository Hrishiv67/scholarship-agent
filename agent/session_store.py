"""
Saves and restores Playwright browser sessions (cookies + localStorage) per domain.
Stored in profile/sessions/ — gitignored so auth tokens never reach GitHub.
On the next run, the agent restores a saved session and skips login entirely.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

SESSIONS_DIR = Path(__file__).parent.parent / "profile" / "sessions"


def _domain_key(url_or_domain: str) -> str:
    if url_or_domain.startswith("http"):
        domain = urlparse(url_or_domain).netloc.lower().removeprefix("www.")
    else:
        domain = url_or_domain.lower().removeprefix("www.")
    return hashlib.sha256(domain.encode()).hexdigest()[:12]


def session_path(url_or_domain: str) -> Path:
    return SESSIONS_DIR / f"{_domain_key(url_or_domain)}.json"


def has_session(url_or_domain: str) -> bool:
    return session_path(url_or_domain).exists()


def save(url_or_domain: str, storage_state: dict) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = session_path(url_or_domain)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f)
    domain = urlparse(url_or_domain).netloc if url_or_domain.startswith("http") else url_or_domain
    print(f"[session_store] Saved session for {domain}")


def load(url_or_domain: str) -> dict | None:
    path = session_path(url_or_domain)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[session_store] Failed to load session: {e}")
        return None


def delete(url_or_domain: str) -> None:
    path = session_path(url_or_domain)
    if path.exists():
        path.unlink()
        print(f"[session_store] Deleted session for {url_or_domain}")
