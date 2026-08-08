# Scholarship & Internship Agent

Runs automatically Mon / Wed / Fri at 9 AM ET via GitHub Actions — no computer needed.

Finds and applies to paid internships, research programs, fly-in programs, and no-essay scholarships.

---

## What it does each run

1. Searches for new opportunities (Tavily, 15+ queries — RDU first, then national)
2. Classifies each one with Gemini AI — eligible? essay required? CAPTCHA present?
3. Auto-applies to anything it can (email applications, simple web forms)
4. Saves essay prompts to `outputs/essays_needed.md` for you to fill in
5. Emails a full digest to hrishiv14@gmail.com with results

---

## Folder structure

```
outputs/
  applications.md      Everything applied to — master log
  essays_needed.md     Essay prompts waiting for your response
  essay_responses/     Drop your completed essays here
  dedup.json           What's been seen — prevents duplicate applications

profile/
  profile.json         Your student data (used to fill all forms)
  cv_combined.txt      Combined CV

agent/                 All Python source code
.github/workflows/     GitHub Actions schedule
```

---

## How to respond to an essay prompt

When the agent finds something needing an essay, it saves it to `outputs/essays_needed.md` with an ID like `OPP-20270101-001`.

1. Open `outputs/essays_needed.md` — find the prompt
2. Write your response
3. Create `outputs/essay_responses/OPP-20270101-001.md` and paste your essay in
4. Commit and push
5. The next scheduled run picks it up and submits the application automatically

---

## How to trigger a manual run

1. Go to the **Actions** tab on GitHub
2. Click **Scholarship Agent** in the left sidebar
3. Click **Run workflow** → set `dry_run: false` → **Run workflow**

Set `dry_run: true` to test without submitting anything.

---

## Secrets (already configured in GitHub)

| Secret | Purpose |
|---|---|
| `GEMINI_API_KEY` | AI classification of opportunities |
| `TAVILY_API_KEY` | Web search for new opportunities |
| `GMAIL_ADDRESS` | Send application emails and digest |
| `GMAIL_APP_PASSWORD` | Gmail authentication |
| `PORTAL_PASSWORD` | Password used when creating accounts on scholarship portals |
