"""
Naukri Connector
================
Playwright-based connector for Naukri.com — India's largest job board.
Searches jobs and applies using Naukri's one-click apply where available.
"""

import json
import time
import hashlib
from pathlib import Path
from typing import Optional
from connectors.base import BaseConnector

COOKIE_FILE = Path(__file__).parent.parent / "data" / "naukri_cookies.json"


class NaukriConnector(BaseConnector):
    platform_name = "naukri"
    BASE_URL = "https://www.naukri.com"

    def __init__(self, config: dict):
        super().__init__(config)
        self.headless = config.get("headless", True)
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

        keyword_slug = keywords.lower().replace(" ", "-")
        loc_slug = (location or "india").lower().replace(" ", "-")
        # Filter by experience from profile config
        from config.config_loader import load_config
        exp_years = load_config()["profile"].get("years_of_experience", 1)
        url = f"{self.BASE_URL}/{keyword_slug}-jobs-in-{loc_slug}?experience={exp_years}"
        if remote:
            url += "&wfhType=1"

        self._page.goto(url, timeout=60000)
        self._page.wait_for_load_state("load", timeout=60000)
        time.sleep(5)

        jobs = []
        seen = set()
        pages = max(1, limit // 20)

        for _ in range(pages):
            # Naukri uses multiple possible selectors for job cards
            cards = self._page.query_selector_all(
                "article.jobTuple, div.srp-jobtuple-wrapper, div[class*='jobTuple']"
            )
            if not cards:
                # Try newer Naukri layout
                cards = self._page.query_selector_all("div.cust-job-tuple, div[data-job-id]")
            self.logger.info(f"[Naukri] Page has {len(cards)} cards")

            if cards and not jobs:
                try:
                    sample = cards[0].inner_html()[:1000]
                    self.logger.debug(f"[Naukri] First card HTML: {sample}")
                except Exception:
                    pass

            for card in cards:
                if len(jobs) >= limit:
                    break
                job = self._parse_naukri_card(card)
                if job and job["url"] not in seen:
                    seen.add(job["url"])
                    jobs.append(job)
            if len(jobs) >= limit:
                break
            next_btn = self._page.query_selector(
                "a[class*='next'], a[class*='fright'], a:has-text('Next')"
            )
            if next_btn:
                next_btn.click()
                self._page.wait_for_load_state("load", timeout=30000)
                time.sleep(3)
            else:
                break

        self._stop_browser()
        return jobs[:limit]

    # ── Apply ─────────────────────────────────────────────────────────────────

    def apply(self, job: dict) -> tuple[bool, str]:
        self._start_browser()
        self._login()
        try:
            self._page.goto(job["url"], timeout=60000)
            self._page.wait_for_load_state("load", timeout=60000)
            time.sleep(3)

            # Dismiss chatbot overlay if present
            self._dismiss_chatbot()

            # Try multiple apply button selectors
            apply_selectors = [
                "button#apply-button",
                "button.apply-button",
                "a#apply-button",
                "div[id='apply-button']",
                "button[class*='apply']",
                "button:has-text('Apply')",
            ]
            apply_btn = None
            for sel in apply_selectors:
                apply_btn = self._page.query_selector(sel)
                if apply_btn:
                    self.logger.info(f"[Naukri] Found apply button: {sel}")
                    break

            if not apply_btn:
                return False, "Apply button not found on Naukri job page"

            # Use JavaScript click to bypass overlay interception
            apply_btn.evaluate("el => el.click()")
            time.sleep(4)

            # Dismiss chatbot again if it reappears
            self._dismiss_chatbot()

            # Check if a new tab/window opened (company site redirect)
            pages = self._context.pages
            if len(pages) > 1:
                # External apply — close new tab
                for p in pages[1:]:
                    p.close()
                return False, "MANUAL:Redirects to company site — apply manually"

            # Check if already applied (Naukri sometimes applies instantly)
            page_text = self._page.inner_text("body")
            if "already applied" in page_text.lower() or "application submitted" in page_text.lower():
                self.logger.info(f"[Naukri] Already applied: {job['title']}")
                return True, "Already applied on Naukri"

            # Check if "Applied Successfully" message appeared
            if "applied successfully" in page_text.lower() or "successfully applied" in page_text.lower():
                self.logger.info(f"[Naukri] Applied: {job['title']} @ {job['company']}")
                return True, "Applied via Naukri"

            # Handle possible "apply with profile" modal / confirmation
            confirm_selectors = [
                "button:has-text('Submit')",
                "button:has-text('Confirm')",
                "button:has-text('Apply Now')",
                "button[class*='submit']",
            ]
            for sel in confirm_selectors:
                confirm = self._page.query_selector(sel)
                if confirm:
                    confirm.evaluate("el => el.click()")
                    time.sleep(2)
                    self.logger.info(f"[Naukri] Applied: {job['title']} @ {job['company']}")
                    return True, "Applied via Naukri (profile apply)"

            # If a multi-step form appears
            from config.config_loader import load_config
            profile = load_config()["profile"]

            for _ in range(5):
                time.sleep(2)
                self._dismiss_chatbot()

                # Upload resume if file input appears
                resume_input = self._page.query_selector("input[type='file']")
                if resume_input:
                    resume_path = profile.get("resume_path", "")
                    resolved = Path(resume_path)
                    if resolved.exists():
                        resume_input.set_input_files(str(resolved))
                        self.logger.info(f"[Naukri] Uploaded resume: {resolved.name}")

                submit = self._page.query_selector(
                    "button:has-text('Submit'), button:has-text('Apply now')"
                )
                if submit:
                    submit.evaluate("el => el.click()")
                    time.sleep(2)
                    self.logger.info(f"[Naukri] Applied: {job['title']} @ {job['company']}")
                    return True, "Applied via Naukri"
                nxt = self._page.query_selector("button:has-text('Next')")
                if nxt:
                    nxt.evaluate("el => el.click()")
                else:
                    break

            return False, "Could not complete Naukri application"
        except Exception as e:
            return False, f"Naukri apply error: {e}"
        finally:
            self._stop_browser()

    def _dismiss_chatbot(self):
        """Remove Naukri's chatbot overlay that blocks clicks."""
        try:
            self._page.evaluate("""
                document.querySelectorAll('[class*="chatbot"], [class*="ChatBot"], [id*="chatbot"]')
                    .forEach(el => el.remove());
                document.querySelectorAll('.chatbot_Overlay').forEach(el => el.remove());
            """)
        except Exception:
            pass

    # ── Private ───────────────────────────────────────────────────────────────

    def _login(self):
        if self._logged_in:
            return

        # Try saved cookies first
        if self._load_cookies():
            self._page.goto(f"{self.BASE_URL}/mnjuser/homepage", timeout=30000)
            self._page.wait_for_load_state("load", timeout=30000)
            time.sleep(2)
            if "/login" not in self._page.url and "/nlogin" not in self._page.url:
                self._logged_in = True
                self.logger.info("[Naukri] Logged in via saved cookies")
                return
            self.logger.info("[Naukri] Saved cookies expired, logging in fresh...")

        self._page.goto(f"{self.BASE_URL}/nlogin/login", timeout=30000)
        self._page.wait_for_load_state("load", timeout=30000)

        try:
            self._page.wait_for_selector("input#usernameField", timeout=10000)
            self._page.fill("input#usernameField", self.config.get("email", ""))
            self._page.fill("input#passwordField", self.config.get("password", ""))
            self._page.click("button[type='submit']")
            self.logger.info("[Naukri] Credentials submitted...")
        except Exception:
            self.logger.info("[Naukri] Login form not found -- please log in manually in the browser window")

        # Wait for redirect away from login page
        try:
            self._page.wait_for_url("**/homepage**", timeout=60000)
        except Exception:
            if "/login" in self._page.url or "/nlogin" in self._page.url:
                self.logger.info("[Naukri] Still on login page -- waiting for manual login...")
                self._page.wait_for_url("**/homepage**", timeout=120000)

        self._save_cookies()
        self._logged_in = True
        self.logger.info("[Naukri] Logged in successfully (cookies saved for next run)")
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

    def _parse_naukri_card(self, card) -> Optional[dict]:
        try:
            # Try multiple selectors for different Naukri layouts
            title_el = (
                card.query_selector("a.title")
                or card.query_selector("a[class*='title']")
                or card.query_selector("a[href*='/job-listings']")
                or card.query_selector("a[href*='naukri.com/job']")
            )
            company_el = (
                card.query_selector("a.subTitle")
                or card.query_selector("a[class*='comp-name']")
                or card.query_selector("span[class*='comp-name']")
                or card.query_selector("a[class*='subTitle']")
            )
            location_el = (
                card.query_selector("li.location span")
                or card.query_selector("span[class*='loc']")
                or card.query_selector("span[class*='location']")
            )
            exp_el = (
                card.query_selector("li.experience span")
                or card.query_selector("span[class*='exp']")
                or card.query_selector("span[class*='expwdth']")
            )
            snippet_el = (
                card.query_selector("div.job-description")
                or card.query_selector("div[class*='job-desc']")
            )

            title = title_el.inner_text().strip() if title_el else ""
            url = title_el.get_attribute("href") if title_el else ""
            if url and not url.startswith("http"):
                url = self.BASE_URL + url
            company = company_el.inner_text().strip() if company_el else ""
            location = location_el.inner_text().strip() if location_el else ""
            description = (snippet_el.inner_text().strip() if snippet_el else "") + (
                f" Experience: {exp_el.inner_text()}" if exp_el else ""
            )

            if not title or not url:
                # Fallback: try to get any link in the card
                any_link = card.query_selector("a[href*='naukri.com']")
                if any_link:
                    title = title or any_link.inner_text().strip()
                    url = url or any_link.get_attribute("href") or ""
                if not title or not url:
                    return None

            job_id = hashlib.md5(url.encode()).hexdigest()[:8]
            return self._job_dict(
                id=job_id, title=title, company=company,
                location=location, url=url, description=description,
            )
        except Exception as e:
            self.logger.debug(f"Naukri card parse error: {e}")
            return None

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
