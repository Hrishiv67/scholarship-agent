# Program Research Calendar

Deep-researches AI, Engineering, and Business opportunities for high school students. Reads **official program pages** (plus apply/deadline subpages), confirms dates when stated, and publishes a live calendar website.

**No auto-apply.** This tool finds and tracks — you apply yourself.

---

## Live site (free hosting)

GitHub Pages on a **private** repo requires a paid GitHub plan. Use one of these **free** options instead:

### Option A — Netlify (recommended, keep repo private)

1. Sign up at [netlify.com](https://www.netlify.com/) (free)
2. **Add new site** → **Import an existing project** → connect GitHub → pick this repo
3. Build settings: **Build command** = leave empty · **Publish directory** = `docs`
4. Deploy → you get a URL like `https://your-name.netlify.app`
5. Run **Calendar Refresh** on GitHub — each run updates `docs/` and Netlify auto-redeploys

### Option B — GitHub Pages (free if repo is public)

1. Repo **Settings → General → Danger zone → Change visibility → Public**  
   (No API keys are in the repo — only calendar data.)
2. **Settings → Pages** → Source: **Deploy from a branch** → branch `master` → folder `/docs`
3. Live at `https://hrishiv67.github.io/scholarship-agent/`

### Option C — Open locally (always works)

After a refresh, open `docs/index.html` in your browser.

---

## What each run does

1. **Discover** — Tavily advanced search across `.edu` / `.gov` for new programs
2. **Deep research** — official page + apply/deadline subpages; Claude extracts facts
3. **Date honesty** — deadlines only when the page states a 2026–2028 date with a quote
4. **Filter** — seniors-only → track for fall 2027; skip women-only, need-only, FRC/FTC-only
5. **Publish** — commits `docs/index.html` + `docs/calendar.ics` (your host redeploys)

---

## Run it

**GitHub:** Actions → **Calendar Refresh** → Run workflow  
(`research_limit` = `0` researches all programs; raise it for a shorter run)

**Locally** (`.env` with `ANTHROPIC_API_KEY` + `TAVILY_API_KEY`):

```bash
pip install -r requirements.txt
python -m calendar_agent
```

---

## Outputs

| File | What it is |
|------|------------|
| `docs/index.html` | Calendar website (what Netlify/Pages serves) |
| `docs/calendar.ics` | Subscribe in Google/Apple Calendar |
| `outputs/program_calendar.json` | Full data |
| `outputs/program_research/*.md` | Per-program research notes |

---

## Secrets (GitHub Actions only)

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Read and extract from official pages |
| `TAVILY_API_KEY` | Discover new program pages |
| `GMAIL_ADDRESS` | Optional weekly email summary |
| `GMAIL_APP_PASSWORD` | Optional weekly email summary |

---

## Repo layout

```
calendar_agent/     Research pipeline
docs/               Website + .ics (deploy this folder)
outputs/            Generated data + research notes
profile/            Student profile for eligibility context
.github/workflows/  Weekly research job
```
