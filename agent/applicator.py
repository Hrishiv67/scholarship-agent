import re

from .classifier import ClassifiedOpportunity
from .dedup import DedupStore
from .email_applicator import send_application
from .form_filler import fill_and_submit
from .logger import RunLog, RunResult
from .profile_loader import Profile
from . import accounts, packet

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
        login_note = (f"Log in as {profile.personal.email} with your portal password. "
                      f"If there is no account yet, sign up at the link above (one-time "
                      f"CAPTCHA), then paste the answers below.")
        packet.write(opp, profile, login_note)
        result.notes = f"{result.notes} | Packet: outputs/application_packets/{opp.id}.md"
    except Exception as e:
        print(f"[applicator] packet generation failed: {e}")


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

    # ── elite: reserved for the user, no AI ────────────────────────────────────
    if opp.route == "yours_manual":
        result.outcome = "yours_manual"
        result.notes = "Elite - apply yourself. Tracked for deadline reminders."
        dedup_store.mark(opp.url, opp.title, "yours_manual", opp.id,
                         opp.application_type, opp.route, opp.award_value, opp.reason)
        return result

    # ── track_remind: eligible but not auto-completable / far off ──────────────
    if opp.route == "track_remind":
        result.outcome = "tracked"
        result.notes = opp.reason or "Tracked for reminders."
        _attach_packet(result, opp, profile, dry_run)
        dedup_store.mark(opp.url, opp.title, "tracked", opp.id,
                         opp.application_type, opp.route, opp.award_value, result.notes)
        return result

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
        if any(k in reason.lower() for k in ("captcha", "cloudflare", "oauth", "sign in", "login", "account")):
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
    result.notes = (f"Fields filled: {fill_result.fields_filled}, missed: {fill_result.fields_missed}"
                    if fill_result.success
                    else "Submit not confirmed - flagged for you to finish")
    if not fill_result.success:
        _attach_packet(result, opp, profile, dry_run)
    dedup_store.mark(opp.url, opp.title,
                     "submitted" if fill_result.success else "tracked", opp.id,
                     "web_form", opp.route, opp.award_value, result.notes)
    return result
