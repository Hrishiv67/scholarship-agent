import re
import time
from dataclasses import dataclass
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .profile_loader import Profile
from . import session_store, account_creator

SCREENSHOTS_DIR = Path(__file__).parent.parent / "outputs" / "screenshots"

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

FIELD_MAP_PATTERNS = [
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

            if filled == 0:
                browser.close()
                return FillResult(False, 0, missed, True, "No fields could be filled — likely account-required form", "")

            # Take screenshot before submitting
            screenshot_pre = SCREENSHOTS_DIR / f"{opp.id}_prefill.png"
            page.screenshot(path=str(screenshot_pre))

            # Find and click submit
            submit = (
                page.query_selector('button[type="submit"]') or
                page.query_selector('input[type="submit"]') or
                page.query_selector('button:has-text("Submit")') or
                page.query_selector('button:has-text("Apply")') or
                page.query_selector('button:has-text("Send")')
            )

            if not submit:
                browser.close()
                return FillResult(False, filled, missed, True, "Submit button not found", str(screenshot_pre))

            submit.click()
            page.wait_for_timeout(3000)

            # Check for success
            content = page.content().lower()
            success = any(kw in content for kw in SUCCESS_KEYWORDS)

            screenshot_post = SCREENSHOTS_DIR / f"{opp.id}_post.png"
            page.screenshot(path=str(screenshot_post))
            browser.close()

            return FillResult(success, filled, missed, False, "", str(screenshot_post))

        except Exception as e:
            try:
                browser.close()
            except Exception:
                pass
            return FillResult(False, 0, 0, True, f"Browser error: {str(e)[:100]}", "")
