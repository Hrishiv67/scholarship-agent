import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.form_filler import _match_field, score_apply_link, _extract_confirmation


def test_match_core_fields():
    assert _match_field("First Name") == "first_name"
    assert _match_field("email address") == "email"
    assert _match_field("parent email") == "guardian_email"
    assert _match_field("GPA") == "gpa_weighted"
    print("PASS: field matching")


def test_score_apply_link():
    assert score_apply_link("Apply Now", "https://school.edu/apply") >= 12
    assert score_apply_link("Donate", "https://school.edu/donate") == 0
    assert score_apply_link("News", "https://facebook.com/post") == 0
    assert score_apply_link("Learn more", "https://school.edu/about") < score_apply_link(
        "Start application", "https://school.edu/application"
    )
    print("PASS: apply-link scoring")


def test_cloudflare_is_not_confirmation():
    raw = (
        "Press & Hold to confirm you are a human (and not a bot). "
        "Reference ID aa862371-a266-11f1-a0ee-98d51c9a6ad5"
    )
    assert _extract_confirmation(raw) == ""
    print("PASS: cloudflare reference id is not a confirmation")


if __name__ == "__main__":
    test_match_core_fields()
    test_score_apply_link()
    test_cloudflare_is_not_confirmation()
