import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.page_solver import decide_heuristic, profile_facts
from agent.profile_loader import load


def test_heuristic_fills_empty_email():
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "",
        "errors": [],
        "heading": "Apply",
        "submitEnabled": False,
        "buttons": [{"text": "Submit my application", "disabled": True}],
        "fields": [
            {"tag": "input", "type": "email", "name": "email", "id": "email",
             "placeholder": "", "label": "Email address", "value": "",
             "empty": True, "required": True, "invalid": False},
        ],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action is not None
    assert action["action"] == "FILL"
    assert "hrishiv" in action["value"].lower()
    print("PASS: heuristic fills empty email")


def test_heuristic_address_error():
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "application information",
        "errors": ["Full street address required"],
        "heading": "",
        "submitEnabled": False,
        "buttons": [],
        "fields": [
            {"tag": "input", "type": "text", "name": "address", "id": "",
             "placeholder": "Enter a location", "label": "Permanent Address",
             "value": "x", "empty": False, "required": True, "invalid": True},
        ],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action is not None
    assert action["action"] == "ADDRESS"
    print("PASS: heuristic fixes address error")


def test_heuristic_clicks_student():
    from agent.page_solver import decide_heuristic, profile_facts
    from agent.profile_loader import load
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "Are you a student or a parent?",
        "errors": [],
        "heading": "",
        "submitEnabled": False,
        "buttons": [{"text": "Student", "disabled": False}, {"text": "Parent", "disabled": False}],
        "fields": [],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action and action["action"] == "CLICK" and action["target"] == "Student"
    print("PASS: heuristic clicks Student")


def test_heuristic_gives_up_without_dob():
    from agent.page_solver import decide_heuristic, profile_facts
    from agent.profile_loader import load
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "date of birth",
        "errors": [],
        "heading": "",
        "submitEnabled": False,
        "buttons": [],
        "fields": [
            {"tag": "input", "type": "text", "name": "dob", "id": "",
             "placeholder": "", "label": "Date of birth", "value": "",
             "empty": True, "required": True, "invalid": False},
        ],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action and action["action"] == "GIVE_UP"
    print("PASS: heuristic gives up without DOB")


def test_heuristic_skips_continue_when_school_empty():
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "which high school do you currently attend?",
        "errors": [],
        "heading": "",
        "submitEnabled": False,
        "buttons": [{"text": "Continue", "disabled": False}],
        "fields": [
            {"tag": "input", "type": "text", "name": "school", "id": "",
             "placeholder": "", "label": "Which High School do you currently attend?",
             "value": "", "empty": True, "required": True, "invalid": False},
        ],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action and action["action"] == "FILL"
    assert "green hope" in action["value"].lower()
    print("PASS: heuristic fills school instead of Continue")


def test_heuristic_picks_start_year():
    profile = load()
    facts = profile_facts(profile)
    assert facts["hs_start_year"] == "2024"
    snap = {
        "body": "When did you start studying at Green Hope High?",
        "errors": [],
        "heading": "",
        "submitEnabled": False,
        "buttons": [{"text": "Select year", "disabled": False}, {"text": "2024", "disabled": False}],
        "fields": [],
    }
    action = decide_heuristic(snap, facts, profile)
    assert action and action["action"] == "CLICK" and action["target"] == "2024"
    print("PASS: heuristic picks high school start year 2024")


def test_heuristic_does_not_give_up_on_cloudflare_dob():
    profile = load()
    facts = profile_facts(profile)
    snap = {
        "body": "Press & Hold to confirm you are a human (and not a bot).",
        "errors": [],
        "heading": "",
        "submitEnabled": False,
        "buttons": [],
        "fields": [
            {"tag": "input", "type": "text", "name": "dob", "id": "",
             "placeholder": "", "label": "Date of birth", "value": "",
             "empty": True, "required": True, "invalid": False},
        ],
    }
    action = decide_heuristic(snap, facts, profile)
    assert not action or action.get("action") != "GIVE_UP"
    print("PASS: cloudflare page does not trigger DOB give-up")


if __name__ == "__main__":
    test_heuristic_fills_empty_email()
    test_heuristic_address_error()
    test_heuristic_clicks_student()
    test_heuristic_gives_up_without_dob()
    test_heuristic_skips_continue_when_school_empty()
    test_heuristic_picks_start_year()
    test_heuristic_does_not_give_up_on_cloudflare_dob()
