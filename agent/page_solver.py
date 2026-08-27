"""
Watch the live application page and keep unblocking it until submit confirms.

Heuristic first (empty required fields, validation errors, Yes/No, disabled submit).
If that stalls, ask Claude what a person would do next — then do that one action
and look again. Never claims success without a confirmation page.
"""
from __future__ import annotations

import json
import os
import re

import anthropic

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import captcha

_MODEL = "claude-haiku-4-5-20251001"
_MAX_STEPS = 14

_SNAP_JS = """() => {
  const vis = (el) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 1 && r.height > 1;
  };
  const labelFor = (el) => {
    const id = el.id;
    if (id) {
      const lab = document.querySelector('label[for="' + id.replace(/"/g, '') + '"]');
      if (lab) return (lab.innerText || '').trim();
    }
    const wrap = el.closest('label');
    if (wrap) return (wrap.innerText || '').trim().slice(0, 80);
    return (el.getAttribute('aria-label') || '').trim();
  };
  const fields = [...document.querySelectorAll('input, textarea, select')]
    .filter(el => vis(el) && !['hidden','submit','button','image'].includes((el.type || '').toLowerCase()))
    .slice(0, 40)
    .map(el => {
      const type = (el.type || el.tagName.toLowerCase()).toLowerCase();
      const val = (el.value || '').trim();
      return {
        tag: el.tagName.toLowerCase(),
        type,
        name: el.name || '',
        id: el.id || '',
        placeholder: el.placeholder || '',
        label: labelFor(el).slice(0, 80),
        value: val.slice(0, 80),
        empty: type === 'checkbox' || type === 'radio' ? !el.checked : !val,
        required: el.required || (el.getAttribute('aria-required') === 'true') || (labelFor(el).includes('*')),
        invalid: el.getAttribute('aria-invalid') === 'true' || (el.className || '').toLowerCase().includes('error'),
      };
    });
  const errors = [...document.querySelectorAll('[class*="error"], [class*="invalid"], [aria-invalid="true"], [role="alert"]')]
    .filter(vis)
    .map(el => (el.innerText || '').trim())
    .filter(t => t && t.length < 180)
    .slice(0, 8);
  const buttons = [...document.querySelectorAll('button, a, [role="button"], [role="radio"], input[type="submit"], label')]
    .filter(vis)
    .map(el => ({
      text: (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 60),
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
    }))
    .filter(b => b.text && b.text.length < 50)
    .slice(0, 30);
  const submit = buttons.find(b => /submit/i.test(b.text));
  const heading = ((document.querySelector('h1,h2') || {}).innerText || '').trim().slice(0, 120);
  const body = (document.body.innerText || '').slice(0, 1600);
  return {url: location.href, heading, errors, fields, buttons, submitEnabled: !!(submit && !submit.disabled), body};
}"""


def profile_facts(profile: Profile) -> dict[str, str]:
    p, a = profile.personal, profile.academic
    g = next((x for x in profile.guardians if x.primary), profile.guardians[0]) if profile.guardians else None
    return {
        "first_name": p.first_name,
        "last_name": p.last_name,
        "email": p.email,
        "phone": p.phone_formatted,
        "address": f"{p.address.line1}, {p.address.city}, {p.address.state} {p.address.zip}",
        "line1": p.address.line1,
        "city": p.address.city,
        "state": p.address.state,
        "zip": p.address.zip,
        "school": a.current_school,
        "grad_year": str(a.graduation_year),
        "grade": str(a.current_grade),
        "gender": p.gender,
        "college": "North Carolina State University",
        "study_level": "High School Junior",
        "hs_start_year": str(int(a.graduation_year) - 4),
        "citizenship": p.citizenship.split("/")[0].strip() if p.citizenship else "US Citizen",
        "ethnicity": p.ethnicity,
        "guardian_email": g.email if g else "",
        "guardian_name": g.full_name if g else "",
    }


def snapshot(page) -> dict:
    try:
        data = page.evaluate(_SNAP_JS)
    except Exception:
        data = {}
    data.setdefault("fields", [])
    data.setdefault("errors", [])
    data.setdefault("buttons", [])
    data.setdefault("body", "")
    data.setdefault("heading", "")
    data.setdefault("submitEnabled", False)
    data["url"] = getattr(page, "url", data.get("url", ""))
    return data


def _value_for_field(label_blob: str, facts: dict[str, str], profile: Profile) -> str | None:
    from . import form_filler as ff
    key = ff._match_field(label_blob)
    if key:
        val = ff._get_field_value(key, profile)
        return val or None
    blob = (label_blob or "").lower()
    if "first" in blob and "name" in blob:
        return facts["first_name"]
    if "last" in blob and "name" in blob:
        return facts["last_name"]
    if "email" in blob and "parent" not in blob and "guardian" not in blob:
        return facts["email"]
    if "parent" in blob and "email" in blob:
        return facts["guardian_email"]
    if "phone" in blob or "mobile" in blob:
        return facts["phone"]
    if "address" in blob or "location" in blob:
        return facts["address"]
    if "college" in blob or "university" in blob:
        return facts["college"]
    if "school" in blob:
        return facts["school"]
    if "grad" in blob and "year" in blob:
        return facts["grad_year"]
    if "start" in blob and "year" in blob:
        return facts["hs_start_year"]
    if "level of study" in blob or "upcoming" in blob:
        return facts["study_level"]
    return None


def decide_heuristic(snap: dict, facts: dict[str, str], profile: Profile, skip: set | None = None) -> dict | None:
    skip = {s.lower() for s in (skip or set())}
    body = (snap.get("body") or "").lower()
    errors = " ".join(snap.get("errors") or []).lower()
    heading = (snap.get("heading") or "").lower()

    if "applied for scholarships before" in body:
        if any((b.get("text") or "").strip().lower() == "no" for b in snap.get("buttons") or []):
            return {"action": "CLICK", "target": "No", "why": "onboarding: first-time applicant"}
    if "student or a parent" in body or "student or parent" in body:
        has_name = any(
            "first" in (f.get("label") or "").lower() and "name" in (f.get("label") or "").lower()
            for f in snap["fields"]
        )
        student_checked = any(
            f.get("type") == "radio" and "student" in (f.get("label") or "").lower() and not f.get("empty")
            for f in snap["fields"]
        )
        if not student_checked and not has_name:
            return {"action": "CLICK", "target": "Student", "why": "select student"}

    dob_empty = any(
        "birth" in " ".join([f.get("label") or "", f.get("name") or "", f.get("placeholder") or ""]).lower()
        and f.get("empty")
        for f in snap["fields"]
    )
    if dob_empty and not (profile.personal.date_of_birth or "").strip():
        if "press & hold" not in body and "not a bot" not in body:
            return {"action": "GIVE_UP", "why": "date of birth required and not in profile"}

    for f in sorted(snap["fields"], key=lambda x: 0 if x.get("tag") == "select" else 1):
        blob = " ".join([f.get("label") or "", f.get("name") or "", f.get("placeholder") or ""])
        if f.get("type") in ("checkbox", "radio"):
            continue
        if "referral" in blob.lower() or "double your chances" in blob.lower():
            continue
        if blob.lower()[:80] in skip or (f.get("name") or "").lower() in skip:
            continue
        needs = f.get("empty") or f.get("invalid") or f.get("required") and f.get("empty")
        if not needs:
            # select still on placeholder
            val = (f.get("value") or "").lower()
            if f.get("tag") == "select" and (not val or "select" in val or "please" in val):
                needs = True
        if not needs:
            continue
        value = _value_for_field(blob, facts, profile)
        if not value:
            continue
        low = blob.lower()
        is_addr = (
            "email" not in low
            and ("street" in low or "location" in low or "permanent address" in low or "address" in low)
        ) or "street" in errors or "full street" in errors
        extra = {"name": f.get("name") or "", "id": f.get("id") or ""}
        if is_addr:
            return {"action": "ADDRESS", "target": blob, "value": facts["address"], "why": "fix address / places widget", **extra}
        if f.get("tag") == "select":
            return {"action": "SELECT", "target": blob, "value": value, "why": f"select {blob[:40]}", **extra}
        return {"action": "FILL", "target": blob, "value": value, "why": f"fill empty {blob[:40]}", **extra}

    if "street" in errors or "full street" in errors or ("address" in errors and "email" not in errors):
        if "address" not in skip:
            return {"action": "ADDRESS", "target": "address", "value": facts["address"], "why": "validation error on address"}

    eth = (facts.get("ethnicity") or "").lower()
    if eth:
        for b in snap.get("buttons") or []:
            t = (b.get("text") or "").lower()
            if b.get("disabled"):
                continue
            if "asian" in eth and "asian" in t:
                return {"action": "CLICK", "target": b["text"], "why": "select ethnicity from profile"}

    if "start studying" in body or "when did you start" in body:
        year = facts.get("hs_start_year") or ""
        if year:
            return {"action": "CLICK", "target": year, "why": "high school start year"}

    for b in snap.get("buttons") or []:
        t = (b.get("text") or "").strip()
        if b.get("disabled"):
            continue
        if t == facts.get("grad_year"):
            return {"action": "CLICK", "target": t, "why": "pick graduation year"}
        if t == facts.get("hs_start_year"):
            return {"action": "CLICK", "target": t, "why": "pick start year"}

    school_empty = any(
        "school" in " ".join([f.get("label") or "", f.get("placeholder") or ""]).lower()
        and "college" not in (f.get("label") or "").lower()
        and f.get("empty")
        for f in snap["fields"]
    )

    for b in snap.get("buttons") or []:
        t = (b.get("text") or "").strip().lower()
        if b.get("disabled"):
            continue
        if t in ("high school", "high school student", "high school junior"):
            if any(w in body for w in ("education", "grade", "school", "student type", "i am a")):
                return {"action": "CLICK", "target": b["text"], "why": "pick high school education level"}
        if t in ("quick apply", "get started", "join bold.org", "join bold", "apply now", "start applying"):
            return {"action": "CLICK", "target": b["text"], "why": "enter apply / signup"}

    for b in snap.get("buttons") or []:
        t = (b.get("text") or "").lower()
        if b.get("disabled"):
            continue
        if t in ("next", "continue", "save and continue", "save & continue"):
            if school_empty:
                continue
            return {"action": "CLICK", "target": b["text"], "why": "advance wizard"}

    empties = [
        f for f in snap["fields"]
        if f.get("empty") and f.get("type") not in ("checkbox", "radio", "hidden")
    ]
    if snap.get("submitEnabled"):
        if empties:
            return None
        return {"action": "SUBMIT", "why": "submit is enabled"}

    submit_btns = [b for b in snap.get("buttons") or [] if "submit" in (b.get("text") or "").lower()]
    if submit_btns and submit_btns[0].get("disabled") and not empties:
        return {"action": "SUBMIT", "why": "no empty fields left, try submit anyway"}
    return None


def decide_ai(snap: dict, facts: dict[str, str], opp: ClassifiedOpportunity) -> dict | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    compact = {
        "url": snap.get("url"),
        "heading": snap.get("heading"),
        "errors": snap.get("errors"),
        "submitEnabled": snap.get("submitEnabled"),
        "fields": [
            {k: f.get(k) for k in ("label", "name", "type", "tag", "empty", "required", "invalid", "value", "placeholder")}
            for f in (snap.get("fields") or [])[:25]
        ],
        "buttons": snap.get("buttons"),
        "body": (snap.get("body") or "")[:900],
    }
    prompt = f"""You are filling a scholarship/internship application for {facts['first_name']} {facts['last_name']}.
Do the next SINGLE action a careful human would do. Do not invent a birthday or any fact not listed.

Applicant facts (use these values only):
{json.dumps(facts, indent=2)}

Program: {opp.title}
Page snapshot:
{json.dumps(compact)[:5000]}

Return ONLY JSON with:
{{"action":"FILL"|"SELECT"|"CLICK"|"ADDRESS"|"SUBMIT"|"WAIT"|"GIVE_UP","target":"<label or button text>","value":"<text to type if FILL/SELECT/ADDRESS>","why":"<short>"}}

Rules:
- FILL empty first name, last name, email, phone, school, college with the facts above.
- ADDRESS when the field is a location/places autocomplete — use the full street address fact.
- SELECT graduation year {facts['grad_year']}, grade 11 / High School Junior, state NC, gender Male.
- Ethnicity is {facts.get('ethnicity') or 'not listed'}. For religion/income/first-generation if not listed, click "Prefer not to say" — never invent.
- If a dropdown is not a native select, CLICK the visible option text (e.g. "High School" / "High School Junior") instead of SELECT.
- Password fields: leave value as "<portal_password>" and the agent will type the saved portal password. Do not invent a password.
- CLICK "Student" not Parent. CLICK "No" if asked whether they have applied for scholarships before. CLICK Quick Apply / Get Started / Join / Next when that unblocks the form.
- Do NOT fill referral / "double your chances" / optional parent email fields.
- SUBMIT only when required fields look filled. After submit, a HubSpot form may show "Thanks for submitting".
- GIVE_UP only if this is clearly not an application (article, 404, login-with-Google-only), or a Cloudflare human-check that did not pass.
"""
    try:
        msg = anthropic.Anthropic(api_key=api_key).messages.create(
            model=_MODEL, max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        if data.get("action") in ("FILL", "SELECT", "CLICK", "ADDRESS", "SUBMIT", "WAIT", "GIVE_UP"):
            return data
    except Exception as e:
        print(f"[page_solver] AI decide failed: {type(e).__name__}: {str(e)[:120]}")
    return None


def _fill_by_target(page, target: str, value: str, name: str = "", fid: str = "") -> bool:
    if not value:
        return False
    if name:
        try:
            loc = page.locator(f'input[name="{name}"], textarea[name="{name}"], select[name="{name}"]')
            if loc.count() > 0:
                loc.first.fill(value, timeout=2500)
                return True
        except Exception:
            pass
    if fid:
        try:
            loc = page.locator(f"#{fid}")
            if loc.count() > 0:
                loc.first.fill(value, timeout=2500)
                return True
        except Exception:
            pass
    if not target:
        return False
    label = target.strip()[:80]
    tries = [
        lambda: page.get_by_label(re.compile(re.escape(label[:30]), re.I)).first.fill(value, timeout=2500),
        lambda: page.get_by_placeholder(re.compile(re.escape(label[:30]), re.I)).first.fill(value, timeout=2500),
        lambda: page.locator(f'input[name="{label}"], textarea[name="{label}"], select[name="{label}"]').first.fill(value, timeout=2500),
        lambda: page.get_by_role("textbox", name=re.compile(label[:20], re.I)).first.fill(value, timeout=2500),
    ]
    # Prefer first/last/email shortcuts when the target mentions them
    low = label.lower()
    if "first" in low and "name" in low:
        tries.insert(0, lambda: page.get_by_label(re.compile(r"first name", re.I)).first.fill(value, timeout=2500))
    if "last" in low and "name" in low:
        tries.insert(0, lambda: page.get_by_label(re.compile(r"last name", re.I)).first.fill(value, timeout=2500))
    if "email" in low and "parent" not in low:
        tries.insert(0, lambda: page.locator('input[type="email"]').first.fill(value, timeout=2500))
    if "phone" in low:
        tries.insert(0, lambda: page.locator('input[type="tel"]').first.fill(value, timeout=2500))
    for fn in tries:
        try:
            fn()
            return True
        except Exception:
            continue
    return False


def _frames(page):
    try:
        return list(page.frames)
    except Exception:
        return [page]


def _select_by_target(page, target: str, value: str, name: str = "") -> bool:
    if not value:
        return False
    names = [n for n in (name, "member_hs_grad_year", "member_upcoming_level_of_study") if n]
    if value.isdigit():
        names = ["member_hs_grad_year"] + [n for n in names if n != "member_hs_grad_year"]
    elif "junior" in value.lower() or "level" in (target or "").lower():
        names = ["member_upcoming_level_of_study"] + [n for n in names if n != "member_upcoming_level_of_study"]
    candidates = [value]
    if "high school" in value.lower() and "junior" not in value.lower():
        candidates.append("High School Junior")
    for frame in _frames(page):
        for nm in names:
            loc = frame.locator(f'select[name="{nm}"]')
            try:
                if loc.count() == 0:
                    continue
            except Exception:
                continue
            for cand in candidates:
                try:
                    loc.select_option(label=cand, timeout=2500)
                    return True
                except Exception:
                    pass
                try:
                    loc.select_option(value=cand, timeout=2500)
                    return True
                except Exception:
                    pass
    # Custom widgets (Bold.org and similar): click the option text.
    for frame in _frames(page):
        for cand in candidates:
            for role in ("option", "menuitem", "radio"):
                try:
                    loc = frame.get_by_role(role, name=re.compile(rf"^{re.escape(cand)}$", re.I))
                    if loc.count() > 0:
                        loc.first.click(timeout=2500, force=True)
                        return True
                except Exception:
                    continue
            try:
                loc = frame.get_by_text(cand, exact=True)
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click(timeout=2500, force=True)
                    return True
            except Exception:
                continue
    return False


def _pick_suggestion(page, needle: str) -> bool:
    """Click an autocomplete row (school search, Google Places, etc.)."""
    if not needle:
        return False
    snippet = needle.strip()[:18]
    page.wait_for_timeout(700)
    for frame in _frames(page):
        try:
            loc = frame.get_by_role("option").filter(has_text=re.compile(re.escape(snippet.split()[0]), re.I))
            if loc.count() > 0:
                loc.first.click(force=True, timeout=2500)
                return True
        except Exception:
            pass
        for sel in (".pac-item", '[role="option"]', '[role="listbox"] li', "[class*='suggestion']"):
            try:
                items = frame.locator(sel)
                n = min(items.count(), 8)
                for i in range(n):
                    txt = (items.nth(i).inner_text() or "").lower()
                    if snippet.lower().split()[0] in txt:
                        items.nth(i).click(force=True, timeout=2000)
                        return True
            except Exception:
                continue
    try:
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(150)
        page.keyboard.press("Enter")
        return True
    except Exception:
        return False


def _click_target(page, target: str) -> bool:
    if not target:
        return False
    rx = re.compile(rf"^{re.escape(target.strip())}$", re.I)
    for role in ("button", "link", "radio", "option", "menuitem", "tab"):
        try:
            loc = page.get_by_role(role, name=rx)
            if loc.count() > 0:
                loc.first.click(timeout=4000, force=True)
                return True
        except Exception:
            continue
    try:
        loc = page.get_by_text(target.strip(), exact=True)
        if loc.count() > 0:
            loc.first.click(timeout=4000, force=True)
            return True
    except Exception:
        pass
    try:
        loc = page.get_by_text(re.compile(rf"^{re.escape(target.strip())}$", re.I))
        if loc.count() > 0:
            loc.first.click(timeout=4000, force=True)
            return True
    except Exception:
        pass
    return False


def _fill_address(page, address: str) -> bool:
    street = address.split(",")[0].strip() if address else address
    typed = f"{street}, Cary, NC"
    box = None
    for frame in _frames(page):
        for getter in (
            lambda fr=frame: fr.locator("input.pac-target-input"),
            lambda fr=frame: fr.locator('input[name="full_address"]'),
            lambda fr=frame: fr.get_by_placeholder(re.compile(r"location|address|street", re.I)),
        ):
            try:
                loc = getter()
                if loc.count() == 0:
                    continue
                box = loc.first
                box.click()
                box.press("Control+A")
                box.press("Backspace")
                box.type(typed, delay=70)
                break
            except Exception:
                continue
        if box is not None:
            break
    try:
        page.wait_for_selector(".pac-item", timeout=4000)
        page.evaluate("""() => {
          const item = document.querySelector('.pac-item');
          if (item) item.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
        }""")
        page.wait_for_timeout(400)
    except Exception:
        if box is not None:
            try:
                box.press("ArrowDown")
                page.wait_for_timeout(200)
                box.press("Enter")
            except Exception:
                pass
    # HubSpot stores the validated street in hidden inputs; Places may never
    # open in automation, so set those fields directly.
    set_ok = False
    for frame in _frames(page):
        try:
            set_ok = frame.evaluate(
                """({line1, city, state, zip}) => {
                  const set = (name, val) => {
                    const el = document.querySelector('input[name="' + name + '"]');
                    if (!el) return false;
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles:true}));
                    el.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                  };
                  let n = 0;
                  if (set('address', line1)) n++;
                  if (set('city', city)) n++;
                  if (set('state', state)) n++;
                  if (set('zip', zip)) n++;
                  if (set('state_of_residence', state)) n++;
                  return n > 0;
                }""",
                {"line1": street, "city": "Cary", "state": "NC", "zip": "27519"},
            )
            if set_ok:
                break
        except Exception:
            continue
    return bool(box is not None or set_ok)


def execute(page, action: dict, facts: dict[str, str]) -> bool:
    kind = (action.get("action") or "").upper()
    target = action.get("target") or ""
    value = action.get("value") or ""
    if kind == "WAIT":
        page.wait_for_timeout(1500)
        return True
    if kind == "FILL":
        if "password" in target.lower():
            value = os.environ.get("PORTAL_PASSWORD", "") or value
        val = value or facts.get("email", "")
        ok = _fill_by_target(page, target, val, action.get("name") or "", action.get("id") or "")
        low = target.lower()
        if ok and val and ("school" in low or ("address" in low and "email" not in low) or "location" in low):
            _pick_suggestion(page, val.split(",")[0])
        return ok
    if kind == "SELECT":
        ok = _select_by_target(page, target, value, action.get("name") or "")
        if not ok and value:
            ok = _click_target(page, value) or _pick_suggestion(page, value)
        return ok
    if kind == "CLICK":
        ok = _click_target(page, target)
        if ok and target.strip().lower() in ("student", "no", "yes", "parent"):
            page.wait_for_timeout(1500)
        return ok
    if kind == "ADDRESS":
        return _fill_address(page, value or facts["address"])
    if kind == "SUBMIT":
        from . import form_filler as ff
        captcha.solve_if_present(page)
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass
        return ff._click_submit(page)
    return False


def run(page, profile: Profile, opp: ClassifiedOpportunity) -> tuple[bool, str, int]:
    """
    Loop: snapshot → decide → act, until confirmation or give up.
    Returns (confirmed, reason, steps_taken).
    """
    from . import form_filler as ff
    facts = profile_facts(profile)
    last_why = "no action"
    repeats: dict[tuple, int] = {}
    skip: set[str] = set()
    submit_count = 0
    for step in range(1, _MAX_STEPS + 1):
        captcha.solve_if_present(page)
        success, conf = ff._detect_success(page, "")
        # _detect_success with empty pre_url treats any url as unchanged; check body only
        snap = snapshot(page)
        body = (snap.get("body") or "").lower()
        fake = any(p in body for p in ("press & hold", "not a bot", "confirm you are a human"))
        if not fake:
            if any(p in body for p in ff.STRONG_SUCCESS) or ff._extract_confirmation(snap.get("body") or ""):
                print(f"[page_solver] step {step}: confirmation on page")
                return True, conf or "thank-you page", step
            if re.search(r"thanks for (applying|your (application|entry|submission))", body):
                return True, "thank-you page", step

        action = decide_heuristic(snap, facts, profile, skip)
        source = "heuristic"
        if action is None:
            action = decide_ai(snap, facts, opp)
            source = "ai"
        if action is None:
            last_why = "no next action found"
            print(f"[page_solver] step {step}: stuck — {last_why}")
            break
        if action.get("action") == "GIVE_UP":
            last_why = action.get("why") or "gave up"
            print(f"[page_solver] step {step}: GIVE_UP ({last_why})")
            break

        last_why = action.get("why") or action.get("action") or ""
        sig = (action.get("action"), action.get("target"), action.get("value"))
        repeats[sig] = repeats.get(sig, 0) + 1
        if repeats[sig] >= 3 and (action.get("action") or "").upper() != "SUBMIT":
            if (action.get("action") or "").upper() == "SELECT":
                click_target = action.get("value") or action.get("target") or ""
                action = {"action": "CLICK", "target": click_target, "why": "click option after select failed"}
                source = "fallback"
            else:
                key = (action.get("name") or action.get("target") or "")[:80]
                skip.add(key.lower())
                print(f"[page_solver] step {step}: skipping repeated {sig[0]} {str(sig[1])[:50]}")
                continue
        print(f"[page_solver] step {step} [{source}] {action.get('action')} {action.get('target') or ''} — {last_why}")
        try:
            ok = execute(page, action, facts)
        except Exception as e:
            msg = str(e)
            print(f"[page_solver] step {step}: page error {type(e).__name__}: {msg[:160]}")
            if "closed" in msg.lower() and (action.get("action") or "").upper() == "SUBMIT":
                return False, "browser closed after submit (check email / confirmation)", step
            last_why = msg[:160]
            break
        if not ok:
            print(f"[page_solver] step {step}: action failed, asking again")
        try:
            page.wait_for_timeout(1200)
        except Exception as e:
            if "closed" in str(e).lower():
                if (action.get("action") or "").upper() == "SUBMIT":
                    return False, "browser closed after submit (check email / confirmation)", step
                break
        if (action.get("action") or "").upper() == "SUBMIT":
            submit_count += 1
            try:
                page.wait_for_timeout(4000)
                captcha.solve_if_present(page)
                body2 = (page.inner_text("body") or "").lower()
            except Exception as e:
                if "closed" in str(e).lower():
                    return False, "browser closed after submit (check email / confirmation)", step
                body2 = ""
            if any(p in body2 for p in ff.STRONG_SUCCESS) or "thank you" in body2 or "thanks for submitting" in body2:
                return True, "thank-you after submit", step
            if submit_count >= 2:
                last_why = "submit clicked but no confirmation page"
                print(f"[page_solver] step {step}: stopping extra submits")
                break

    return False, last_why, _MAX_STEPS
