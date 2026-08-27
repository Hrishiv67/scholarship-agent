"""
Attempts to auto-register an account on a scholarship/internship portal.
Flow: find signup link → fill registration form → submit → verify email via Gmail IMAP.
Falls back gracefully — never crashes the pipeline on failure.
"""
import email as email_lib
import imaplib
import os
import re
import time
from urllib.parse import urlparse

from .profile_loader import Profile
from . import captcha, session_store, accounts

# Registration link text patterns to look for on landing pages
SIGNUP_LINK_TEXTS = [
    "sign up", "create account", "create an account", "register",
    "new account", "join", "get started", "apply now",
]

# Fields commonly found on registration forms
REG_FIELD_PATTERNS = [
    (r'first.?name|fname|given', 'first_name'),
    (r'last.?name|lname|surname', 'last_name'),
    (r'^name$|full.?name', 'full_name'),
    (r'email', 'email'),
    (r'confirm.?email|verify.?email|email.?again', 'email'),
    (r'password|passwd|pwd', 'password'),
    (r'confirm.?pass|verify.?pass|repeat.?pass|re.?enter.?pass', 'password'),
    (r'phone|mobile|tel', 'phone_formatted'),
    (r'zip|postal', 'zip'),
    (r'state', 'state'),
    (r'city', 'city'),
    (r'school|institution|high.?school', 'school_name'),
    (r'grad(uation)?.?year|class.?of', 'graduation_year'),
    (r'grade|current.?grade', 'current_grade'),
    (r'birth.?date|date.?of.?birth|^dob$', 'date_of_birth'),
]


def _get_reg_value(key: str, profile: Profile, password: str) -> str:
    mapping = {
        'first_name': profile.personal.first_name,
        'last_name': profile.personal.last_name,
        'full_name': profile.personal.full_name,
        'email': profile.personal.email,
        'password': password,
        'phone_formatted': profile.personal.phone_formatted,
        'zip': profile.personal.address.zip,
        'state': profile.personal.address.state,
        'city': profile.personal.address.city,
        'school_name': profile.academic.current_school,
        'graduation_year': str(profile.academic.graduation_year),
        'current_grade': str(profile.academic.current_grade),
        'date_of_birth': profile.personal.date_of_birth,
    }
    return mapping.get(key, "")


def _match_reg_field(label_or_name: str) -> str | None:
    text = (label_or_name or "").lower().strip()
    for pattern, key in REG_FIELD_PATTERNS:
        if re.search(pattern, text):
            return key
    return None


def _pick_verification_link(body: str, portal_domain: str) -> str | None:
    """Choose the most likely verification link from an email body."""
    all_links = re.findall(r'https?://[^\s\'"<>]+', body)
    if not all_links:
        return None
    # 1) Links whose URL contains a verification keyword.
    for link in all_links:
        if re.search(r'verif|confirm|activate|token|validate', link, re.I):
            return link
    # 2) Links back to the portal domain (or a mail-tracking redirect to it).
    for link in all_links:
        if portal_domain and portal_domain in link:
            return link
    # 3) Fall back to the first prominent link.
    return all_links[0]


def _fetch_verification_link(gmail_address: str, gmail_password: str, sender_domain: str, timeout: int = 90) -> str | None:
    """
    Polls Gmail IMAP for a verification email. Matches by portal domain OR by a
    verification-style subject (covers SendGrid/Mailgun senders), and extracts the
    link even when it is opaque.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(gmail_address, gmail_password)
            mail.select("inbox")

            ids: list[bytes] = []
            for query in (
                f'(FROM "@{sender_domain}" UNSEEN)',
                '(UNSEEN SUBJECT "verify")',
                '(UNSEEN SUBJECT "confirm")',
                '(UNSEEN SUBJECT "activate")',
            ):
                try:
                    _, data = mail.search(None, query)
                    ids.extend(data[0].split())
                except Exception:
                    continue

            seen = set()
            for msg_id in reversed(ids):
                if msg_id in seen:
                    continue
                seen.add(msg_id)
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() in ("text/plain", "text/html"):
                            payload = part.get_payload(decode=True)
                            if payload:
                                body += payload.decode(errors="ignore")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")

                link = _pick_verification_link(body, sender_domain)
                if link:
                    mail.logout()
                    return link

            mail.logout()
        except Exception as e:
            print(f"[account_creator] IMAP check failed: {e}")

        time.sleep(8)

    return None


def _prefer_email_signup(page) -> None:
    """Avoid Google/Apple OAuth when an email signup path exists."""
    for pat in (
        r"sign ?up with email", r"continue with email", r"use email",
        r"register with email", r"create account with email",
    ):
        try:
            loc = page.get_by_role("button", name=re.compile(pat, re.I))
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=4000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue
        try:
            loc = page.get_by_role("link", name=re.compile(pat, re.I))
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=4000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue


def _looks_logged_in(page) -> bool:
    try:
        content = page.content().lower()
    except Exception:
        return False
    positives = ("sign out", "log out", "your dashboard", "my application", "welcome back")
    negatives = ("sign in", "log in", "create an account", "password")
    if any(p in content for p in positives) and not page.query_selector('input[type="password"]'):
        return True
    if page.query_selector('input[type="password"]') and any(n in content for n in negatives):
        return False
    return False


def login(page, url: str, profile: Profile) -> bool:
    """Log in with the student's email and PORTAL_PASSWORD if a login form is present."""
    password = os.environ.get("PORTAL_PASSWORD", "")
    if not password:
        return False
    email_el = (
        page.query_selector('input[type="email"]')
        or page.query_selector('input[name*="email" i]')
        or page.query_selector('input[autocomplete="username"]')
    )
    pass_el = page.query_selector('input[type="password"]')
    if not email_el or not pass_el:
        return False
    try:
        email_el.fill(profile.personal.email)
        pass_el.fill(password)
    except Exception:
        return False
    captcha.solve_if_present(page)
    submit = (
        page.query_selector('button[type="submit"]')
        or page.query_selector('input[type="submit"]')
        or page.query_selector('button:has-text("Log in")')
        or page.query_selector('button:has-text("Sign in")')
        or page.query_selector('button:has-text("Login")')
    )
    if not submit:
        return False
    try:
        submit.click()
        page.wait_for_timeout(3000)
        captcha.solve_if_present(page)
        storage = page.context.storage_state()
        session_store.save(url, storage)
        domain = urlparse(url).netloc.lower().removeprefix("www.")
        accounts.record(domain, url, profile.personal.email, "agent", "logged in")
        print(f"[account_creator] Logged in on {domain}")
        return True
    except Exception as e:
        print(f"[account_creator] Login failed: {e}")
        return False


def ensure_access(page, url: str, profile: Profile) -> bool:
    """Login if possible, otherwise create an account. Never leaves a CAPTCHA unattempted."""
    if _looks_logged_in(page):
        return True
    captcha.solve_if_present(page)
    if page.query_selector('input[type="password"]') and page.query_selector(
        'input[type="email"], input[name*="email" i]'
    ):
        # Prefer login when the wall is a sign-in form.
        content = ""
        try:
            content = page.content().lower()
        except Exception:
            pass
        if any(w in content for w in ("log in", "sign in", "welcome back")) and "create" not in content[:2000]:
            if login(page, url, profile):
                return True
    created = register(page, url, profile)
    if created:
        return True
    return login(page, url, profile)


def register(page, url: str, profile: Profile) -> bool:
    """
    Attempt to create an account on a portal and verify email.
    page: an active Playwright page already navigated to the opportunity URL.
    Returns True if account created and verified successfully.
    """
    password = os.environ.get("PORTAL_PASSWORD", "")
    gmail_address = os.environ.get("GMAIL_ADDRESS", "")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print("[account_creator] PORTAL_PASSWORD not set — skipping account creation")
        return False

    domain = urlparse(url).netloc.lower().removeprefix("www.")
    already_on_form = bool(
        page.query_selector('input[type="email"], input[name*="email" i]')
        and page.query_selector('input[type="password"]')
    )

    if not already_on_form:
        signup_link = None
        for text in SIGNUP_LINK_TEXTS:
            el = (
                page.query_selector(f'a:has-text("{text}")') or
                page.query_selector(f'button:has-text("{text}")')
            )
            if el:
                try:
                    if not el.is_visible():
                        continue
                except Exception:
                    continue
                signup_link = el
                break

        if signup_link:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                signup_link.click(timeout=8000, force=True)
                page.wait_for_load_state("domcontentloaded")
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[account_creator] Could not click signup link: {e}")
                return False
        else:
            found = False
            for suffix in ["/signup", "/register", "/create-account", "/join", "/apply"]:
                base = f"{urlparse(url).scheme}://{urlparse(url).netloc}{suffix}"
                try:
                    page.goto(base, timeout=10000, wait_until="domcontentloaded")
                    if page.query_selector('input[type="email"], input[name*="email" i]'):
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                print(f"[account_creator] No signup link found on {domain}")
                return False

    _prefer_email_signup(page)
    captcha.solve_if_present(page)

    # Step 2: Fill registration form
    filled = 0
    inputs = page.query_selector_all(
        'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), select'
    )

    for el in inputs:
        try:
            field_type = el.get_attribute("type") or "text"
            name = el.get_attribute("name") or ""
            placeholder = el.get_attribute("placeholder") or ""
            aria_label = el.get_attribute("aria-label") or ""

            label_text = ""
            el_id = el.get_attribute("id")
            if el_id:
                label_el = page.query_selector(f'label[for="{el_id}"]')
                if label_el:
                    label_text = label_el.inner_text()

            search_text = " ".join([name, placeholder, aria_label, label_text])
            key = _match_reg_field(search_text)
            if not key:
                continue

            value = _get_reg_value(key, profile, password)
            if not value:
                continue

            if field_type in ("text", "email", "tel", "number", "password"):
                el.fill(value)
                filled += 1
            elif field_type == "checkbox" and key in ("terms", "agree"):
                el.check()
                filled += 1
        except Exception:
            continue

    if filled < 2:
        print(f"[account_creator] Could not fill registration form on {domain} (filled {filled} fields)")
        return False

    # Handle checkboxes for terms of service
    for checkbox in page.query_selector_all('input[type="checkbox"]'):
        try:
            name = (checkbox.get_attribute("name") or "").lower()
            label_id = checkbox.get_attribute("id")
            label_text = ""
            if label_id:
                lbl = page.query_selector(f'label[for="{label_id}"]')
                if lbl:
                    label_text = lbl.inner_text().lower()
            if any(t in name + label_text for t in ["terms", "agree", "accept", "privacy"]):
                checkbox.check()
        except Exception:
            continue

    # Step 3: Solve CAPTCHA, then submit registration
    captcha.solve_if_present(page)
    submit = (
        page.query_selector('button[type="submit"]') or
        page.query_selector('input[type="submit"]') or
        page.query_selector('button:has-text("Sign up")') or
        page.query_selector('button:has-text("Create account")') or
        page.query_selector('button:has-text("Register")')
    )

    if not submit:
        print(f"[account_creator] No submit button found on registration form for {domain}")
        return False

    try:
        submit.click()
        page.wait_for_timeout(3000)
        captcha.solve_if_present(page)
    except Exception as e:
        print(f"[account_creator] Submit click failed: {e}")
        return False

    # Step 4: Check if registration succeeded (look for "check your email" message)
    content = page.content().lower()
    check_email_signals = ["check your email", "verify your email", "confirmation email", "sent you an email"]
    already_exists = any(s in content for s in (
        "already have an account", "account already exists", "email already",
        "already registered",
    ))
    if already_exists:
        print(f"[account_creator] Account already exists on {domain} — logging in")
        return login(page, url, profile)

    if not any(sig in content for sig in check_email_signals):
        try:
            storage = page.context.storage_state()
            session_store.save(url, storage)
            accounts.record(domain, url, profile.personal.email, "agent",
                            "created (no email verification)")
            print(f"[account_creator] Registered on {domain} (no email verification needed)")
            return True
        except Exception:
            pass
        print(f"[account_creator] Registration unclear on {domain}")
        return False

    if not gmail_address or not gmail_app_password:
        print("[account_creator] Gmail credentials not set — cannot verify email")
        return False

    # Step 5: Fetch verification link from Gmail
    print(f"[account_creator] Waiting for verification email from {domain}...")
    verify_link = _fetch_verification_link(gmail_address, gmail_app_password, domain, timeout=90)

    if not verify_link:
        print(f"[account_creator] Verification email not received from {domain} within 60s")
        return False

    # Step 6: Click verification link
    try:
        page.goto(verify_link, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        # Save session after successful verification
        storage = page.context.storage_state()
        session_store.save(url, storage)
        accounts.record(domain, url, profile.personal.email, "agent", "created & verified")
        print(f"[account_creator] Account created and verified on {domain}")
        return True
    except Exception as e:
        print(f"[account_creator] Verification link failed: {e}")
        return False
