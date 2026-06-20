"""
Indeed Connector
================
Uses Indeed's Publisher XML API for search (if publisher_id is set),
otherwise falls back to Playwright scraping.

Apply: Indeed's "Apply with Indeed Resume" flow via browser automation.
"""

import time
import hashlib
import requests
from typing import Optional
from connectors.base import BaseConnector


class IndeedConnector(BaseConnector):
    platform_name = "indeed"
    PUBLISHER_URL = "https://api.indeed.com/ads/apisearch"

    def __init__(self, config: dict):
        super().__init__(config)
        self.publisher_id = config.get("publisher_id", "")
        self.headless = config.get("headless", True)
        self._pw = self._browser = self._context = self._page = None

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        keywords: str,
        location: Optional[str] = None,
        remote: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        if self.publisher_id:
            return self._search_api(keywords, location, remote, limit)
        return self._search_browser(keywords, location, remote, limit)

    def _search_api(self, keywords, location, remote, limit) -> list[dict]:
        params = {
            "publisher": self.publisher_id,
            "q": keywords,
            "l": location or "",
            "format": "json",
            "v": "2",
            "limit": min(limit, 25),
            "remotejob": "1" if remote else "0",
            "co": "in",           # India
            "userip": "1.2.3.4",
            "useragent": "Mozilla/5.0",
        }
        try:
            resp = requests.get(self.PUBLISHER_URL, params=params, timeout=10)
            data = resp.json()
            jobs = []
            for r in data.get("results", []):
                job_id = hashlib.md5(r.get("url", r.get("jobkey", "")).encode()).hexdigest()[:8]
                jobs.append(self._job_dict(
                    id=job_id,
                    title=r.get("jobtitle", ""),
                    company=r.get("company", ""),
                    location=r.get("formattedLocation", ""),
                    url=r.get("url", ""),
                    description=r.get("snippet", ""),
                    posted_date=r.get("date", ""),
                ))
            return jobs
        except Exception as e:
            self.logger.warning(f"Indeed API failed ({e}), falling back to browser")
            return self._search_browser(keywords, location, remote, limit)

    def _search_browser(self, keywords, location, remote, limit) -> list[dict]:
        self._start_browser()
        loc = location or "India"
        url = (
            f"https://in.indeed.com/jobs?q={keywords.replace(' ', '+')}"
            f"&l={loc.replace(' ', '+')}"
        )
        if remote:
            url += "&remotejob=032b3046-06a3-4876-8dfd-474eb5e7ed11"

        self._page.goto(url)
        self._page.wait_for_load_state("networkidle", timeout=15000)

        jobs = []
        seen = set()
        pages = max(1, limit // 15)
        for _ in range(pages):
            cards = self._page.query_selector_all("div.job_seen_beacon")
            for card in cards:
                if len(jobs) >= limit:
                    break
                job = self._parse_indeed_card(card)
                if job and job["url"] not in seen:
                    seen.add(job["url"])
                    jobs.append(job)
            if len(jobs) >= limit:
                break
            next_btn = self._page.query_selector("a[data-testid='pagination-page-next']")
            if next_btn:
                next_btn.click()
                self._page.wait_for_load_state("networkidle", timeout=10000)
            else:
                break

        self._stop_browser()
        return jobs[:limit]

    # ── Apply ─────────────────────────────────────────────────────────────────

    def apply(self, job: dict) -> tuple[bool, str]:
        self._start_browser()
        self._login()
        try:
            self._page.goto(job["url"])
            self._page.wait_for_load_state("networkidle", timeout=15000)

            # Look for "Apply now" button (Indeed Resume flow)
            apply_btn = self._page.query_selector(
                "button#indeedApplyButton, button[id*='apply']"
            )
            if not apply_btn:
                return False, "Apply button not found — may require external site"

            apply_btn.click()
            time.sleep(3)

            # Indeed opens an iframe or new page
            frames = self._page.frames
            apply_frame = next(
                (f for f in frames if "indeedapply" in f.url or "smartapply" in f.url),
                None,
            )
            target = apply_frame or self._page

            # Step through form — upload resume at each step if file input appears
            from pathlib import Path
            from config.config_loader import load_config
            profile = load_config()["profile"]

            for _ in range(6):
                time.sleep(1.5)

                # Upload resume if file input appears
                resume_input = target.query_selector("input[type='file']")
                if resume_input:
                    resume_path = profile.get("resume_path", "")
                    resolved = Path(resume_path).resolve()
                    if resolved.exists():
                        resume_input.set_input_files(str(resolved))
                        self.logger.info(f"Uploaded resume: {resolved.name}")

                # Next / Submit
                submit = target.query_selector("button[type='submit'], button:has-text('Submit')")
                if submit:
                    submit.click()
                    time.sleep(2)
                    return True, "Submitted via Indeed"
                nxt = target.query_selector(
                    "button:has-text('Continue'), button:has-text('Next')"
                )
                if nxt:
                    nxt.click()
                else:
                    break

            return False, "Could not complete Indeed application flow"
        except Exception as e:
            return False, f"Indeed apply error: {e}"
        finally:
            self._stop_browser()

    # ── Private ───────────────────────────────────────────────────────────────

    def _login(self):
        self._page.goto("https://secure.indeed.com/account/login")
        self._page.wait_for_load_state("networkidle")
        self._page.fill("input#login-email-input", self.config.get("email", ""))
        self._page.click("button[type='submit']")
        time.sleep(1)
        self._page.fill("input#login-password-input", self.config.get("password", ""))
        self._page.click("button[type='submit']")
        self._page.wait_for_load_state("networkidle", timeout=15000)
        self.logger.info("[Indeed] Logged in")

    def _parse_indeed_card(self, card) -> Optional[dict]:
        try:
            title_el = card.query_selector("h2.jobTitle a, a.jcs-JobTitle")
            company_el = card.query_selector("span[data-testid='company-name']")
            location_el = card.query_selector("div[data-testid='text-location']")
            snippet_el = card.query_selector("div.job-snippet, ul.jobCardShelfContainer")

            title = title_el.inner_text().strip() if title_el else ""
            href = title_el.get_attribute("href") if title_el else ""
            url = f"https://in.indeed.com{href}" if href and not href.startswith("http") else href
            company = company_el.inner_text().strip() if company_el else ""
            location = location_el.inner_text().strip() if location_el else ""
            description = snippet_el.inner_text().strip() if snippet_el else ""

            if not title or not url:
                return None

            job_id = hashlib.md5(url.encode()).hexdigest()[:8]
            return self._job_dict(
                id=job_id, title=title, company=company,
                location=location, url=url, description=description,
            )
        except Exception as e:
            self.logger.debug(f"Indeed card parse error: {e}")
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
        self._pw = self._browser = self._context = self._page = None
