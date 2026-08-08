import json
import os
from dataclasses import dataclass

import anthropic

from .searcher import RawOpportunity

SKIP_SIGNALS = [
    "must be enrolled in college", "undergraduate student", "graduate student",
    "bachelor", "master", "phd", "doctoral", "degree required",
    "must be 18", "age 18", "age 21", "18 years of age",
    "teacher recommendation", "letter of recommendation required",
    "official transcript", "transcript required",
    "financial need required", "income verification",
]

ESSAY_SIGNALS = [
    "personal statement", "500 words", "250 words", "essay required",
    "write a ", "describe your", "explain why", "tell us why",
    "why do you want", "what motivates you", "500-word", "250-word",
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
    tier: str           # auto_apply | semi_apply | essay_pending | skip
    application_type: str  # email | web_form | portal_account | unknown
    deadline: str
    award_value: str
    eligible: bool
    essay_prompts: list[str]
    reason: str
    source_query: str


def _hard_skip(text: str) -> str | None:
    lower = text.lower()
    for sig in SKIP_SIGNALS:
        if sig in lower:
            return f"Contains skip signal: '{sig}'"
    return None


def _batch_classify(opps: list[RawOpportunity], client: anthropic.Anthropic) -> list[dict]:
    items = ""
    for i, opp in enumerate(opps, 1):
        items += f"\n[{i}] Title: {opp.title}\nURL: {opp.url}\nSnippet: {opp.snippet[:400]}\n"

    prompt = f"""You are classifying scholarship, internship, research, and fly-in program opportunities for a high school student.

Student profile:
- Rising 11th grade at Green Hope High School, Cary NC
- GPA 4.696W / 3.96UW, SAT 1430, Class Rank 7/652
- Strong STEM: rocketry 2nd nationally (1,001 teams), VEX robotics top 150 worldwide, NC State + Duke research, Science Olympiad NC State record holder
- Published paper on Zenodo, dual enrollment Wake Tech (4.0 GPA)
- Community: Books for Africa (10,000+ books, $85,000+ shipped), 350+ volunteer hours
- Skills: Python, MATLAB, 3D printing, AI/ML modeling, aerodynamics
- Looking for: paid internships, research programs, no-essay scholarships, fly-in programs

Today's date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}

For each opportunity below, return a JSON array. Each entry MUST have exactly these fields:
- "id": the number (integer)
- "tier": one of "auto_apply", "semi_apply", "essay_pending", "skip"
- "application_type": one of "email", "web_form", "portal_account", "fly_in", "unknown"
- "deadline": ISO date string like "2027-03-15" or "" if unknown
- "award_value": string like "$2,500" or "paid" or "all-expenses" or "" if unknown
- "eligible": true or false
- "essay_prompts": list of essay prompt strings found, or []
- "reason": one sentence explaining your tier decision

Tier rules:
- "skip": requires college enrollment, degree, age 18+, teacher rec, transcript upload, or deadline clearly passed
- "essay_pending": requires any original essay or personal statement over 100 words
- "semi_apply": web form requiring account creation, has CAPTCHA/Cloudflare, or multi-step portal
- "auto_apply": email-based application, simple short web form, or fly-in with minimal requirements

Return ONLY valid JSON array, no other text.

Opportunities:
{items}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"[classifier] Claude call failed: {e}")
        return []


def classify_all(
    raw: list[RawOpportunity],
    dedup_store,
    dry_run: bool = False,
) -> list[ClassifiedOpportunity]:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[classifier] WARNING: ANTHROPIC_API_KEY not set")
        return []

    client = anthropic.Anthropic(api_key=api_key)
    results: list[ClassifiedOpportunity] = []

    # First pass: hard-rule skips (no API call needed)
    to_classify: list[tuple[int, RawOpportunity]] = []
    opp_counter = [0]

    def next_id():
        opp_counter[0] += 1
        from datetime import datetime
        date = datetime.now().strftime("%Y%m%d")
        return f"OPP-{date}-{opp_counter[0]:03d}"

    for opp in raw:
        # Skip already-seen
        if dedup_store.seen(opp.url, opp.title):
            continue

        skip_reason = _hard_skip(opp.snippet + " " + opp.title)
        if skip_reason:
            results.append(ClassifiedOpportunity(
                id=next_id(), title=opp.title, url=opp.url,
                snippet=opp.snippet, tier="skip",
                application_type="unknown", deadline="",
                award_value="", eligible=False, essay_prompts=[],
                reason=skip_reason, source_query=opp.source_query,
            ))
            continue
        to_classify.append((opp_counter[0] + 1, opp))

    print(f"[classifier] {len(to_classify)} opportunities to classify via Claude (after {len(raw)-len(to_classify)} hard skips/dedup)")

    if dry_run or not to_classify:
        # In dry run, mark everything as semi_apply for review
        for _, opp in to_classify:
            results.append(ClassifiedOpportunity(
                id=next_id(), title=opp.title, url=opp.url,
                snippet=opp.snippet, tier="semi_apply",
                application_type="unknown", deadline="",
                award_value="", eligible=True, essay_prompts=[],
                reason="DRY_RUN: not classified", source_query=opp.source_query,
            ))
        return results

    # Batch Claude calls (5 at a time to save tokens)
    batch_size = 5
    opps_only = [opp for _, opp in to_classify]
    for i in range(0, len(opps_only), batch_size):
        batch = opps_only[i:i + batch_size]
        print(f"[classifier] Classifying batch {i//batch_size + 1}/{(len(opps_only)-1)//batch_size + 1}...")
        classified = _batch_classify(batch, client)

        for j, opp in enumerate(batch):
            opp_id = next_id()
            match = next((c for c in classified if c.get("id") == j + 1), None)
            if not match:
                # Fallback: can't classify → semi_apply
                results.append(ClassifiedOpportunity(
                    id=opp_id, title=opp.title, url=opp.url,
                    snippet=opp.snippet, tier="semi_apply",
                    application_type="unknown", deadline="",
                    award_value="", eligible=True, essay_prompts=[],
                    reason="Classification failed — defaulted to semi_apply",
                    source_query=opp.source_query,
                ))
                continue

            results.append(ClassifiedOpportunity(
                id=opp_id,
                title=opp.title,
                url=opp.url,
                snippet=opp.snippet,
                tier=match.get("tier", "semi_apply"),
                application_type=match.get("application_type", "unknown"),
                deadline=match.get("deadline", ""),
                award_value=match.get("award_value", ""),
                eligible=match.get("eligible", True),
                essay_prompts=match.get("essay_prompts", []),
                reason=match.get("reason", ""),
                source_query=opp.source_query,
            ))

    # Count by tier
    counts = {}
    for r in results:
        counts[r.tier] = counts.get(r.tier, 0) + 1
    print(f"[classifier] Classification complete: {counts}")
    return results
