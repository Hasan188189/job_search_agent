# Job Search Agent - User Guide

A command-line tool that searches for jobs across **LinkedIn** and **Naukri**, collects all job data, and saves everything into an Excel spreadsheet for you to review and apply manually.

---

## Setup (One-Time)

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure your profile

Open `config/settings.yaml` and fill in:

- **Your profile** — name, email, phone, skills, years of experience
- **Resume path** — full path to your resume PDF (use single quotes for Windows paths)
- **Platform credentials** — email and password for LinkedIn and/or Naukri
- **Set `enabled: true`** for platforms you want to search

Example resume path (Windows):
```yaml
resume_path: 'C:\Users\YourName\Documents\resume.pdf'
```

### 3. Platform notes

| Platform | First Run | After First Run |
|----------|-----------|-----------------|
| LinkedIn | Set `headless: false`. A browser opens — log in manually if CAPTCHA appears. | Cookies are saved, login is automatic. |
| Naukri | Set `headless: false`. Log in if OTP is required. | Cookies are saved, login is automatic. |

After the first successful login, you can set `headless: true` to run without a visible browser.

---

## Usage

### Search and collect jobs

```bash
# Search both platforms
python agent.py run -k "Design Verification Engineer" -l "Bangalore"

# Search with specific skills
python agent.py run -k "VLSI Verification UVM SystemVerilog" -l "Bangalore"

# Search only one platform
python agent.py run -k "ASIC Verification" -l "Hyderabad" --platforms naukri

# Limit results per platform
python agent.py run -k "Verification Engineer" -l "Bangalore" --limit 20

# Remote jobs only
python agent.py run -k "Design Verification" --remote
```

### View collected jobs

```bash
python agent.py status
```

### Export to Excel

```bash
# Default location: data/applications.xlsx
python agent.py export

# Custom output path
python agent.py export -o "C:\Users\YourName\Desktop\jobs.xlsx"
```

### Search without saving (preview only)

```bash
python agent.py search -k "Verification Engineer" -l "Bangalore" --platforms linkedin
```

---

## Output

The spreadsheet (`data/applications.xlsx`) contains:

| Column | Description |
|--------|-------------|
| S.No | Serial number |
| Platform | linkedin or naukri |
| Job Title | Role title |
| Company | Company name |
| Location | City / remote |
| Description | Job description snippet |
| Match Score | How well the job matches your profile (0-100%) |
| Job URL | Direct link to apply |
| Found On | Date the job was collected |

Jobs are sorted by match score (highest first). The spreadsheet has filters enabled so you can filter by platform, company, location, etc.

---

## How It Works

1. **Search** — The agent opens a browser, logs into LinkedIn/Naukri, and scrapes job listings
2. **Score** — Each job is scored against your profile (skills, title, location match)
3. **Store** — Jobs are saved to a local SQLite database (no duplicates on re-runs)
4. **Export** — All data is exported to a formatted Excel spreadsheet

Running the agent multiple times with different keywords **adds new jobs** without duplicating existing ones.

---

## Configuration Reference

### Filters (`config/settings.yaml`)

```yaml
filters:
  exclude_companies:    # Skip these employers
    - "TCS"
    - "Infosys"
  exclude_keywords:     # Skip jobs containing these words
    - "10+ years"
    - "unpaid"
  min_match_score: 0.3  # Minimum match score (0.0 to 1.0)
```

### Environment Variables (optional, override settings.yaml)

```bash
export LINKEDIN_EMAIL="you@email.com"
export LINKEDIN_PASSWORD="..."
export NAUKRI_EMAIL="you@email.com"
export NAUKRI_PASSWORD="..."
```

---

## Files Generated (not committed to git)

| File | Purpose |
|------|---------|
| `data/applications.db` | SQLite database with all collected jobs |
| `data/applications.xlsx` | Excel spreadsheet export |
| `data/linkedin_cookies.json` | Saved login session (auto-login on next run) |
| `data/naukri_cookies.json` | Saved login session (auto-login on next run) |
| `logs/agent.log` | Detailed debug log |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Login timeout | Set `headless: false` in settings.yaml, log in manually in the browser |
| CAPTCHA on LinkedIn | Set `headless: false`, solve CAPTCHA manually, cookies are saved for next time |
| Excel file locked error | Close the spreadsheet in Excel before running the agent |
| 0 jobs found | Try broader keywords, check if platform is `enabled: true` in config |
| Resume path error | Use single quotes and full path: `'C:\Users\...\resume.pdf'` |
| Cookies expired | Delete the cookies file in `data/`, run again with `headless: false` |
