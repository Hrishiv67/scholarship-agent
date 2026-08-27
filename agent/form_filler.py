import re
from dataclasses import dataclass
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import account_creator, captcha, session_store, writer

SCREENSHOTS_DIR = Path(__file__).parent.parent / "outputs" / "screenshots"
CONFIRM_DIR = Path(__file__).parent.parent / "outputs" / "confirmations"
RESUME_PATH = Path(__file__).parent.parent / "profile" / "resume.pdf"
DOCUMENTS_DIR = Path(__file__).parent.parent / "profile" / "documents"

SUCCESS_KEYWORDS = [
    "thank you", "thanks for", "submitted", "received", "application complete",
    "successfully", "confirmation", "we have received", "you have applied",
    "you're in", "you are in", "entry received", "application received",
]

STRONG_SUCCESS = [
    "application has been submitted", "application was submitted",
    "your application has been received", "we have received your application",
    "thank you for applying", "thank you for your application",
    "application successfully submitted", "your application has been submitted",
    "application complete", "confirmation number", "reference number",
    "you have successfully applied", "your submission has been received",
    "thanks for submitting", "thanks for submitting the form",
    "your form has been submitted", "submitted the form",
]
_CONF_NUM = re.compile(
    r'(confirmation|reference|application)\s*(number|no\.?|id|#)\s*[:#]?\s*([A-Za-z0-9-]{5,})',
    re.I,
)
_FAKE_CONFIRM = (
    "press & hold", "not a bot", "confirm you are a human",
    "cf-challenge", "just a moment", "attention required",
)

APPLY_CLICK_PATTERNS = [
    r"start (your )?application",
    r"begin application",
    r"apply now",
    r"apply online",
    r"apply here",
    r"quick apply",
    r"get started",
    r"join bold",
    r"submit application",
    r"create (an )?account",
    r"sign ?up",
    r"^apply$",
    r"apply for",
    r"start applying",
    r"continue application",
]

NEXT_PATTERNS = [
    r"^next$", r"^continue$", r"save and continue", r"save & continue",
    r"^proceed$", r"next step", r"continue application",
]

SUBMIT_PATTERNS = [
    r"submit my application", r"submit application", r"submit my application",
    r"finish application", r"^submit$", r"^send$", r"apply now",
    r"complete application", r"quick apply",
]

_LINK_SKIP = (
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "youtube.com", "/donate", "/news", "/about", "/contact", "/privacy",
    "mailto:", "tel:",
)

_LINKS_JS = """() => {
  const out = []; const seen = new Set();
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.href;
    const text = (a.innerText || a.textContent || '').trim();
    if (!href || !href.startsWith('http')) return;
    if (seen.has(href)) return; seen.add(href);
    out.push({text, href});
  });
  return out.slice(0, 80);
}"""


def _resolve_document(label: str) -> Path | None:
    text = (label or "").lower()
    if re.search(r'resume|cv|curriculum', text):
        return RESUME_PATH if RESUME_PATH.exists() else None
    if re.search(r'transcript', text):
        p = DOCUMENTS_DIR / "transcript.pdf"
        if p.exists():
            return p
        for alt in Path(__file__).parent.parent.joinpath("profile").glob("*ranscript*.pdf"):
            return alt
    if re.search(r'portfolio', text):
        p = DOCUMENTS_DIR / "portfolio.pdf"
        return p if p.exists() else None
    return RESUME_PATH if RESUME_PATH.exists() else None


def _upload_documents(target, profile: Profile) -> int:
    if not RESUME_PATH.exists():
        try:
            from .email_applicator import _build_pdf_resume
            _build_pdf_resume(profile)
        except Exception as e:
            print(f"[form_filler] could not build resume PDF: {e}")

    uploaded = 0
    try:
        inputs = target.query_selector_all('input[type="file"]')
    except Exception:
        return 0
    for el in inputs:
        try:
            name = el.get_attribute("name") or ""
            aria = el.get_attribute("aria-label") or ""
            el_id = el.get_attribute("id")
            label_text = ""
            if el_id:
                lbl = target.query_selector(f'label[for="{el_id}"]')
                if lbl:
                    label_text = lbl.inner_text()
            doc = _resolve_document(" ".join([name, aria, label_text]))
            if doc and doc.exists():
                el.set_input_files(str(doc))
                uploaded += 1
        except Exception:
            continue
    return uploaded


FIELD_MAP_PATTERNS = [
    (r'(parent|guardian|emergency).*(e.?mail)|consent.?email', 'guardian_email'),
    (r'(parent|guardian|emergency).*(phone|tel|mobile|cell)', 'guardian_phone'),
    (r'parent|guardian|emergency.?contact|mother|father', 'guardian_name'),
    (r'first.?name|fname|given.?name', 'first_name'),
    (r'last.?name|lname|surname|family.?name', 'last_name'),
    (r'^name$|full.?name|your.?name', 'full_name'),
    (r'preferred.?name|nickname', 'preferred_name'),
    (r'email', 'email'),
    (r'phone|tel|mobile|cell', 'phone_formatted'),
    (r'permanent.?address|enter a location|^location$', 'address_full'),
    (r'address.?(line.?)?1|street.?address|mailing.?address', 'address_line1'),
    (r'address.?line.?2|apt|suite|unit', 'address_line2'),
    (r'^city$|city.?name|\bcity\b', 'city'),
    (r'^state$|state.?province|state.?region|address.?state|\bstate\b', 'state'),
    (r'zip|postal.?code', 'zip'),
    (r'country', 'country'),
    (r'school|high.?school|institution|current.?school', 'school_name'),
    (r'gpa|grade.?point.?avg', 'gpa_weighted'),
    (r'member_hs_grad_year|grad(uation)?.?year|expected.?grad|class.?of', 'graduation_year'),
    (r'upcoming.?level|level.?of.?study|year.?in.?school', 'current_grade'),
    (r'member_college|college.?name|intended.?college', 'intended_college'),
    (r'class.?rank|rank', 'class_rank'),
    (r'sat.?score|sat.?total', 'sat_total'),
    (r'grade|current.?grade|grade.?level', 'current_grade'),
    (r'major|intended.?major|field.?of.?study', 'intended_major'),
    (r'bio|about.?you|tell.?us.?about|describe.?yourself', 'bio_150'),
    (r'linkedin', 'linkedin'),
    (r'birth.?date|date.?of.?birth|^dob$', 'date_of_birth'),
    (r'gender|sex assigned', 'gender'),
    (r'citizenship|citizen', 'citizenship'),
    (r'ethnicity', 'ethnicity'),
    (r'\brace\b', 'race'),
]


def _get_field_value(field_key: str, profile: Profile) -> str:
    p, a = profile.personal, profile.academic
    mapping = {
        'first_name': p.first_name,
        'last_name': p.last_name,
        'full_name': p.full_name,
        'preferred_name': p.preferred_name,
        'email': p.email,
        'phone_formatted': p.phone_formatted,
        'address_line1': p.address.line1,
        'address_full': f"{p.address.line1}, {p.address.city}, {p.address.state} {p.address.zip}",
        'address_line2': p.address.line2,
        'city': p.address.city,
        'state': p.address.state,
        'zip': p.address.zip,
        'country': p.address.country,
        'school_name': a.current_school,
        'gpa_weighted': str(a.gpa_weighted),
        'graduation_year': str(a.graduation_year),
        'class_rank': str(a.class_rank),
        'sat_total': str(a.sat_total or ""),
        'current_grade': str(a.current_grade),
        'intended_major': a.intended_major,
        'intended_college': "North Carolina State University",
        'bio_150': profile.essay_snippets.bio_150,
        'linkedin': p.linkedin,
        'date_of_birth': p.date_of_birth,
        'gender': p.gender,
        'citizenship': p.citizenship,
        'ethnicity': p.ethnicity,
        'race': p.race,
    }
    if field_key in ("guardian_name", "guardian_email", "guardian_phone") and profile.guardians:
        g = next((x for x in profile.guardians if x.primary), profile.guardians[0])
        return {
            "guardian_name": g.full_name,
            "guardian_email": g.email,
            "guardian_phone": g.phone_formatted or g.phone,
        }[field_key]
    return mapping.get(field_key, "")


def _match_field(label_or_name: str) -> str | None:
    text = (label_or_name or "").lower().strip()
    for pattern, key in FIELD_MAP_PATTERNS:
        if re.search(pattern, text):
            return key
    return None


def score_apply_link(text: str, href: str) -> int:
    """Heuristic score for how likely a link is the actual application."""
    t = (text or "").lower().strip()
    h = (href or "").lower()
    if not h.startswith("http"):
        return 0
    if any(s in h for s in _LINK_SKIP):
        return 0
    score = 0
    if any(x in t for x in ("apply now", "start application", "begin application", "apply here")):
        score += 12
    elif re.search(r'\bapply\b', t):
        score += 8
    if "application" in t:
        score += 5
    if re.search(r'/apply\b|/application|/register|/signup|/sign-up', h):
        score += 10
    if any(x in h for x in ("portal", "app.", "apply.", "forms.gle", "docs.google.com/forms")):
        score += 6
    return score


@dataclass
class FillResult:
    success: bool
    fields_filled: int
    fields_missed: int
    downgraded: bool
    downgrade_reason: str
    screenshot_path: str
    confirmation: str = ""


def _frames(page):
    try:
        return list(page.frames)
    except Exception:
        return [page]


def _looks_like_application_form(target) -> int:
    count = 0
    try:
        els = target.query_selector_all(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]), textarea, select'
        )
    except Exception:
        return 0
    for el in els:
        try:
            search = " ".join([
                el.get_attribute("name") or "",
                el.get_attribute("placeholder") or "",
                el.get_attribute("aria-label") or "",
            ])
            tag = el.evaluate("e => e.tagName")
            if tag == "SELECT" or tag == "TEXTAREA":
                count += 1
                continue
            if (el.get_attribute("type") or "").lower() == "radio":
                count += 1
                continue
            if _match_field(search):
                count += 1
        except Exception:
            continue
    return count


def _form_signal_count(page) -> int:
    return sum(_looks_like_application_form(f) for f in _frames(page))


def _has_submit_control(page) -> bool:
    rx = re.compile(r"submit my application|submit application|^submit$", re.I)
    for frame in _frames(page):
        try:
            if frame.query_selector('input[type="submit"], button[type="submit"]'):
                return True
            if frame.get_by_role("button", name=rx).count() > 0:
                return True
        except Exception:
            continue
    return False


def _ready_to_fill(page) -> bool:
    n = _form_signal_count(page)
    if n >= 2:
        return True
    return n >= 1 and _has_submit_control(page)


def _answer_onboarding(page) -> bool:
    """Click Yes/No / Student wizard steps that have no input fields."""
    try:
        body = (page.inner_text("body") or "")[:1500].lower()
    except Exception:
        return False
    if "applied for scholarships before" in body:
        try:
            loc = page.get_by_text("No", exact=True)
            if loc.count() > 0:
                loc.last.click(timeout=4000)
                return True
        except Exception:
            return _click_named(page, [r"^no$"], roles=("button",))
    if "student or a parent" in body:
        try:
            page.get_by_text("Student", exact=True).first.click(timeout=4000)
            return True
        except Exception:
            return False
    return False


def _form_signal_count(page) -> int:
    return sum(_looks_like_application_form(f) for f in _frames(page))


def _collect_links(page) -> list[dict]:
    try:
        raw = page.evaluate(_LINKS_JS)
    except Exception:
        return []
    links = []
    for item in raw:
        href = (item.get("href") or "")
        text = (item.get("text") or "").strip()
        if not href.startswith("http"):
            continue
        if any(s in href.lower() for s in _LINK_SKIP):
            continue
        links.append({"i": len(links), "text": text or href, "href": href})
    return links


def _click_named(page, patterns: list[str], roles: tuple[str, ...] = ("button", "link")) -> bool:
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for role in roles:
            try:
                loc = page.get_by_role(role, name=rx)
                if loc.count() == 0:
                    continue
                first = loc.first
                if first.is_visible():
                    first.click(timeout=6000)
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(1500)
                    return True
            except Exception:
                continue
        try:
            loc = page.get_by_text(rx)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=6000)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(1500)
                return True
        except Exception:
            continue
    return False


def _ensure_application_page(page, opp, max_hops: int = 5) -> None:
    from . import navigator

    for hop in range(max_hops):
        captcha.solve_if_present(page)
        if _ready_to_fill(page) or _has_submit_control(page):
            return
        if _answer_onboarding(page):
            page.wait_for_timeout(1500)
            continue
        if _click_named(page, APPLY_CLICK_PATTERNS):
            captcha.wait_out_cloudflare(page)
            captcha.solve_if_present(page)
            continue

        links = _collect_links(page)
        target = None
        if links:
            try:
                excerpt = page.inner_text("body")[:1800]
            except Exception:
                excerpt = ""
            decision = navigator.choose_next(opp.title, page.url, links, excerpt)
            if decision.get("action") == "GO":
                target = next((l["href"] for l in links if l["i"] == decision.get("index")), None)
            if not target:
                ranked = sorted(links, key=lambda l: score_apply_link(l["text"], l["href"]), reverse=True)
                if ranked and score_apply_link(ranked[0]["text"], ranked[0]["href"]) >= 6:
                    target = ranked[0]["href"]
        if not target:
            return
        print(f"[form_filler] navigating toward application: {target[:80]}")
        try:
            page.goto(target, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            captcha.wait_out_cloudflare(page)
        except Exception:
            return


def _search_text_for(el, target) -> str:
    name = el.get_attribute("name") or ""
    placeholder = el.get_attribute("placeholder") or ""
    aria_label = el.get_attribute("aria-label") or ""
    label_text = ""
    el_id = el.get_attribute("id")
    if el_id:
        try:
            label_el = target.query_selector(f'label[for="{el_id}"]')
            if label_el:
                label_text = label_el.inner_text()
        except Exception:
            pass
    return " ".join([name, placeholder, aria_label, label_text])


def _fill_target(target, profile: Profile, opp: ClassifiedOpportunity) -> tuple[int, int]:
    filled = 0
    missed = 0
    try:
        inputs = target.query_selector_all(
            'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]), textarea, select'
        )
    except Exception:
        return 0, 0

    for el in inputs:
        try:
            field_type = (el.get_attribute("type") or "text").lower()
            search_text = _search_text_for(el, target)
            if "referral" in search_text.lower() or "double your chances" in search_text.lower():
                continue
            field_key = _match_field(search_text)
            tag = el.evaluate("e => e.tagName")

            if field_type == "radio":
                blob = " ".join([
                    search_text.lower(),
                    (el.get_attribute("value") or "").lower(),
                    (el.get_attribute("aria-label") or "").lower(),
                ])
                gender = (profile.personal.gender or "").lower()
                if gender and gender in blob:
                    el.check()
                    filled += 1
                elif re.search(r'(^|\s|:)student(\s|$)', blob) and "parent" not in (el.get_attribute("aria-label") or "").lower().split(":")[-1]:
                    el.check()
                    filled += 1
                continue
            if field_type == "checkbox":
                continue

            if tag == "TEXTAREA" and field_key in (None, "bio_150"):
                prompt_text = (
                    (el.get_attribute("aria-label") or "")
                    or (el.get_attribute("placeholder") or "")
                    or search_text
                    or "Tell us about yourself and why you are applying"
                )
                if opp.essay_prompts:
                    prompt_text = opp.essay_prompts[0]
                maxlen = el.get_attribute("maxlength")
                answer = writer.draft(
                    prompt_text, profile, opp.title,
                    max_chars=int(maxlen) if maxlen and maxlen.isdigit() else None,
                )
                el.fill(answer)
                filled += 1
                continue

            if not field_key:
                missed += 1
                continue
            value = _get_field_value(field_key, profile)
            if not value:
                missed += 1
                continue

            if field_type in ("text", "email", "tel", "number", "url", "search", "password"):
                el.fill(value)
                filled += 1
            elif tag == "TEXTAREA":
                el.fill(value)
                filled += 1
            elif tag == "SELECT":
                options = el.query_selector_all("option")
                matched = False
                for opt in options:
                    opt_text = (opt.inner_text() or "").lower()
                    opt_val = (opt.get_attribute("value") or "").lower()
                    if value.lower() in opt_text or opt_text in value.lower() or value.lower() in opt_val:
                        el.select_option(value=opt.get_attribute("value") or "")
                        filled += 1
                        matched = True
                        break
                if not matched and field_key in ("graduation_year", "current_grade"):
                    for opt in options:
                        opt_text = (opt.inner_text() or "").lower()
                        if field_key == "graduation_year" and str(profile.academic.graduation_year) in opt_text:
                            el.select_option(value=opt.get_attribute("value") or "")
                            filled += 1
                            matched = True
                            break
                        if field_key == "current_grade" and any(
                            k in opt_text for k in ("high school", "undergraduate", "bachelor", "11")
                        ):
                            el.select_option(value=opt.get_attribute("value") or "")
                            filled += 1
                            matched = True
                            break
                if not matched:
                    missed += 1
            elif field_type == "date" and value:
                el.fill(value)
                filled += 1
        except Exception:
            missed += 1
            continue
    return filled, missed


def _check_terms(page) -> None:
    for frame in _frames(page):
        try:
            boxes = frame.query_selector_all('input[type="checkbox"]')
        except Exception:
            continue
        for checkbox in boxes:
            try:
                name = (checkbox.get_attribute("name") or "").lower()
                aria = (checkbox.get_attribute("aria-label") or "").lower()
                el_id = checkbox.get_attribute("id") or ""
                label_text = ""
                if el_id:
                    lbl = frame.query_selector(f'label[for="{el_id}"]')
                    if lbl:
                        label_text = (lbl.inner_text() or "").lower()
                blob = " ".join([name, aria, label_text])
                if any(t in blob for t in ("terms", "agree", "accept", "privacy", "certify", "confirm", "consent")):
                    if not checkbox.is_checked():
                        checkbox.check()
            except Exception:
                continue


def _apply_site_quirks(page, profile: Profile) -> int:
    """Fill controls generic matching misses (custom radios, native selects by label)."""
    filled = 0
    year = str(profile.academic.graduation_year)
    try:
        loc = page.locator('input[type="radio"][aria-label$="Student"]')
        if loc.count() > 0:
            loc.first.check(force=True)
            filled += 1
    except Exception:
        try:
            page.get_by_text("Student", exact=True).first.click(timeout=2000)
            filled += 1
        except Exception:
            pass
    try:
        loc = page.locator('select[name="member_hs_grad_year"]')
        if loc.count() > 0:
            loc.select_option(label=year)
            filled += 1
    except Exception:
        pass
    try:
        loc = page.locator('select[name="member_upcoming_level_of_study"]')
        if loc.count() > 0:
            loc.select_option(label="High School Junior")
            filled += 1
    except Exception:
        pass
    try:
        page.get_by_label(re.compile(r'^first name', re.I)).fill(profile.personal.first_name, timeout=2000)
        filled += 1
    except Exception:
        pass
    try:
        page.get_by_label(re.compile(r'^last name', re.I)).fill(profile.personal.last_name, timeout=2000)
        filled += 1
    except Exception:
        pass
    try:
        page.locator('input[type="email"]').first.fill(profile.personal.email, timeout=2000)
        filled += 1
    except Exception:
        pass
    try:
        addr = f"{profile.personal.address.line1}, {profile.personal.address.city}, {profile.personal.address.state} {profile.personal.address.zip}"
        loc = page.get_by_placeholder(re.compile(r"location|address", re.I))
        if loc.count() == 0:
            loc = page.get_by_label(re.compile(r"address", re.I))
        if loc.count() > 0:
            box = loc.first
            box.click()
            box.fill("")
            box.type(profile.personal.address.line1, delay=50)
            page.wait_for_timeout(1400)
            picked = False
            for sel in (".pac-item", '[role="option"]'):
                item = page.locator(sel).first
                try:
                    if item.count() > 0 and item.is_visible():
                        item.click(timeout=2000)
                        picked = True
                        break
                except Exception:
                    continue
            if not picked:
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
            filled += 1
    except Exception:
        pass
    return filled


def _fill_all_frames(page, profile: Profile, opp: ClassifiedOpportunity) -> tuple[int, int]:
    filled = missed = uploaded = 0
    for frame in _frames(page):
        f, m = _fill_target(frame, profile, opp)
        filled += f
        missed += m
        uploaded += _upload_documents(frame, profile)
    if uploaded:
        print(f"[form_filler] uploaded {uploaded} document(s)")
    _check_terms(page)
    return filled, missed


def _click_submit(page) -> bool:
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    for frame in _frames(page):
        try:
            clicked = frame.evaluate("""() => {
              const btn = document.querySelector(
                'input.hs-button.primary, input.hs-button, .hs-submit .hs-button, button[type="submit"], input[type="submit"]'
              );
              if (!btn) return false;
              btn.removeAttribute('disabled');
              btn.click();
              return true;
            }""")
            if clicked:
                page.wait_for_timeout(3000)
                return True
        except Exception:
            continue
    try:
        loc = page.get_by_role("button", name=re.compile(r"submit my application|submit application|^submit$", re.I))
        if loc.count() > 0:
            btn = loc.first
            btn.scroll_into_view_if_needed()
            btn.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            return True
    except Exception:
        pass
    try:
        loc = page.locator("input.hs-button, .hs-button, input[type='submit']")
        if loc.count() > 0:
            loc.first.click(force=True, timeout=5000)
            page.wait_for_timeout(3000)
            return True
    except Exception:
        pass
    if _click_named(page, SUBMIT_PATTERNS, roles=("button", "link")):
        return True
    return False


def _extract_confirmation(raw: str) -> str:
    text = raw or ""
    low = text.lower()
    if any(p in low for p in _FAKE_CONFIRM):
        return ""
    match = _CONF_NUM.search(text)
    if match:
        return match.group(0).strip()
    return ""


def _detect_success(page, pre_url: str) -> tuple[bool, str]:
    try:
        raw = page.content()
    except Exception:
        raw = ""
    content = raw.lower()
    post_url = page.url
    url_changed = pre_url.rstrip("/") != post_url.rstrip("/")
    confirmation = _extract_confirmation(raw)
    strong = any(p in content for p in STRONG_SUCCESS) or bool(confirmation)
    weak = any(kw in content for kw in SUCCESS_KEYWORDS)
    still_on_form = (_form_signal_count(page) >= 3) and not url_changed
    success = (strong or (url_changed and weak) or bool(confirmation)) and not still_on_form
    return success, confirmation


def _save_confirmation(opp_id: str, url: str, confirmation: str, snippet: str) -> None:
    CONFIRM_DIR.mkdir(parents=True, exist_ok=True)
    path = CONFIRM_DIR / f"{opp_id}.txt"
    path.write_text(
        f"URL: {url}\nConfirmation: {confirmation or '(thank-you / received page)'}\n\n{snippet[:1500]}\n",
        encoding="utf-8",
    )


def fill_and_submit(opp: ClassifiedOpportunity, profile: Profile, dry_run: bool = False) -> FillResult:
    """Fill and submit a web application. Solves captchas; confirms before claiming success."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[form_filler] Playwright not installed")
        return FillResult(False, 0, 0, True, "Playwright not available", "")

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = captcha.launch_browser(p)
        saved_session = session_store.load(opp.url)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
            storage_state=saved_session if saved_session else None,
        )
        captcha.apply_stealth(context)
        page = context.new_page()

        try:
            page.goto(opp.url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3500)
            if not captcha.wait_out_cloudflare(page):
                return FillResult(False, 0, 0, True, "Cloudflare challenge did not clear", "")
            captcha.solve_if_present(page)

            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
            except Exception:
                pass

            if not saved_session and not _ready_to_fill(page) and not _has_submit_control(page):
                account_creator.ensure_access(page, opp.url, profile)
                page.wait_for_timeout(1000)
                captcha.solve_if_present(page)

            _ensure_application_page(page, opp)
            captcha.solve_if_present(page)

            if dry_run:
                screenshot = SCREENSHOTS_DIR / f"{opp.id}_dryrun.png"
                page.screenshot(path=str(screenshot), full_page=True)
                return FillResult(True, 0, 0, False, "", str(screenshot))

            filled = missed = 0
            from . import page_solver
            for _ in range(4):
                captcha.solve_if_present(page)
                f, m = _fill_all_frames(page, profile, opp)
                filled += f
                missed += m
                filled += _apply_site_quirks(page, profile)
                page.wait_for_timeout(800)
                if _answer_onboarding(page):
                    page.wait_for_timeout(1200)
                    continue
                break

            screenshot_pre = SCREENSHOTS_DIR / f"{opp.id}_prefill.png"
            page.screenshot(path=str(screenshot_pre), full_page=True)

            confirmed, why, steps = page_solver.run(page, profile, opp)
            filled = max(filled, steps)

            screenshot_post = SCREENSHOTS_DIR / f"{opp.id}_post.png"
            try:
                page.screenshot(path=str(screenshot_post), full_page=True)
            except Exception:
                screenshot_post = screenshot_pre

            try:
                session_store.save(opp.url, page.context.storage_state())
            except Exception:
                pass

            if confirmed:
                snippet = ""
                try:
                    snippet = page.inner_text("body")[:1500]
                except Exception:
                    pass
                _save_confirmation(opp.id, page.url, why, snippet)
                return FillResult(True, filled, missed, False, "", str(screenshot_post), why)

            if filled < 2 and not _has_submit_control(page):
                return FillResult(
                    False, filled, missed, True,
                    f"Could not reach a fillable application form (only {filled} applicant fields). Last: {why}",
                    str(screenshot_post),
                )
            return FillResult(
                False, filled, missed, True,
                f"Worked the form but no confirmation ({why})",
                str(screenshot_post),
            )
        except Exception as e:
            return FillResult(False, 0, 0, True, f"Browser error: {str(e)[:160]}", "")
        finally:
            try:
                browser.close()
            except Exception:
                pass
