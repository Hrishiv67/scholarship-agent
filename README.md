# Scholarship & Internship Agent

Runs automatically every week via GitHub Actions — no computer needed.

Finds and applies to paid internships, research programs, apprenticeships, fly-in programs, and scholarships that build a strong college-application narrative. Elite programs are tracked and reminded, but left for you to apply to yourself.

---

## What it does each run

1. Searches for opportunities (Tavily queries + a curated program calendar + direct program pages), fetching real page content.
2. Classifies each one with the Anthropic Claude API — is it a real application, does it cost money, is it paid, does it need an essay.
3. Routes each opportunity:
   - **Elite** (Morehead-Cain, RSI, Clark Scholars, and the like) → tracked and reminded, **you apply yourself, no AI**.
   - **Everything else** → applies automatically: creates the account, confirms the email, fills your details, drafts any essay in your voice (fitted to the word/character limit), attaches your resume, and submits.
   - **Costs money** (application fee, tuition, pay-to-attend) → skipped. Money *to* you (stipends, wages, awards) is preferred and ranked first.
4. When something genuinely blocks it (CAPTCHA, "sign in with Google", a question it has no answer for), it does not stall silently — it records why and surfaces it in the weekly digest with a link so you can finish it.
5. Emails you a weekly digest: everything applied to, elite programs reserved for you, anything that needs you, and an **Upcoming Deadlines** board so nothing is ever missed.

There is no eligibility filtering — it applies broadly. It never fabricates facts and never marks something submitted that was not.

---

## Folder structure

```
outputs/
  applications.md         Everything applied to / tracked — master log
  program_calendar.json   Confirmed deadlines (refreshed monthly)
  CALENDAR.md             Human-readable deadline calendar
  my_status.json          You edit this to silence reminders (see below)
  dedup.json              What has been seen — prevents duplicate applications
  screenshots/            Proof of each submission

profile/
  profile.json            Your data (used to fill all forms), including guardians
  cv_combined.txt         Combined CV (a resume PDF is generated from this)
  writing_style.md        Your writing voice, used for all drafted prose
  documents/              Drop transcript.pdf / portfolio.pdf here for uploads

agent/                    Application pipeline (search → classify → apply → digest)
calendar_agent/           Deadline research (programs.json + monthly refresh)
.github/workflows/        Weekly apply run + monthly calendar refresh
```

---

## Silencing a reminder

When you have applied to (or want to ignore) a program yourself, add it to `outputs/my_status.json` keyed by its calendar slug:

```json
{ "morehead-cain": "applied", "some-other-program": "skip" }
```

The next digest drops it from the Upcoming Deadlines board.

---

## How to trigger a manual run

1. Go to the **Actions** tab on GitHub → **Scholarship Agent** → **Run workflow**.
2. Set `dry_run: true` to test (search + classify, no submissions) or `false` to run for real.

Refresh deadlines any time via the **Calendar Refresh** workflow (also runs monthly on its own).

---

## Secrets (configured in GitHub)

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | AI classification and in-voice essay drafting |
| `TAVILY_API_KEY` | Web search for new opportunities |
| `GMAIL_ADDRESS` | Send application emails, the digest, and read verification emails |
| `GMAIL_APP_PASSWORD` | Gmail authentication (SMTP + IMAP) |
| `PORTAL_PASSWORD` | Password used when creating accounts on portals |
