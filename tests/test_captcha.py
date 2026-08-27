import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.captcha import parse_html


def test_recaptcha_v2_data_sitekey():
    html = '<div class="g-recaptcha" data-sitekey="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"></div>'
    challenge = parse_html(html, "https://example.com/apply")
    assert challenge is not None
    assert challenge.kind == "recaptcha_v2"
    assert challenge.sitekey.startswith("6LeIxAcT")
    print("PASS: reCAPTCHA v2 sitekey")


def test_recaptcha_iframe_k():
    html = '<iframe src="https://www.google.com/recaptcha/api2/anchor?k=6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI"></iframe>'
    challenge = parse_html(html, "https://example.com/apply")
    assert challenge is not None
    assert "recaptcha" in challenge.kind
    assert "6LeIxAcT" in challenge.sitekey
    print("PASS: reCAPTCHA iframe k=")


def test_turnstile():
    html = '<div class="cf-turnstile" data-sitekey="0x4AAAAAAABBBBBBBBBBBBBB"></div>'
    challenge = parse_html(html, "https://example.com/apply")
    assert challenge is not None
    assert challenge.kind == "turnstile"
    assert challenge.sitekey.startswith("0x4")
    print("PASS: Turnstile")


def test_hcaptcha():
    html = '<div class="h-captcha" data-sitekey="a1b2c3d4e5f6g7h8i9j0klmnopqrstuv"></div>'
    challenge = parse_html(html, "https://example.com/signup")
    assert challenge is not None
    assert challenge.kind == "hcaptcha"
    print("PASS: hCaptcha")


def test_no_captcha():
    assert parse_html("<form><input name='email'></form>", "https://example.com") is None
    print("PASS: no captcha")


if __name__ == "__main__":
    test_recaptcha_v2_data_sitekey()
    test_recaptcha_iframe_k()
    test_turnstile()
    test_hcaptcha()
    test_no_captcha()
