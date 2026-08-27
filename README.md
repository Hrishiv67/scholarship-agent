# Program calendar (AI / Engineering / Business)

Runs on GitHub Actions every Monday. It finds high-school programs, reads the **official page**, and files them on a due-date calendar. It does **not** submit applications.

Tracks: **AI**, **Engineering**, **Business**. Generic merit scholarships that are not field programs are listed separately.

---

## What each run does

1. Searches (Tavily) for new official program pages in the three tracks.
2. Fetches each program page and extracts a deadline **only if the page states a 2026–2028 date**. Typical months from last year are not dates.
3. Skips or files aside programs that still fail the standing rules: seniors-only (track for fall 2027), women-only, need-only, FRC/FTC-only. Date of birth is unknown and is never invented.
4. Writes:
   - `outputs/CALENDAR.md` — human calendar by track, then due date
   - `outputs/program_calendar.json` — machine copy
   - `outputs/calendar.ics` — **confirmed** deadlines only (safe to import)
5. Commits those files (rebase-then-push so the job is not rejected) and emails a short count if Gmail secrets are set.

---

## How to run it

1. GitHub → **Actions** → **Calendar Refresh** → **Run workflow**.
2. Optional: lower `research_limit` for a shorter run (default 40 pages).

The job uses these secrets: `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, and optionally `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`.

Locally (same keys in `.env`):

```
python -m calendar_agent
```

---

## How to read the calendar

- **✅ confirmed** — the official page quoted a date for this cycle.
- **— no date on page** — do not guess; it will be retried next week.
- Import `outputs/calendar.ics` into Google Calendar. Unconfirmed dates are never added as events.

---

## Folder structure

```
calendar_agent/           Discover + confirm dates (this is the product)
outputs/CALENDAR.md       Calendar by AI / Engineering / Business
outputs/calendar.ics      Confirmed deadlines only
outputs/program_calendar.json
profile/profile.json      Student facts used for eligibility notes
.github/workflows/        Weekly calendar job + tests
```

---

## Secrets

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Read official pages and extract stated dates |
| `TAVILY_API_KEY` | Find new program pages |
| `GMAIL_ADDRESS` | Optional calendar email |
| `GMAIL_APP_PASSWORD` | Optional calendar email |
