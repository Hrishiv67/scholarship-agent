import re

from .classifier import ClassifiedOpportunity
from .dedup import DedupStore
from .email_applicator import send_application
from .form_filler import fill_and_submit
from .logger import RunLog, RunResult
from .profile_loader import Profile
from . import accounts, packet

_RETRY_SKIP = ("instagram.com", "facebook.com", "twitter.com", "x.com", "linkedin.com")
_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')


def _extract_email(text: str) -> str | None:
    if not text:
        return None
    match = _EMAIL_PATTERN.search(text)
    if not match:
        return None
    email = match.group()
    skip = {"hrishiv14@gmail.com", "example@example.com", "info@example.com"}
    return email if email not in skip else None


def _attach_packet(result: RunResult, opp: ClassifiedOpportunity, profile: Profile,
                   dry_run: bool) -> None:
    """Write a copy-paste packet (login + fields + in-voice essays) so a blocked
    application is not work the user has to redo. Non-dry only."""
    if dry_run:
        return
    try:
        login_note = (
            f"Log in as {profile.personal.email} with your portal password. "
            f"The agent creates the account and solves CAPTCHA when it can."
        )
        packet.write(opp, profile, login_note)
        result.notes = f"{result.notes} | Packet: outputs/application_packets/{opp.id}.md"
    except Exception as e:
        print(f"[applicator] packet generation failed: {e}")


def retries_from_store(dedup_store: DedupStore, already: list[ClassifiedOpportunity],
                       limit: int = 30) -> list[ClassifiedOpportunity]:
    """Re-queue unfinished applications that did not come back in this week's search."""
    seen = {(o.url, o.title.lower().strip()) for o in already}
    out: list[ClassifiedOpportunity] = []
    for entry in dedup_store.pending():
        key = (entry.url, (entry.title or "").lower().strip())
        if key in seen:
            continue
        if entry.status == "skipped":
            continue
        if any(b in (entry.url or "").lower() for b in _RETRY_SKIP):
            continue
        out.append(ClassifiedOpportunity(
            id=entry.id,
            title=entry.title,
            url=entry.url,
            snippet=entry.notes or "",
            route="auto_submit",
            application_type=entry.application_type or "web_form",
            award_value=entry.award_value or "",
            reason="retry unfinished application",
        ))
        if len(out) >= limit:
            break
    if out:
        print(f"[applicator] Retrying {len(out)} unfinished application(s)")
    return out


def dispatch(opp: ClassifiedOpportunity, profile: Profile, dedup_store: DedupStore,
             run_log: RunLog, dry_run: bool = False) -> RunResult:
    print(f"[applicator] [{opp.route.upper()}] {opp.title[:60]}")

    result = RunResult(
        opportunity_id=opp.id, title=opp.title, url=opp.url, tier=opp.route,
        outcome="tracked", application_type=opp.application_type,
        award_value=opp.award_value, deadline=opp.deadline,
    )

    # ── skip ──────────────────────────────────────────────────────────────────
    if opp.route == "skip":
        result.outcome = "skipped"
        result.notes = opp.reason
        dedup_store.mark(opp.url, opp.title, "skipped", opp.id,
                         opp.application_type, opp.route, opp.award_value, opp.reason)
        return result

    # ── elite programs are applied to automatically (no manual holdback) ──────
    if opp.route == "yours_manual":
        opp.route = "auto_submit"

    # Previously-tracked items are attempted, not parked.

    # ── auto_submit: attempt end-to-end; if blocked, flag (never silent) ───────
    # For email-type applications, prefer the address the classifier pulled from the
    # full page (the snippet often does not contain it), then fall back to regex.
    to_email = None
    if opp.application_type == "email":
        if opp.contact_email and _EMAIL_PATTERN.fullmatch(opp.contact_email):
            to_email = opp.contact_email
        else:
            to_email = _extract_email(opp.snippet) or _extract_email(opp.url)

    if to_email:
        success = send_application(opp, profile, to_email, dry_run=dry_run)
        result.outcome = "submitted" if success else "tracked"
        result.notes = (f"Email sent to {to_email}" if success
                        else f"Email send failed to {to_email} - flagged for you")
        if not success:
            _attach_packet(result, opp, profile, dry_run)
        dedup_store.mark(opp.url, opp.title,
                         "submitted" if success else "tracked", opp.id,
                         "email", opp.route, opp.award_value, result.notes)
        return result

    # Web form / portal (form_filler drafts any required writing in-voice, uploads
    # resume/docs, creates an account + confirms email if needed, then submits).
    fill_result = fill_and_submit(opp, profile, dry_run=dry_run)

    if fill_result.downgraded:
        # A real blocker (CAPTCHA / OAuth / no fields / account-required-fail).
        # Track + flag with the reason so it surfaces in the weekly digest - never
        # silent, but NOT an immediate per-item email (that was just noise).
        reason = fill_result.downgrade_reason or ""
        result.outcome = "tracked"
        result.notes = f"Needs you: {reason}"
        # If it stalled on a signup/CAPTCHA, log the portal to the accounts registry
        # as a manual signup to do (the agent takes over once the account exists).
        if any(k in reason.lower() for k in ("oauth", "google sign", "sign in with")):
            accounts.record(opp.title, opp.url, profile.personal.email, "you (manual)",
                            "needs signup", reason)
        _attach_packet(result, opp, profile, dry_run)
        dedup_store.mark(opp.url, opp.title, "tracked", opp.id,
                         "web_form", opp.route, opp.award_value, result.notes)
        return result

    if dry_run:
        result.outcome = "tracked"
        result.notes = f"DRY_RUN: would submit ({fill_result.fields_filled} fields pre-filled)"
        return result

    result.outcome = "submitted" if fill_result.success else "tracked"
    if fill_result.success:
        conf = fill_result.confirmation or "thank-you / received page"
        result.notes = (
            f"SUBMITTED and confirmed ({conf}). "
            f"Fields filled: {fill_result.fields_filled}, missed: {fill_result.fields_missed}"
        )
    else:
        result.notes = "Submit not confirmed - flagged for you to finish"
    if not fill_result.success:
        _attach_packet(result, opp, profile, dry_run)
    dedup_store.mark(opp.url, opp.title,
                     "submitted" if fill_result.success else "tracked", opp.id,
                     "web_form", opp.route, opp.award_value, result.notes)
    return result
