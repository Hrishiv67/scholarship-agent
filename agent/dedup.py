import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

DEDUP_PATH = Path(__file__).parent.parent / "data" / "dedup.json"

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "fbclid", "gclid", "ref", "referrer", "source", "_ga",
}


def normalize_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip().rstrip("/"))
        qs = parse_qs(parsed.query, keep_blank_values=True)
        clean_qs = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
        netloc = parsed.netloc.lower().removeprefix("www.")
        clean = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=netloc,
            query=urlencode(clean_qs, doseq=True),
            fragment="",
        )
        return urlunparse(clean)
    except Exception:
        return url.strip()


def make_key(url: str, title: str) -> str:
    normalized = normalize_url(url) + "|" + title.lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


@dataclass
class DedupEntry:
    id: str
    title: str
    url: str
    first_seen: str
    status: str  # submitted | essay_pending | skipped | semi_apply_queued
    submitted_at: str = ""
    application_type: str = ""
    tier: str = ""
    award_value: str = ""
    notes: str = ""


@dataclass
class DedupStore:
    entries: dict[str, DedupEntry] = field(default_factory=dict)
    _run_counter: int = field(default=0, repr=False)

    def seen(self, url: str, title: str) -> bool:
        return make_key(url, title) in self.entries

    def mark(self, url: str, title: str, status: str, opp_id: str,
             application_type: str = "", tier: str = "",
             award_value: str = "", notes: str = "") -> None:
        key = make_key(url, title)
        now = datetime.now(timezone.utc).isoformat()
        entry = DedupEntry(
            id=opp_id,
            title=title,
            url=url,
            first_seen=now,
            status=status,
            submitted_at=now if status == "submitted" else "",
            application_type=application_type,
            tier=tier,
            award_value=award_value,
            notes=notes,
        )
        self.entries[key] = entry

    def update_status(self, url: str, title: str, status: str) -> None:
        key = make_key(url, title)
        if key in self.entries:
            self.entries[key].status = status
            if status == "submitted":
                self.entries[key].submitted_at = datetime.now(timezone.utc).isoformat()

    def next_id(self) -> str:
        self._run_counter += 1
        date = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"OPP-{date}-{self._run_counter:03d}"


def load(path: Path | None = None) -> DedupStore:
    path = path or DEDUP_PATH
    if not path.exists():
        return DedupStore()
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    store = DedupStore()
    for key, val in raw.get("entries", {}).items():
        store.entries[key] = DedupEntry(**val)
    return store


def save(store: DedupStore, path: Path | None = None) -> None:
    path = path or DEDUP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "entries": {k: vars(v) for k, v in store.entries.items()},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
