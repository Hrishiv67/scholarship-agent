import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import anthropic

from .searcher import RawOpportunity

_PROGRAMS_DB = Path(__file__).parent.parent / "calendar_agent" / "programs.json"


def _norm_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


_TIER_MAP: list[dict] | None = None


def _load_tier_map() -> list[dict]:
    """Load (domain, name, tier) rows from the program DB, cached."""
    global _TIER_MAP
    if _TIER_MAP is not None:
        return _TIER_MAP
    rows = []
    if _PROGRAMS_DB.exists():
        try:
            for p in json.load(open(_PROGRAMS_DB, encoding="utf-8")):
                name = re.sub(r'\(.*?\)', '', p.get("name", "")).strip().lower()
                rows.append({"domain": _norm_domain(p.get("url", "")),
                             "name": name, "tier": p.get("tier", "")})
        except Exception:
            pass
    _TIER_MAP = rows
    return rows


def _db_tier(url: str, title: str) -> str:
    """Look up a program's DB tier by domain or name match (any source)."""
    domain = _norm_domain(url)
    title_l = (title or "").lower()
    for row in _load_tier_map():
        if not row["tier"]:
            continue
        if domain and row["domain"] and domain == row["domain"]:
            return row["tier"]
        if row["name"] and len(row["name"]) > 6 and (row["name"] in title_l or title_l in row["name"]):
            return row["tier"]
    return ""

# Model used for classification (validated available).
_MODEL = "claude-haiku-4-5-20251001"
_BATCH_SIZE = 3
_MAX_TOKENS = 4096

# Junk that is not itself an application (aggregators / listing pages).
# NOTE: we do NOT filter on eligibility anymore — apply to anything.
JUNK_DOMAINS = [
    "indeed.com", "ziprecruiter.com", "glassdoor.com", "linkedin.com/jobs",
    "reddit.com", "quora.com", "collegevine.com", "niche.com/colleges/scholarships",
]

CAPTCHA_SIGNALS = [
    "recaptcha", "hcaptcha", "cloudflare", "cf-turnstile", "verify you are human",
]


@dataclass
class ClassifiedOpportunity:
    id: str
    title: str
    url: str
    snippet: str
    # Routing
    route: str = "auto_submit"      # yours_manual | auto_submit | track_remind | skip
    application_type: str = "unknown"  # email | web_form | portal_account | fly_in | unknown
    # Money
    costs_money: bool = False       # applicant must pay (fee/tuition/pay-to-attend)
    paid: bool = False              # program pays the applicant (stipend/wage/award)
    # Content
    writing_required: bool = False
    essay_prompts: list = field(default_factory=list)
    is_real_application: bool = True
    deadline: str = ""
    award_value: str = ""
    contact_email: str = ""
    reason: str = ""
    # Provenance
    db_tier: str = ""               # elite | competitive | accessible (from program DB)
    slug: str = ""
    source_query: str = ""

    # Back-compat shims for older callers/tests
    @property
    def tier(self) -> str:
        return self.route

    @property
    def eligible(self) -> bool:
        return self.route != "skip"


def _content_for(opp: RawOpportunity) -> str:
    """Prefer full fetched page text; fall back to the search snippet."""
    text = (opp.raw_content or "").strip()
    if not text or text == "(page loaded but contained no readable text)":
        text = opp.snippet or ""
    return text[:6000]


def _batch_classify(opps: list[RawOpportunity], client: anthropic.Anthropic) -> list[dict]:
    items = ""
    for i, opp in enumerate(opps, 1):
        items += (
            f"\n[{i}] Title: {opp.title}\nURL: {opp.url}\n"
            f"Page content: {_content_for(opp)}\n"
        )

    prompt = f"""You are triaging scholarship, internship, research, apprenticeship, and fly-in opportunities for a high school student who wants to apply broadly. Do NOT judge whether he is eligible or competitive — assume he applies to everything. Your only jobs are (a) detect money direction, (b) detect whether original writing is required, and (c) detect whether this page is a real application vs a listing/aggregator.

Student: Hrishiv Khatiwala, rising 11th grader, Green Hope High School, Cary NC. Strong STEM (rocketry 2nd of 1,001 nationally, VEX top 150 worldwide, Duke + NC State research, published paper, NC Science Olympiad state record).

Today's date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}

For each opportunity return a JSON array. Each entry MUST have exactly these fields:
- "id": the number (integer)
- "application_type": one of "email", "web_form", "portal_account", "fly_in", "unknown"
- "costs_money": true ONLY if the APPLICANT must pay money to apply or participate (application fee, tuition, program cost, pay-to-attend). Otherwise false.
- "paid": true if the program PAYS the applicant (stipend, hourly wage, cash scholarship/award). Otherwise false.
- "writing_required": true if an original essay, personal statement, or short written answer is required.
- "essay_prompts": list of verbatim essay/short-answer prompts found on the page (include any word/character limit in the string), or [].
- "is_real_application": true if this page is (or directly leads to) an actual application. false if it is a job-board/aggregator/listing/blog-roundup/dead page that is not itself an application.
- "deadline": ISO date "YYYY-MM-DD" or "" if unknown.
- "award_value": string like "$2,500", "paid", "all-expenses", stipend amount, or "" if unknown.
- "contact_email": the application or contact email address to send an application to, if one is stated anywhere in the page content. Otherwise "". Only a real email like name@org.edu, never a placeholder.
- "reason": one sentence explaining costs_money / paid / is_real_application.

Rules:
- A paid stipend or wage is NOT "costs_money" — that is money TO the student. Only fees/tuition the student pays are costs_money.
- Generic job boards (Indeed, LinkedIn, ZipRecruiter, Glassdoor) and "top N internships" blog roundups are is_real_application=false.
- Do not skip anything for eligibility. Do not consider age/grade requirements.

Return ONLY a valid JSON array, no other text.

Opportunities:
{items}"""

    message = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) >= 2 else text
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("classifier did not return a JSON array")
    return data


def _derive_route(db_tier: str, costs_money: bool, is_real_application: bool) -> tuple[str, str]:
    """Return (route, reason_suffix)."""
    if db_tier == "elite":
        return "yours_manual", "elite program - reserved for you to apply personally"
    if costs_money:
        return "skip", "costs money (fee/tuition/pay-to-attend) - skipped"
    if not is_real_application:
        return "skip", "not a real application (listing/aggregator/dead page)"
    return "auto_submit", ""


def classify_all(
    raw: list[RawOpportunity],
    dedup_store,
    dry_run: bool = False,
    run_log=None,
) -> list[ClassifiedOpportunity]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[classifier] WARNING: ANTHROPIC_API_KEY not set")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    results: list[ClassifiedOpportunity] = []

    opp_counter = [0]

    def next_id() -> str:
        opp_counter[0] += 1
        from datetime import datetime
        return f"OPP-{datetime.now().strftime('%Y%m%d')}-{opp_counter[0]:03d}"

    # Drop already-seen; no eligibility hard-skip anymore.
    to_classify = [opp for opp in raw if not dedup_store.seen(opp.url, opp.title)]
    print(f"[classifier] {len(to_classify)} to classify ({len(raw) - len(to_classify)} already seen)")

    if dry_run or not to_classify:
        for opp in to_classify:
            tier = opp.tier or _db_tier(opp.url, opp.title)
            route, suffix = _derive_route(tier, False, True)
            results.append(ClassifiedOpportunity(
                id=next_id(), title=opp.title, url=opp.url, snippet=opp.snippet,
                route=route, db_tier=tier, slug=opp.slug,
                reason=(suffix or "DRY_RUN: not classified"),
                source_query=opp.source_query,
            ))
        return results

    for i in range(0, len(to_classify), _BATCH_SIZE):
        batch = to_classify[i:i + _BATCH_SIZE]
        batch_no = i // _BATCH_SIZE + 1
        total_batches = (len(to_classify) - 1) // _BATCH_SIZE + 1
        print(f"[classifier] Batch {batch_no}/{total_batches}...")

        classified: list[dict] = []
        error = ""
        for attempt in (1, 2):
            try:
                classified = _batch_classify(batch, client)
                if len(classified) < len(batch):
                    raise ValueError(f"got {len(classified)} results for {len(batch)} items")
                error = ""
                break
            except Exception as e:
                error = f"{type(e).__name__}: {str(e)[:160]}"
                print(f"[classifier] batch {batch_no} attempt {attempt} failed: {error}")

        for j, opp in enumerate(batch):
            opp_id = next_id()
            tier = opp.tier or _db_tier(opp.url, opp.title)
            match = next((c for c in classified if str(c.get("id", "")) == str(j + 1)), None)

            if match is None:
                # Never silently mass-default to a no-op. Track + remind, record the error.
                if run_log is not None and error:
                    run_log.add_error(opp_id, f"classification_failed: {error}")
                results.append(ClassifiedOpportunity(
                    id=opp_id, title=opp.title, url=opp.url, snippet=opp.snippet,
                    route=("yours_manual" if tier == "elite" else "track_remind"),
                    db_tier=tier, slug=opp.slug,
                    reason=f"classification failed ({error or 'no match'}) - tracking so it is not lost",
                    source_query=opp.source_query,
                ))
                continue

            costs_money = bool(match.get("costs_money", False))
            is_real = bool(match.get("is_real_application", True))
            route, suffix = _derive_route(tier, costs_money, is_real)
            reason = match.get("reason", "")
            if suffix:
                reason = f"{suffix}. {reason}".strip()

            results.append(ClassifiedOpportunity(
                id=opp_id, title=opp.title, url=opp.url, snippet=opp.snippet,
                route=route,
                application_type=match.get("application_type", "unknown"),
                costs_money=costs_money,
                paid=bool(match.get("paid", False)),
                writing_required=bool(match.get("writing_required", False)),
                essay_prompts=match.get("essay_prompts", []) or [],
                is_real_application=is_real,
                deadline=match.get("deadline", ""),
                award_value=match.get("award_value", ""),
                contact_email=(match.get("contact_email", "") or "").strip(),
                reason=reason,
                db_tier=tier, slug=opp.slug,
                source_query=opp.source_query,
            ))

    # Rank: paid first, then everything else (stable within groups).
    results.sort(key=lambda r: (not r.paid, r.route == "skip"))

    counts: dict[str, int] = {}
    for r in results:
        counts[r.route] = counts.get(r.route, 0) + 1
    print(f"[classifier] Routes: {counts}")
    return results
