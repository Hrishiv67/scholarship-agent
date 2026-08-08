import json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional


class Address(BaseModel):
    line1: str
    line2: str = ""
    city: str
    state: str
    state_full: str
    zip: str
    country: str


class Personal(BaseModel):
    first_name: str
    last_name: str
    full_name: str
    preferred_name: str
    email: str
    phone: str
    phone_formatted: str
    date_of_birth: str = ""
    gender: str = ""
    ethnicity: str = ""
    race: str = ""
    citizenship: str = ""
    address: Address
    linkedin: str = ""
    website: str = ""


class DualEnrollment(BaseModel):
    school: str
    gpa: float
    degree_pursuing: str
    expected_completion: str = ""


class Academic(BaseModel):
    current_school: str
    school_address: str = ""
    school_type: str = ""
    graduation_year: int
    current_grade: int
    grade_level_text: str = ""
    gpa_weighted: float
    gpa_unweighted: float
    gpa_scale_weighted: float = 5.0
    gpa_scale_unweighted: float = 4.0
    class_rank: int
    class_size: int
    sat_total: Optional[int] = None
    sat_math: Optional[int] = None
    sat_ebrw: Optional[int] = None
    act_composite: Optional[int] = None
    dual_enrollment: Optional[DualEnrollment] = None
    ap_courses: list[str] = []
    certifications: list[str] = []
    intended_major: str = ""
    intended_college_grad_year: Optional[int] = None


class Activity(BaseModel):
    name: str
    role: str
    years: str
    hours_per_week: int = 0
    description: str
    category: str = ""


class Research(BaseModel):
    institution: str
    role: str
    dates: str
    description: str
    pi_name: str = ""
    department: str = ""


class Publication(BaseModel):
    title: str
    doi: str = ""
    url: str = ""
    year: int
    venue: str = ""


class WorkExperience(BaseModel):
    employer: str
    role: str
    dates: str
    description: str


class Skills(BaseModel):
    programming: list[str] = []
    engineering: list[str] = []
    tools: list[str] = []
    languages: list[str] = []
    research: list[str] = []
    business: list[str] = []


class Preferences(BaseModel):
    opportunity_types: list[str] = []
    location_preference: list[str] = []
    available_start: str = ""
    field_interests: list[str] = []
    max_application_time_minutes: int = 30


class EssaySnippets(BaseModel):
    bio_150: str = Field("", alias="150_word_bio")
    why_stem: str = ""
    leadership: str = ""
    community_impact: str = ""

    model_config = {"populate_by_name": True}


class Profile(BaseModel):
    personal: Personal
    academic: Academic
    activities: list[Activity] = []
    research: list[Research] = []
    publications: list[Publication] = []
    work_experience: list[WorkExperience] = []
    awards: list[str] = []
    skills: Skills
    preferences: Preferences
    essay_snippets: EssaySnippets


def load(path: str | Path | None = None) -> Profile:
    if path is None:
        path = Path(__file__).parent.parent / "profile" / "profile.json"
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"profile.json not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return Profile.model_validate(data)
