"""
LinkedIn Connector
==================
Uses Playwright to search LinkedIn Jobs and apply via Easy Apply.
LinkedIn has no public jobs API, so browser automation is required.

Targets "Easy Apply" jobs (multi-step modal) first.
Regular "Apply" jobs open external sites — those are saved to tracker
for manual follow-up unless the site is one we support.
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional
from connectors.base import BaseConnector

COOKIE_FILE = Path(__file__).parent.parent / "data" / "linkedin_cookies.json"


class LinkedInConnector(BaseConnector):
    platform_name = "linkedin"
    BASE_URL = "https://www.linkedin.com"

    def __init__(self, config: dict):
        super().__init__(config)
        self.headless = config.get("headless", True)
        self.easy_apply_only = config.get("easy_apply_only", True)
        self._logged_in = False
        self._pw = self._browser = self._context = self._page = None

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        keywords: str,
        location: Optional[str] = None,
        remote: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        self._start_browser()
        self._login()

        params = f"keywords={keywords.replace(' ', '%20')}"
        if location:
            params += f"&location={location.replace(' ', '%20')}"
        if remote:
            params += "&f_WT=2"          # LinkedIn remote filter code
        if self.easy_apply_only:
            params += "&f_LF=f_AL"       # Easy Apply filter

        url = f"{self.BASE_URL}/jobs/search/?{params}"
        self._page.goto(url, timeout=60000)
        self._page.wait_for_load_state("load", timeout=60000)
        time.sleep(5)

        jobs = []
        seen_urls = set()

        for _ in range(max(1, limit // 10)):          # paginate
            # LinkedIn uses multiple possible selectors for job cards
            self._page.wait_for_selector(
                "div.job-card-container, li.jobs-search-results__list-item, div.job-card-list",
                timeout=15000,
            )
            cards = self._page.query_selector_all(
                "div.job-card-container, li.jobs-search-results__list-item"
            )
            self.logger.info(f"[LinkedIn] Page has {len(cards)} job cards")
            if cards and not jobs:
                try:
                    sample = cards[0].inner_html()[:1000]
                    self.logger.debug(f"[LinkedIn] First card HTML sample: {sample}")
                except Exception:
                    pass
            for card in cards:
                if len(jobs) >= limit:
                    break
                job = self._parse_card(card)
                if job and job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    jobs.append(job)
            if len(jobs) >= limit:
                break
            # Try to go to next page
            next_btn = self._page.query_selector("button[aria-label='Next']")
            if next_btn:
                next_btn.click()
                self._page.wait_for_load_state("load", timeout=15000)
                time.sleep(3)
            else:
                break

        self._stop_browser()
        return jobs[:limit]

    # ── Apply ─────────────────────────────────────────────────────────────────

    def apply(self, job: dict) -> tuple[bool, str]:
        """Open the job URL in the user's default browser for manual apply."""
        import webbrowser
        webbrowser.open(job["url"])
        self.logger.info(f"[LinkedIn] Opened in browser: {job['title']} @ {job['company']}")
        return False, "MANUAL:Opened in browser — apply manually"

    # ── Private ───────────────────────────────────────────────────────────────

    def _login(self):
        if self._logged_in:
            return

        # Try loading saved cookies first
        if self._load_cookies():
            self._page.goto(f"{self.BASE_URL}/feed")
            self._page.wait_for_load_state("load", timeout=30000)
            if "/feed" in self._page.url:
                self._logged_in = True
                self.logger.info("[LinkedIn] Logged in via saved cookies")
                return
            self.logger.info("[LinkedIn] Saved cookies expired, logging in fresh...")

        self._page.goto(f"{self.BASE_URL}/login")
        self._page.wait_for_load_state("load", timeout=30000)

        # Try auto-fill, but if the form isn't found, let user log in manually
        try:
            self._page.wait_for_selector("#username", timeout=10000)
            self._page.fill("#username", self.config.get("email", ""))
            self._page.fill("#password", self.config.get("password", ""))
            self._page.click("button[type='submit']")
            self.logger.info("[LinkedIn] Credentials submitted, waiting for login...")
        except Exception:
            self.logger.info("[LinkedIn] Login form not found — please log in manually in the browser window")

        # Wait for the feed page (up to 2 minutes for manual login / CAPTCHA)
        try:
            self._page.wait_for_url("**/feed**", timeout=120000)
        except Exception:
            if "/login" in self._page.url or "/checkpoint" in self._page.url:
                self.logger.info("[LinkedIn] Still on login/checkpoint — waiting longer, please complete login...")
                self._page.wait_for_url("**/feed**", timeout=120000)

        self._save_cookies()
        self._logged_in = True
        self.logger.info("[LinkedIn] Logged in successfully (cookies saved for next run)")
        time.sleep(2)

    def _save_cookies(self):
        try:
            cookies = self._context.cookies()
            COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f)
        except Exception as e:
            self.logger.debug(f"Could not save cookies: {e}")

    def _load_cookies(self) -> bool:
        try:
            if COOKIE_FILE.exists():
                with open(COOKIE_FILE, "r") as f:
                    cookies = json.load(f)
                self._context.add_cookies(cookies)
                return True
        except Exception as e:
            self.logger.debug(f"Could not load cookies: {e}")
        return False

    def _parse_card(self, card) -> Optional[dict]:
        try:
            # LinkedIn changes class names often — try multiple selectors
            title_el = (
                card.query_selector("a.job-card-list__title")
                or card.query_selector("a.job-card-container__link")
                or card.query_selector("a[class*='job-card'] strong")
                or card.query_selector("a[href*='/jobs/view/']")
            )
            company_el = (
                card.query_selector("span.job-card-container__company-name")
                or card.query_selector("span.job-card-container__primary-description")
                or card.query_selector("div[class*='artdeco-entity-lockup__subtitle'] span")
                or card.query_selector("span[class*='company']")
            )
            location_el = (
                card.query_selector("li.job-card-container__metadata-item")
                or card.query_selector("span[class*='job-card-container__metadata-item']")
                or card.query_selector("div[class*='artdeco-entity-lockup__caption'] span")
                or card.query_selector("span[class*='location']")
            )

            # Get title — try inner_text of the link or its child elements
            title = ""
            url = ""
            if title_el:
                title = title_el.inner_text().strip()
                url = title_el.get_attribute("href") or ""
                # If the element itself isn't a link, look for a parent link
                if not url:
                    parent_link = card.query_selector("a[href*='/jobs/view/']")
                    if parent_link:
                        url = parent_link.get_attribute("href") or ""
            else:
                # Fallback: find any link to a job
                any_link = card.query_selector("a[href*='/jobs/view/']")
                if any_link:
                    title = any_link.inner_text().strip()
                    url = any_link.get_attribute("href") or ""

            if url and not url.startswith("http"):
                url = self.BASE_URL + url

            company = company_el.inner_text().strip() if company_el else ""
            location = location_el.inner_text().strip() if location_el else ""

            # Check for Easy Apply
            card_text = card.inner_text().lower()
            easy_apply = "easy apply" in card_text

            if not title or not url:
                self.logger.debug(f"Card skipped — title={title!r}, url={url!r}")
                return None

            job_id = hashlib.md5(url.encode()).hexdigest()[:8]
            return self._job_dict(
                id=job_id, title=title, company=company,
                location=location, url=url, easy_apply=easy_apply,
            )
        except Exception as e:
            self.logger.debug(f"Card parse error: {e}")
            return None

    def _fill_modal_step(self, job: dict):
        """Best-effort form filling for Easy Apply steps."""
        from config.config_loader import load_config
        from pathlib import Path
        profile = load_config()["profile"]
        page = self._page

        # Phone number
        for sel in ["input[id*='phone']", "input[name*='phone']"]:
            el = page.query_selector(sel)
            if el and not el.input_value():
                el.fill(profile.get("phone", ""))

        # Email
        for sel in ["input[id*='email']", "input[name*='email']", "input[type='email']"]:
            el = page.query_selector(sel)
            if el and not el.input_value():
                el.fill(profile.get("email", ""))

        # Resume upload — always attach if file input appears
        resume_input = page.query_selector("input[type='file']")
        if resume_input:
            resume_path = profile.get("resume_path", "")
            if resume_path:
                resolved = Path(resume_path).resolve()
                if resolved.exists():
                    resume_input.set_input_files(str(resolved))
                    self.logger.info(f"Uploaded resume: {resolved.name}")
                else:
                    self.logger.warning(f"Resume not found at {resolved}")

        # Cover letter text area — only fill if one was generated
        if job.get("cover_letter"):
            for sel in ["textarea[id*='cover']", "textarea[name*='cover']",
                        "div[data-placeholder*='cover']"]:
                el = page.query_selector(sel)
                if el:
                    el.fill(job["cover_letter"])
                    break

        # Name fields
        for sel in ["input[id*='firstName']", "input[name*='firstName']"]:
            el = page.query_selector(sel)
            if el and not el.input_value():
                name_parts = profile.get("name", "").split()
                el.fill(name_parts[0] if name_parts else "")
        for sel in ["input[id*='lastName']", "input[name*='lastName']"]:
            el = page.query_selector(sel)
            if el and not el.input_value():
                name_parts = profile.get("name", "").split()
                el.fill(name_parts[-1] if len(name_parts) > 1 else "")

        # Yes/No radio buttons — default to first option (usually "Yes")
        for radio in page.query_selector_all("fieldset input[type='radio']"):
            try:
                if not radio.is_checked():
                    siblings = radio.query_selector_all("xpath=../input[@type='radio']") or []
                    if not any(s.is_checked() for s in siblings):
                        radio.click()
                        break
            except Exception:
                pass

    def _start_browser(self):
        self._pw, self._browser, self._context = self._new_browser(self.headless)
        self._page = self._context.new_page()

    def _stop_browser(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._logged_in = False
        self._pw = self._browser = self._context = self._page = None
