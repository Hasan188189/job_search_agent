"""
Orchestrator
============
Coordinates search -> score -> track -> export to spreadsheet.
"""

from __future__ import annotations
import uuid
from typing import Optional
from config.config_loader import load_config
from core.tracker import Tracker
from core.scorer import score_job
from core.logger import get_logger
from connectors.linkedin import LinkedInConnector
from connectors.naukri import NaukriConnector

logger = get_logger("orchestrator")


class Orchestrator:
    def __init__(self):
        self.cfg = load_config()
        self.tracker = Tracker()
        self._connectors = {
            "linkedin": LinkedInConnector,
            "naukri": NaukriConnector,
        }

    def search(
        self,
        keywords: str,
        location: Optional[str],
        remote: bool,
        platforms: list[str],
        limit: int,
    ) -> list[dict]:
        """Search all requested platforms and store results in tracker."""
        all_jobs = []
        for platform in platforms:
            if platform not in self._connectors:
                logger.info(f"Skipping {platform} (no connector)")
                continue
            cfg_p = self.cfg["platforms"].get(platform, {})
            if not cfg_p.get("enabled", True):
                logger.info(f"Skipping {platform} (disabled in config)")
                continue
            try:
                connector = self._connectors[platform](cfg_p)
                jobs = connector.search(keywords=keywords, location=location,
                                        remote=remote, limit=limit)
                logger.info(f"[{platform}] Found {len(jobs)} jobs")
                all_jobs.extend(jobs)
            except Exception as e:
                logger.error(f"[{platform}] Search failed: {e}")

        all_jobs = self._apply_filters(all_jobs)

        profile = self.cfg["profile"]
        for job in all_jobs:
            job["id"] = job.get("id") or str(uuid.uuid4())[:8]
            job["match_score"] = score_job(job, profile)
            self.tracker.upsert_job(job)

        all_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        return all_jobs

    def run(
        self,
        keywords: str,
        location: Optional[str],
        remote: bool,
        platforms: list[str],
        limit: int,
        dry_run: bool = False,
    ):
        """Search -> score -> track -> export spreadsheet."""
        logger.info("Starting job search...")
        jobs = self.search(keywords, location, remote, platforms, limit)
        logger.info(f"Collected {len(jobs)} jobs total")

        self.tracker.print_dashboard()
        path = self.tracker.export_spreadsheet()
        logger.info(f"Spreadsheet saved: {path}")

    def _apply_filters(self, jobs: list[dict]) -> list[dict]:
        excl_companies = [c.lower() for c in self.cfg["filters"].get("exclude_companies", [])]
        excl_keywords = [k.lower() for k in self.cfg["filters"].get("exclude_keywords", [])]
        filtered = []
        for job in jobs:
            if job.get("company", "").lower() in excl_companies:
                continue
            desc = (job.get("description", "") + " " + job.get("title", "")).lower()
            if any(kw in desc for kw in excl_keywords):
                continue
            filtered.append(job)
        return filtered
