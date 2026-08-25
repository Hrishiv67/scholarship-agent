"""
AI-driven navigation: given a program page that is not itself an application form,
reason about which link leads to the actual application and go there - the way a
person would, instead of giving up because the landing page is a homepage.
"""
import json
import os

import anthropic

_MODEL = "claude-haiku-4-5-20251001"


def choose_next(title: str, current_url: str, links: list[dict], page_excerpt: str) -> dict:
    """
    Decide the single best next step toward this program's application.
    links: [{"i": int, "text": str, "href": str}, ...]
    Returns {"action": "THIS_PAGE" | "GO" | "NONE", "index": int|None, "why": str}.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not links:
        return {"action": "THIS_PAGE", "index": None, "why": "no api key or no links"}

    listed = "\n".join(f'[{l["i"]}] {l["text"][:80]}  ->  {l["href"]}' for l in links[:40])
    prompt = f"""You are helping a high school student reach the ACTUAL application for this program, navigating like a person would.

Program: {title}
Current page URL: {current_url}

Page text (excerpt):
{page_excerpt[:1800]}

Links on the page (index, text, href):
{listed}

Decide the single best next step to reach the real application form or portal.
- If the actual application form (fields to fill) is already ON this page, return THIS_PAGE.
- If a link clearly leads toward applying (for example "Apply", "Application", "Apply Now", "Start your application", a portal login, an application on a subpage), return GO with that link's index.
- Prefer the most direct route to applying for high school students. Avoid news, donate, about, contact, and social links.
- If nothing on this page leads toward an application, return NONE.

Return ONLY JSON: {{"action": "THIS_PAGE" | "GO" | "NONE", "index": <int or null>, "why": "<short reason>"}}"""

    try:
        msg = anthropic.Anthropic(api_key=api_key).messages.create(
            model=_MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        if data.get("action") not in ("THIS_PAGE", "GO", "NONE"):
            return {"action": "THIS_PAGE", "index": None, "why": "bad response"}
        return data
    except Exception as e:
        print(f"[navigator] decision failed: {type(e).__name__}: {str(e)[:100]}")
        return {"action": "THIS_PAGE", "index": None, "why": "error"}
