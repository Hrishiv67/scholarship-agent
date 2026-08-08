import re

from .classifier import ClassifiedOpportunity
from .dedup import DedupStore
from .email_applicator import send_application
from .essay_manager import queue_essay
from .form_filler import fill_and_submit
from .logger import RunLog, RunResult
from .profile_loader import Profile

_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def _extract_email_from_snippet(snippet: str) -> str | None:
    match = _EMAIL_PATTERN.search(snippet)
    if match:
        email = match.group()
        # Filter out the student's own email and common non-application emails
        skip = {"hrishiv14@gmail.com", "example@example.com", "info@example.com"}
        if email not in skip:
            return email
    return None


def dispatch(opp: ClassifiedOpportunity, profile: Profile, dedup_store: DedupStore,
             run_log: RunLog, dry_run: bool = False) -> RunResult:
    print(f"[applicator] [{opp.tier.upper()}] {opp.title[:60]}")

    result = RunResult(
        opportunity_id=opp.id,
        title=opp.title,
        url=opp.url,
        tier=opp.tier,
        outcome="skipped",
        application_type=opp.application_type,
        award_value=opp.award_value,
    )

    if opp.tier == "skip" or not opp.eligible:
        result.outcome = "skipped"
        result.notes = opp.reason
        dedup_store.mark(opp.url, opp.title, "skipped", opp.id,
                         opp.application_type, opp.tier, opp.award_value, opp.reason)
        return result

    if opp.tier == "essay_pending":
        queue_essay(opp)
        result.outcome = "essay_saved"
        dedup_store.mark(opp.url, opp.title, "essay_pending", opp.id,
                         opp.application_type, opp.tier, opp.award_value)
        return result

    if opp.tier == "semi_apply":
        # Pre-fill the form if possible, then queue for human
        fill_result = fill_and_submit(opp, profile, dry_run=True)  # Always dry-run for semi
        result.outcome = "semi_queued"
        result.notes = f"Pre-fill: {fill_result.fields_filled} fields"
        dedup_store.mark(opp.url, opp.title, "semi_apply_queued", opp.id,
                         opp.application_type, opp.tier, opp.award_value)
        return result

    # auto_apply — try email first, then form
    if opp.application_type == "email":
        to_email = _extract_email_from_snippet(opp.snippet) or _extract_email_from_snippet(opp.url)
        if not to_email:
            # Can't find email address — downgrade to semi
            result.outcome = "semi_queued"
            result.notes = "Email application but no address found in snippet"
            dedup_store.mark(opp.url, opp.title, "semi_apply_queued", opp.id,
                             "email", opp.tier, opp.award_value)
            return result

        success = send_application(opp, profile, to_email, dry_run=dry_run)
        result.outcome = "submitted" if success else "failed"
        result.notes = f"Email sent to {to_email}" if success else "SMTP failed"
        status = "submitted" if success else "semi_apply_queued"
        dedup_store.mark(opp.url, opp.title, status, opp.id,
                         "email", opp.tier, opp.award_value)
        return result

    # Portal account type — try session restore or auto-registration first
    if opp.application_type == "portal_account":
        from . import session_store
        if session_store.has_session(opp.url):
            print(f"[applicator] Restoring saved session for {opp.url}")
        else:
            print(f"[applicator] No session for portal — will attempt account creation during form fill")
        # Fall through to form_filler which handles both cases

    # Web form automation (also handles portal_account via session/registration)
    fill_result = fill_and_submit(opp, profile, dry_run=dry_run)

    if fill_result.downgraded:
        result.outcome = "semi_queued"
        result.notes = f"Downgraded: {fill_result.downgrade_reason}"
        dedup_store.mark(opp.url, opp.title, "semi_apply_queued", opp.id,
                         "web_form", opp.tier, opp.award_value, fill_result.downgrade_reason)
        return result

    result.outcome = "submitted" if fill_result.success else "failed"
    result.notes = f"Fields filled: {fill_result.fields_filled}, missed: {fill_result.fields_missed}"
    status = "submitted" if fill_result.success else "semi_apply_queued"
    dedup_store.mark(opp.url, opp.title, status, opp.id,
                     "web_form", opp.tier, opp.award_value)
    return result
