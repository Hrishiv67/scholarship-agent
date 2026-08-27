"""
Handle reCAPTCHA, hCaptcha, and Cloudflare Turnstile for free.

Strategy (no paid solver required):
1. Use a real-looking browser so many widgets never challenge.
2. Click the checkbox / wait for Turnstile to auto-pass.
3. Invisible reCAPTCHA v3 often succeeds on submit if the session looks human.
Paid 2Captcha/CapSolver keys are optional and unused unless you set them.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

_SITEKEY = re.compile(
    r'(?:data-sitekey|data-site-key)\s*=\s*["\']([^"\']+)["\']',
    re.I,
)
_RECAPTCHA_K = re.compile(
    r'(?:google\.com|recaptcha\.net)/recaptcha/(?:api2|enterprise|api\.js)[^"\']*[?&](?:k|render)=([A-Za-z0-9_-]{20,})',
    re.I,
)
_RECAPTCHA_RENDER = re.compile(
    r'recaptcha/api\.js\?render=([A-Za-z0-9_-]{20,})',
    re.I,
)
_HCAPTCHA_K = re.compile(
    r'hcaptcha\.com/1/api\.js[^"\']*[?&]sitekey=([A-Za-z0-9_-]{20,})',
    re.I,
)
_TURNSTILE_K = re.compile(
    r'challenges\.cloudflare\.com/turnstile[^"\']*[?&]k=([A-Za-z0-9_-]{10,})',
    re.I,
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


@dataclass
class Challenge:
    kind: str  # recaptcha_v2 | recaptcha_v3 | hcaptcha | turnstile
    sitekey: str
    page_url: str


def parse_html(html: str, page_url: str) -> Challenge | None:
    """Detect a captcha challenge from page HTML. Pure string parsing (testable)."""
    if not html:
        return None
    lower = html.lower()

    if "cf-turnstile" in lower or "challenges.cloudflare.com/turnstile" in lower:
        key = _first(_SITEKEY.findall(html) + _TURNSTILE_K.findall(html))
        if key:
            return Challenge("turnstile", key, page_url)

    if "hcaptcha" in lower or "h-captcha" in lower:
        key = _first(_SITEKEY.findall(html) + _HCAPTCHA_K.findall(html))
        if key:
            return Challenge("hcaptcha", key, page_url)

    v3 = _RECAPTCHA_RENDER.search(html)
    if v3 and "grecaptcha.execute" in html:
        return Challenge("recaptcha_v3", v3.group(1), page_url)

    if "recaptcha" in lower or "g-recaptcha" in lower:
        key = _first(_SITEKEY.findall(html) + _RECAPTCHA_K.findall(html))
        if key:
            kind = "recaptcha_v3" if v3 and v3.group(1) == key else "recaptcha_v2"
            return Challenge(kind, key, page_url)

    return None


def _first(items: list[str]) -> str | None:
    for item in items:
        if item and item.lower() not in ("null", "undefined", "true", "false"):
            return item
    return None


def detect(page) -> Challenge | None:
    frames = []
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    for frame in frames:
        try:
            html = frame.content()
            url = getattr(frame, "url", None) or getattr(page, "url", "")
        except Exception:
            continue
        found = parse_html(html, url)
        if found:
            found.page_url = getattr(page, "url", found.page_url)
            return found
    return None


def _token_present(page) -> bool:
    js = """() => {
      const val = (sel) => {
        const el = document.querySelector(sel);
        return el && (el.value || el.innerHTML || '').trim().length > 20;
      };
      if (val('textarea[name="g-recaptcha-response"]')) return true;
      if (val('textarea#g-recaptcha-response')) return true;
      if (val('[name="h-captcha-response"]')) return true;
      if (val('[name="cf-turnstile-response"]')) return true;
      const box = document.querySelector('#recaptcha-anchor');
      if (box && box.getAttribute('aria-checked') === 'true') return true;
      return false;
    }"""
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    for frame in frames:
        try:
            if frame.evaluate(js):
                return True
        except Exception:
            continue
    return False


def _click_in_frames(page, url_substr: str, selectors: list[str]) -> bool:
    try:
        frames = list(page.frames)
    except Exception:
        return False
    for frame in frames:
        url = (getattr(frame, "url", "") or "")
        if url_substr not in url:
            continue
        for sel in selectors:
            try:
                el = frame.query_selector(sel)
                if el:
                    el.click()
                    return True
            except Exception:
                continue
    return False


def _solve_free(page, timeout: int = 20) -> bool:
    """Click the visible checkbox / wait for Turnstile. No paid API."""
    if _token_present(page):
        return True

    clicked = _click_in_frames(
        page, "recaptcha",
        ["#recaptcha-anchor", ".recaptcha-checkbox-border", ".recaptcha-checkbox"],
    )
    clicked = _click_in_frames(
        page, "hcaptcha",
        ["#checkbox", ".check", "[role='checkbox']"],
    ) or clicked
    if not clicked:
        try:
            loc = page.frame_locator('iframe[src*="recaptcha"][src*="anchor"]').locator(
                "#recaptcha-anchor"
            )
            loc.click(timeout=2500)
            clicked = True
        except Exception:
            pass
        try:
            loc = page.frame_locator('iframe[src*="hcaptcha"][title*="checkbox" i]').locator(
                "#checkbox"
            )
            loc.click(timeout=2500)
            clicked = True
        except Exception:
            pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        if _token_present(page):
            print("[captcha] Passed (checkbox / Turnstile, no paid solver)")
            return True
        wait_out_cloudflare(page, timeout_ms=2000)
        try:
            page.wait_for_timeout(700)
        except Exception:
            break
    return _token_present(page)


def solve_if_present(page, timeout: int = 25) -> bool:
    """
    Try to pass a captcha for free. Never blocks the pipeline: if the widget
    is still there we continue and let submit + confirmation decide success.
    """
    challenge = detect(page)
    if not challenge:
        return True
    print(f"[captcha] {challenge.kind} on page — trying free pass")
    if _solve_free(page, timeout=timeout):
        return True
    # Invisible / score-based widgets often resolve only after submit.
    print("[captcha] No token yet; continuing (many widgets pass on submit)")
    return True


def wait_out_cloudflare(page, timeout_ms: int = 20000) -> bool:
    """Give Cloudflare's managed challenge a chance to auto-resolve."""
    try:
        title = (page.title() or "").lower()
    except Exception:
        return True
    if "just a moment" not in title and "attention required" not in title and "cloudflare" not in title:
        return True
    print("[captcha] Cloudflare interstitial — waiting for it to clear")
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            page.wait_for_timeout(1500)
            title = (page.title() or "").lower()
            if "just a moment" not in title and "attention required" not in title:
                return True
        except Exception:
            return False
    return False


def apply_stealth(context) -> None:
    try:
        context.add_init_script(STEALTH_JS)
    except Exception:
        pass


def launch_browser(playwright):
    """Headed on GitHub Actions (via xvfb) so widgets are more likely to auto-pass."""
    headed = os.environ.get("HEADED", "").lower() in ("1", "true", "yes")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        headed = True
    return playwright.chromium.launch(
        headless=not headed,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
