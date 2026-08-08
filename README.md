# Scholarship & Internship Agent

Autonomous agent that searches for and applies to paid internships, research programs, fly-in programs, and no-essay scholarships on a schedule — runs on GitHub Actions with no computer required.

**Schedule:** Monday / Wednesday / Friday at 9:00 AM ET, automatically.

---

## How It Works

Each run:
1. Searches for new opportunities (Tavily web search, 15+ queries)
2. Classifies each one — eligible? essay required? account needed?
3. Auto-applies to anything it can (email applications, simple web forms)
4. Saves essay prompts to `data/essays_needed.md` for you to fill in
5. Emails a digest to hrishiv14@gmail.com with everything it did

---

## Folder Structure

```
agent/              All Python source code
data/
  applications.md   Master log of everything applied to
  essays_needed.md  Essay prompts waiting for your response
  essay_responses/  Drop your essay files here (see below)
  dedup.json        Tracks what's been seen — prevents duplicate applications
  run_logs/         Per-run JSON logs
profile/
  profile.json      Your student profile (used to fill all forms)
  cv_combined.txt   Combined professional CV
.github/workflows/  GitHub Actions schedule
```

---

## How to Respond to an Essay Prompt

When the agent finds an opportunity that needs an essay, it saves it to `data/essays_needed.md` with an ID like `OPP-20270101-001`.

To complete that application:
1. Open `data/essays_needed.md` on GitHub — find the prompt
2. Write your essay response
3. Create a new file: `data/essay_responses/OPP-20270101-001.md`
4. Paste your essay into that file and commit + push
5. The **next scheduled run** will pick it up and finish the application automatically

---

## How to Trigger a Manual Run

1. Go to the **Actions** tab on GitHub
2. Click **Scholarship Agent** in the left sidebar
3. Click **Run workflow** → set `dry_run: false` → **Run workflow**

To test without submitting anything, set `dry_run: true`.

---

## Secrets Required (already configured)

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | AI classification of opportunities |
| `TAVILY_API_KEY` | Web search for new opportunities |
| `GMAIL_ADDRESS` | Send application emails + digest |
| `GMAIL_APP_PASSWORD` | Gmail authentication |
| `PORTAL_PASSWORD` | Password used when creating accounts on scholarship portals |
