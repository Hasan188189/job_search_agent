# 🤖 Job Application Agent

An autonomous agent that searches for jobs across **LinkedIn, Indeed, and Naukri**, generates AI-tailored cover letters using Claude, auto-applies, and tracks every application in a local database.

---

## Features

| Feature | Detail |
|---|---|
| 🔍 Multi-platform search | LinkedIn, Indeed, Naukri (pluggable) |
| 🧠 AI cover letters | Claude generates a tailored letter per job |
| 📊 Match scoring | Keyword-based fit score (0–1) filters weak matches |
| 🖱️ Auto-apply | Browser automation via Playwright |
| 📋 Tracker | SQLite DB with status: discovered → applied → offer |
| 🔒 Credential safety | Stored locally in YAML / env vars only |
| 🛡️ Safety caps | Max applications per run, dry-run mode |

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure your profile

Edit `config/settings.yaml`:
- Fill in your name, email, skills, resume path
- Add LinkedIn / Indeed / Naukri credentials
- Set your Anthropic API key (or export it as `ANTHROPIC_API_KEY`)

### 3. Run

```bash
# Search only (preview results)
python agent.py search -k "Python Developer" -l "Bangalore" --remote

# Full auto: search + apply + track
python agent.py run -k "Senior Engineer" -l "Bangalore" --limit 10

# Dry run (no actual applications submitted)
python agent.py run -k "Data Scientist" --dry-run

# Apply to a specific job by ID
python agent.py apply --job-id a1b2c3d4

# View tracker dashboard
python agent.py status
```

---

## Project Structure

```
job_agent/
├── agent.py                  # CLI entrypoint
├── requirements.txt
├── config/
│   ├── settings.yaml         # ← Edit this first!
│   └── config_loader.py
├── core/
│   ├── orchestrator.py       # Pipeline coordinator
│   ├── ai_writer.py          # Claude cover letter generator
│   ├── scorer.py             # Job match scorer
│   ├── tracker.py            # SQLite application tracker
│   └── logger.py
├── connectors/
│   ├── base.py               # Abstract base connector
│   ├── linkedin.py           # LinkedIn (Easy Apply)
│   ├── indeed.py             # Indeed (API + browser)
│   └── naukri.py             # Naukri.com
├── data/
│   ├── resume.pdf            # ← Place your resume here
│   └── applications.db       # Auto-created SQLite DB
└── logs/
    └── agent.log
```

---

## Adding a New Platform

1. Create `connectors/yourplatform.py`
2. Extend `BaseConnector` and implement `search()` and `apply()`
3. Add it to `config/settings.yaml` under `platforms:`
4. Register it in `core/orchestrator.py` in `self._connectors`

---

## Environment Variables (override settings.yaml)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export LINKEDIN_EMAIL="you@email.com"
export LINKEDIN_PASSWORD="..."
export INDEED_EMAIL="you@email.com"
export INDEED_PASSWORD="..."
export NAUKRI_EMAIL="you@email.com"
export NAUKRI_PASSWORD="..."
```

---

## Important Notes

- **LinkedIn**: Uses Playwright browser automation. Easy Apply jobs only by default.
- **Indeed**: Uses Publisher XML API if `publisher_id` is set; falls back to browser scraping.
- **Naukri**: Browser automation. Profile-based one-click apply targeted.
- **CAPTCHA**: If platforms show CAPTCHAs, set `headless: false` in config to solve them manually on first run. Cookies are reused afterward.
- **Rate limiting**: The agent adds delays between actions to stay within reasonable usage. Don't set `limit` too high in one run.
- **Terms of Service**: Check each platform's ToS before using automated tooling.

---

## Tracker Status Flow

```
discovered → applied → interviewing → offer
                   ↘ rejected
                   ↘ error
```

Update status manually if needed:
```python
from core.tracker import Tracker
t = Tracker()
t.update_status("a1b2c3d4", "interviewing", notes="Phone screen scheduled Mon 10am")
```
