# Program Research Calendar

Deep-researches AI, Engineering, and Business opportunities for high school students. Reads **official program pages** (plus apply/deadline subpages), confirms dates when stated, and publishes a live calendar website.

**No auto-apply.** This tool finds and tracks — you apply yourself.

---

## Live site (bookmark this)

**https://hrishiv67.github.io/scholarship-agent/**

- **Calendar view** — month grid with deadlines
- **All programs** — searchable cards by track
- **Subscribe** — Google Calendar / Apple Calendar / `.ics` download (confirmed dates only)

Updates every Monday via GitHub Actions, or run manually anytime.

---

## What each run does

1. **Discover** — Tavily advanced search across `.edu` / `.gov` for new programs (AI, Engineering, Business)
2. **Deep research** — fetches each official page + linked apply/deadline pages; Claude extracts facts
3. **Date honesty** — deadlines only when the page states a 2026–2028 date with a verbatim quote
4. **Filter** — seniors-only → track for fall 2027; skip women-only, need-only, FRC/FTC-only
5. **Publish** — commits results and deploys the website automatically

---

## Run it

**GitHub:** Actions → **Calendar Refresh** → Run workflow  
(Optional: set `research_limit` to cap how many programs to re-verify; `0` = all)

**Locally** (`.env` with `ANTHROPIC_API_KEY` + `TAVILY_API_KEY`):

```bash
pip install -r requirements.txt
python -m calendar_agent
```

---

## One-time Pages setup (if site 404s)

1. [Settings → Pages](https://github.com/Hrishiv67/scholarship-agent/settings/pages) → Source: **GitHub Actions**
2. Run **Calendar Refresh** once — it deploys the site at the end

---

## Outputs

| File | What it is |
|------|------------|
| `docs/index.html` | Live website |
| `docs/calendar.ics` | Subscribe in Google/Apple Calendar |
| `outputs/program_calendar.json` | Full data |
| `outputs/program_research/*.md` | Per-program research notes |
| `outputs/CALENDAR.md` | Markdown fallback |

---

## Secrets

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Read and extract from official pages |
| `TAVILY_API_KEY` | Discover new program pages |
| `GMAIL_ADDRESS` | Optional weekly email summary |
| `GMAIL_APP_PASSWORD` | Optional weekly email summary |

---

## Repo layout

```
calendar_agent/     Research pipeline (discover → scrape → extract → render)
docs/               Deployed website (GitHub Pages)
outputs/            Generated calendar data + research notes
profile/            Student profile for eligibility context
.github/workflows/  Weekly research + deploy
```
