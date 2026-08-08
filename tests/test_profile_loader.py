import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.profile_loader import load


def test_profile_loads():
    profile = load()
    assert profile.personal.first_name == "Hrishiv"
    assert profile.personal.email == "hrishiv14@gmail.com"
    assert profile.academic.gpa_weighted == 4.696
    assert profile.academic.class_rank == 7
    assert len(profile.activities) >= 5
    assert len(profile.research) >= 2
    assert len(profile.publications) >= 1
    print("PASS: Profile loaded and validated successfully")
    print(f"  Name: {profile.personal.full_name}")
    print(f"  GPA: {profile.academic.gpa_weighted}W / {profile.academic.gpa_unweighted}UW")
    print(f"  Activities: {len(profile.activities)}")
    print(f"  Research: {len(profile.research)}")


if __name__ == "__main__":
    test_profile_loads()
