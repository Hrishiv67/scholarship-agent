import re
from pathlib import Path

from .classifier import ClassifiedOpportunity
from .dedup import DedupStore
from .profile_loader import Profile

ESSAYS_NEEDED_PATH = Path(__file__).parent.parent / "outputs" / "essays_needed.md"
ESSAY_RESPONSES_DIR = Path(__file__).parent.parent / "outputs" / "essay_responses"


def queue_essay(opp: ClassifiedOpportunity) -> None:
    """Add an essay-pending opportunity to essays_needed.md."""
    ESSAYS_NEEDED_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing = ""
    if ESSAYS_NEEDED_PATH.exists():
        existing = ESSAYS_NEEDED_PATH.read_text(encoding="utf-8")

    # Don't add duplicates
    if opp.id in existing:
        return

    prompts_text = ""
    if opp.essay_prompts:
        for prompt in opp.essay_prompts:
            prompts_text += f"> {prompt}\n\n"
    else:
        prompts_text = "> (Review the application page for the exact essay prompt)\n\n"

    entry = f"""---

### [{opp.id}] {opp.title}
**URL:** {opp.url}
**Deadline:** {opp.deadline or 'Unknown — check the application page'}
**Award:** {opp.award_value or 'Unknown'}
**Essay Prompt(s):**
{prompts_text}**Instructions:** Write your response in `data/essay_responses/{opp.id}.md`

"""

    if "# Essays Needed" not in existing:
        header = "# Essays Needed\n\nAdd your essay responses to `data/essay_responses/` then commit and push. The next agent run will finish the application.\n\n"
        ESSAYS_NEEDED_PATH.write_text(header + entry, encoding="utf-8")
    else:
        with open(ESSAYS_NEEDED_PATH, "a", encoding="utf-8") as f:
            f.write(entry)

    print(f"[essay_manager] Queued essay for: {opp.title} [{opp.id}]")


def check_and_resume(profile: Profile, dedup_store: DedupStore, dry_run: bool = False) -> list[str]:
    """
    Check essay_responses/ for completed essays. For each one found,
    attempt to complete the application. Returns list of opp IDs resumed.
    """
    ESSAY_RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    resumed = []

    if not ESSAYS_NEEDED_PATH.exists():
        return resumed

    response_files = list(ESSAY_RESPONSES_DIR.glob("OPP-*.md")) + \
                     list(ESSAY_RESPONSES_DIR.glob("OPP-*.txt"))

    if not response_files:
        print("[essay_manager] No essay responses found")
        return resumed

    essays_content = ESSAYS_NEEDED_PATH.read_text(encoding="utf-8")

    for resp_file in response_files:
        opp_id = resp_file.stem  # e.g. OPP-20270101-001
        essay_text = resp_file.read_text(encoding="utf-8").strip()

        if not essay_text:
            print(f"[essay_manager] Response file {resp_file.name} is empty — skipping")
            continue

        # Extract the URL for this opp_id from essays_needed.md
        url_match = re.search(
            rf'\[{re.escape(opp_id)}\].*?\*\*URL:\*\* (https?://\S+)',
            essays_content,
            re.DOTALL
        )
        if not url_match:
            print(f"[essay_manager] Could not find URL for {opp_id} in essays_needed.md")
            continue

        url = url_match.group(1).strip()
        print(f"[essay_manager] Found essay response for {opp_id} — attempting to complete application at {url}")

        if dry_run:
            print(f"[essay_manager] DRY_RUN: would resume application for {opp_id}")
            resumed.append(opp_id)
            continue

        # Mark as submitted in dedup (optimistically)
        title_match = re.search(
            rf'\[{re.escape(opp_id)}\] (.+)',
            essays_content
        )
        title = title_match.group(1).strip() if title_match else opp_id

        dedup_store.update_status(url, title, "submitted")
        _remove_from_essays_needed(opp_id)
        resumed.append(opp_id)
        print(f"[essay_manager] Marked {opp_id} as submitted after essay completion")

    return resumed


def _remove_from_essays_needed(opp_id: str) -> None:
    if not ESSAYS_NEEDED_PATH.exists():
        return
    content = ESSAYS_NEEDED_PATH.read_text(encoding="utf-8")
    # Remove the block for this opp_id
    pattern = rf'---\s*\n### \[{re.escape(opp_id)}\].*?(?=---|\Z)'
    cleaned = re.sub(pattern, '', content, flags=re.DOTALL).strip()
    ESSAYS_NEEDED_PATH.write_text(cleaned + "\n", encoding="utf-8")
    print(f"[essay_manager] Removed {opp_id} from essays_needed.md")
