import re
import time
from dataclasses import dataclass
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import session_store, account_creator, writer

SCREENSHOTS_DIR = Path(__file__).parent.parent / "outputs" / "screenshots"
RESUME_PATH = Path(__file__).parent.parent / "profile" / "resume.pdf"
DOCUMENTS_DIR = Path(__file__).parent.parent / "profile" / "documents"


def _resolve_document(label: str) -> Path | None:
    """Match a file-field label to a document on disk."""
    text = (label or "").lower()
    if re.search(r'resume|cv|curriculum', text):
        return RESUME_PATH if RESUME_PATH.exists() else None
    if re.search(r'transcript', text):
        p = DOCUMENTS_DIR / "transcript.pdf"
        return p if p.exists() else None
    if re.search(r'portfolio', text):
        p = DOCUMENTS_DIR / "portfolio.pdf"
        return p if p.exists() else None
    # Default any unmatched file field to the resume so uploads are not skipped.
    return RESUME_PATH if RESUME_PATH.exists() else None


def _upload_documents(page, profile: Profile) -> int:
    """Fill file inputs with the resume / matching documents. Returns count uploaded."""
    # Ensure a resume PDF exists.
    if not RESUME_PATH.exists():
        try:
            from .email_applicator import _build_pdf_resume
            _build_pdf_resume(profile)
        except Exception as e:
            print(f"[form_filler] could not build resume PDF: {e}")

    uploaded = 0
    for el in page.query_selector_all('input[type="file"]'):
        try:
            name = el.get_attribute("name") or ""
            aria = el.get_attribute("aria-label") or ""
            el_id = el.get_attribute("id")
            label_text = ""
            if el_id:
                lbl = page.query_selector(f'label[for="{el_id}"]')
                if lbl:
                    label_text = lbl.inner_text()
            doc = _resolve_document(" ".join([name, aria, label_text]))
            if doc and doc.exists():
                el.set_input_files(str(doc))
                uploaded += 1
        except Exception:
            continue
    return uploaded

CAPTCHA_SELECTORS = [
    'iframe[src*="recaptcha"]',
    'iframe[src*="hcaptcha"]',
    '.cf-turnstile',
    '#challenge-stage',
    '[data-sitekey]',
]

SUCCESS_KEYWORDS = [
    "thank you", "thanks for", "submitted", "received", "application complete",
    "successfully", "confirmation", "we have received", "you have applied",
]

# Strong, specific evidence that an APPLICATION (not a newsletter) was received.
STRONG_SUCCESS = [
    "application has been submitted", "application was submitted",
    "your application has been received", "we have received your application",
    "thank you for applying", "thank you for your application",
    "application successfully submitted", "your application has been submitted",
    "application complete", "confirmation number", "reference number",
]
_CONF_NUM = re.compile(r'(confirmation|reference|application)\s*(number|no\.?|id|#)\s*[:#]?\s*([A-Za-z0-9-]{5,})', re.I)

# Links that lead from a program page to its actual application.
APPLY_LINK_TEXTS = [
    "start application", "begin application", "apply now", "apply online",
    "start your application", "application form", "apply for",
]


def _looks_like_application_form(page) -> int:
    """Count inputs whose label maps to a real applicant field (name/email/etc.)."""
    count = 0
    for el in page.query_selector_all('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select'):
        try:
            search = " ".join([
                el.get_attribute("name") or "", el.get_attribute("placeholder") or "",
                el.get_attribute("aria-label") or "",
            ])
            if _match_field(search):
                count += 1
        except Exception:
            continue
    return count


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

_LINK_SKIP = ("facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
              "youtube.com", "/donate", "/news", "/about", "/contact", "/privacy",
              "mailto:", "tel:")


def _collect_links(page) -> list[dict]:
    try:
        raw = page.evaluate(_LINKS_JS)
    except Exception:
        return []
    links = []
    for l in raw:
        href = (l.get("href") or "")
        text = (l.get("text") or "").strip()
        if not href.startswith("http"):
            continue
        if any(s in href.lower() for s in _LINK_SKIP):
            continue
        links.append({"i": len(links), "text": text or href, "href": href})
    return links


def _ensure_application_page(page, opp, max_hops: int = 3) -> None:
    """Use the AI navigator to reach the real application, hopping up to max_hops."""
    from . import navigator
    for _ in range(max_hops):
        if _looks_like_application_form(page) >= 3:
            return
        links = _collect_links(page)
        if not links:
            return
        try:
            excerpt = page.inner_text("body")[:1800]
        except Exception:
            excerpt = ""
        decision = navigator.choose_next(opp.title, page.url, links, excerpt)
        action = decision.get("action")
        if action in ("THIS_PAGE", "NONE"):
            return
        target = next((l["href"] for l in links if l["i"] == decision.get("index")), None)
        if not target:
            return
        print(f"[form_filler] navigating toward application: {target[:80]}")
        try:
            page.goto(target, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
        except Exception:
            return

FIELD_MAP_PATTERNS = [
    # Parent / guardian / emergency contact (checked first so "parent email" != email)
    (r'(parent|guardian|emergency).*(e.?mail)|consent.?email', 'guardian_email'),
    (r'(parent|guardian|emergency).*(phone|tel|mobile|cell)', 'guardian_phone'),
    (r'parent|guardian|emergency.?contact|mother|father', 'guardian_name'),
    # Name
    (r'first.?name|fname|given.?name', 'first_name'),
    (r'last.?name|lname|surname|family.?name', 'last_name'),
    (r'^name$|full.?name|your.?name', 'full_name'),
    (r'preferred.?name|nickname', 'preferred_name'),
    # Contact
    (r'email', 'email'),
    (r'phone|tel|mobile|cell', 'phone_formatted'),
    # Address
    (r'address.?(line.?)?1|street.?address|mailing.?address', 'address_line1'),
    (r'address.?line.?2|apt|suite|unit', 'address_line2'),
    (r'^city$|city.?name', 'city'),
    (r'^state$|state.?province|state.?region', 'state'),
    (r'zip|postal.?code', 'zip'),
    (r'country', 'country'),
    # Academic
    (r'school|high.?school|institution|current.?school', 'school_name'),
    (r'gpa|grade.?point.?avg', 'gpa_weighted'),
    (r'grad(uation)?.?year|expected.?grad|class.?of', 'graduation_year'),
    (r'class.?rank|rank', 'class_rank'),
    (r'sat.?score|sat.?total', 'sat_total'),
    (r'grade|current.?grade|grade.?level', 'current_grade'),
    (r'major|intended.?major|field.?of.?study', 'intended_major'),
    # Bio/short answer
    (r'bio|about.?you|tell.?us.?about|describe.?yourself', 'bio_150'),
    (r'linkedin', 'linkedin'),
]


def _get_field_value(field_key: str, profile: Profile) -> str:
    mapping = {
        'first_name': profile.personal.first_name,
        'last_name': profile.personal.last_name,
        'full_name': profile.personal.full_name,
        'preferred_name': profile.personal.preferred_name,
        'email': profile.personal.email,
        'phone_formatted': profile.personal.phone_formatted,
        'address_line1': profile.personal.address.line1,
        'address_line2': profile.personal.address.line2,
        'city': profile.personal.address.city,
        'state': profile.personal.address.state,
        'zip': profile.personal.address.zip,
        'country': profile.personal.address.country,
        'school_name': profile.academic.current_school,
        'gpa_weighted': str(profile.academic.gpa_weighted),
        'graduation_year': str(profile.academic.graduation_year),
        'class_rank': str(profile.academic.class_rank),
        'sat_total': str(profile.academic.sat_total or ""),
        'current_grade': str(profile.academic.current_grade),
        'intended_major': profile.academic.intended_major,
        'bio_150': profile.essay_snippets.bio_150,
        'linkedin': profile.personal.linkedin,
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


@dataclass
class FillResult:
    success: bool
    fields_filled: int
    fields_missed: int
    downgraded: bool
    downgrade_reason: str
    screenshot_path: str


def fill_and_submit(opp: ClassifiedOpportunity, profile: Profile, dry_run: bool = False) -> FillResult:
    """
    Attempt to fill and submit a web form using Playwright.
    Returns FillResult. If CAPTCHA detected, returns downgraded=True.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[form_filler] Playwright not installed")
        return FillResult(False, 0, 0, True, "Playwright not available", "")

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # Restore saved session if one exists for this domain
        saved_session = session_store.load(opp.url)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            storage_state=saved_session if saved_session else None,
        )
        page = context.new_page()

        try:
            page.goto(opp.url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            # If no saved session and page looks like a login wall, try account creation
            if not saved_session:
                content_lower = page.content().lower()
                login_wall_signals = ["sign in to continue", "log in to apply", "create an account to", "please log in", "please sign in"]
                if any(sig in content_lower for sig in login_wall_signals):
                    print(f"[form_filler] Login wall detected — attempting account creation for {opp.url}")
                    created = account_creator.register(page, opp.url, profile)
                    if not created:
                        browser.close()
                        return FillResult(False, 0, 0, True, "Login wall — account creation failed", "")
                    # Re-navigate to the application URL after registration
                    page.goto(opp.url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)

            # If this is a program/info page, let the AI navigate to the real form.
            _ensure_application_page(page, opp)

            # Check for CAPTCHA
            for sel in CAPTCHA_SELECTORS:
                if page.query_selector(sel):
                    browser.close()
                    return FillResult(False, 0, 0, True, f"CAPTCHA detected: {sel}", "")

            # Check for Cloudflare challenge via page title/content
            title = page.title().lower()
            if "just a moment" in title or "cloudflare" in title:
                browser.close()
                return FillResult(False, 0, 0, True, "Cloudflare challenge page", "")

            if dry_run:
                screenshot = SCREENSHOTS_DIR / f"{opp.id}_dryrun.png"
                page.screenshot(path=str(screenshot))
                browser.close()
                return FillResult(True, 0, 0, False, "", str(screenshot))

            # Find and fill all form fields
            filled = 0
            missed = 0
            inputs = page.query_selector_all('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, select')

            for el in inputs:
                try:
                    field_type = el.get_attribute("type") or "text"
                    name = el.get_attribute("name") or ""
                    placeholder = el.get_attribute("placeholder") or ""
                    aria_label = el.get_attribute("aria-label") or ""

                    # Try to get label text
                    label_text = ""
                    el_id = el.get_attribute("id")
                    if el_id:
                        label_el = page.query_selector(f'label[for="{el_id}"]')
                        if label_el:
                            label_text = label_el.inner_text()

                    search_text = " ".join([name, placeholder, aria_label, label_text])
                    field_key = _match_field(search_text)

                    tag = el.evaluate("e => e.tagName")

                    # Essay / free-text field → draft in Hrishiv's voice, fitted to any limit.
                    if tag == "TEXTAREA" and field_key in (None, "bio_150"):
                        prompt_text = (label_text or placeholder or aria_label or name
                                       or "Tell us about yourself and why you are applying")
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

                    if field_type in ("text", "email", "tel", "number", "url"):
                        el.fill(value)
                        filled += 1
                    elif field_type == "textarea" or el.evaluate("e => e.tagName") == "TEXTAREA":
                        el.fill(value)
                        filled += 1
                    elif el.evaluate("e => e.tagName") == "SELECT":
                        # Try to select matching option
                        options = el.query_selector_all("option")
                        for opt in options:
                            opt_text = opt.inner_text().lower()
                            if value.lower() in opt_text or opt_text in value.lower():
                                el.select_option(value=opt.get_attribute("value") or "")
                                filled += 1
                                break
                        else:
                            missed += 1
                except Exception:
                    missed += 1
                    continue

            # Upload resume / documents to any file fields.
            uploaded = _upload_documents(page, profile)
            if uploaded:
                print(f"[form_filler] uploaded {uploaded} document(s)")

            # Honesty guard: a real application maps several applicant fields. If we
            # only matched 0-2, this is almost certainly a homepage / newsletter box,
            # not an application. Do NOT submit or claim success.
            if filled < 3:
                screenshot_info = SCREENSHOTS_DIR / f"{opp.id}_notform.png"
                page.screenshot(path=str(screenshot_info))
                browser.close()
                return FillResult(
                    False, filled, missed, True,
                    f"Landed on an info/home page, not an application form "
                    f"(only {filled} applicant fields). Needs you to start the application.",
                    str(screenshot_info),
                )

            # Take screenshot before submitting
            screenshot_pre = SCREENSHOTS_DIR / f"{opp.id}_prefill.png"
            page.screenshot(path=str(screenshot_pre))

            # Find and click submit
            submit = (
                page.query_selector('button[type="submit"]') or
                page.query_selector('input[type="submit"]') or
                page.query_selector('button:has-text("Submit Application")') or
                page.query_selector('button:has-text("Submit")') or
                page.query_selector('button:has-text("Send")')
            )

            if not submit:
                browser.close()
                return FillResult(False, filled, missed, True, "Submit button not found", str(screenshot_pre))

            pre_url = page.url
            submit.click()
            page.wait_for_timeout(4000)

            # Honest success detection: require real evidence the application was received,
            # not just the word "thank you" (a newsletter signup shows that too).
            raw = page.content()
            content = raw.lower()
            post_url = page.url
            url_changed = pre_url.rstrip("/") != post_url.rstrip("/")
            strong = any(p in content for p in STRONG_SUCCESS) or bool(_CONF_NUM.search(raw))
            weak = any(kw in content for kw in SUCCESS_KEYWORDS)
            # Still showing the same filled form with the same fields = not submitted.
            still_on_form = (_looks_like_application_form(page) >= 3) and not url_changed
            success = (strong or (url_changed and weak)) and not still_on_form

            screenshot_post = SCREENSHOTS_DIR / f"{opp.id}_post.png"
            page.screenshot(path=str(screenshot_post))
            browser.close()

            if success:
                return FillResult(True, filled, missed, False, "", str(screenshot_post))
            # Filled a real form but no confirmation appeared: do not claim it applied.
            return FillResult(
                False, filled, missed, True,
                "Filled the application but no confirmation appeared - please verify and submit",
                str(screenshot_post),
            )

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return FillResult(False, 0, 0, True, f"Browser error: {str(e)[:100]}", "")
