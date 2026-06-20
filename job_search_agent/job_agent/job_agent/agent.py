"""
Job Search Agent
================
Searches for jobs across LinkedIn and Naukri,
collects all data, and saves to an Excel spreadsheet.

Usage:
    python agent.py search --keywords "Design Verification" --location "Bangalore"
    python agent.py run    # search all enabled platforms
    python agent.py status # show collected jobs
    python agent.py export # export to Excel
"""

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.orchestrator import Orchestrator
from core.tracker import Tracker
from core.logger import get_logger
from config.config_loader import load_config

logger = get_logger("agent")


def _validate_config():
    cfg = load_config()
    profile = cfg.get("profile", {})

    if profile.get("name", "") in ("", "Your Full Name"):
        print("[ERROR] Please fill in your profile in config/settings.yaml before running.")
        sys.exit(1)

    platforms = cfg.get("platforms", {})
    has_creds = False
    for name, pcfg in platforms.items():
        if pcfg.get("enabled", True) and pcfg.get("email", "") not in ("", "you@example.com"):
            has_creds = True
            break
    if not has_creds:
        print("[ERROR] No platform credentials configured. Edit config/settings.yaml.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Job Search Agent - Collects jobs into a spreadsheet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- search command ---
    search_p = subparsers.add_parser("search", help="Search for jobs")
    search_p.add_argument("--keywords", "-k", nargs="+", required=True, help="Job title / skills")
    search_p.add_argument("--location", "-l", default=None, help="City or country")
    search_p.add_argument("--remote", action="store_true", help="Remote only")
    search_p.add_argument("--platforms", nargs="+", default=["linkedin", "naukri"],
                          choices=["linkedin", "naukri"])
    search_p.add_argument("--limit", type=int, default=20, help="Max results per platform")

    # --- run command (search all platforms) ---
    run_p = subparsers.add_parser("run", help="Search all enabled platforms and export")
    run_p.add_argument("--keywords", "-k", nargs="+", required=True)
    run_p.add_argument("--location", "-l", default=None)
    run_p.add_argument("--remote", action="store_true")
    run_p.add_argument("--platforms", nargs="+", default=["linkedin", "naukri"],
                       choices=["linkedin", "naukri"])
    run_p.add_argument("--limit", type=int, default=20)

    # --- status command ---
    subparsers.add_parser("status", help="Show collected jobs dashboard")

    # --- export command ---
    export_p = subparsers.add_parser("export", help="Export jobs to Excel spreadsheet")
    export_p.add_argument("--output", "-o", default=None, help="Output XLSX file path")

    args = parser.parse_args()

    if args.command not in ("status", "export"):
        _validate_config()

    orchestrator = Orchestrator()
    tracker = Tracker()

    if args.command == "search":
        jobs = orchestrator.search(
            keywords=" ".join(args.keywords),
            location=args.location,
            remote=args.remote,
            platforms=args.platforms,
            limit=args.limit,
        )
        print(f"\nFound {len(jobs)} jobs.\n")
        for j in jobs:
            print(f"  [{j['platform']}] {j['title']} @ {j['company']} -- {j['location']}")
        path = tracker.export_spreadsheet()
        print(f"\nSpreadsheet saved: {path}")

    elif args.command == "run":
        orchestrator.run(
            keywords=" ".join(args.keywords),
            location=args.location,
            remote=args.remote,
            platforms=args.platforms,
            limit=args.limit,
        )

    elif args.command == "status":
        tracker.print_dashboard()

    elif args.command == "export":
        path = tracker.export_spreadsheet(args.output)
        print(f"Exported to: {path}")


if __name__ == "__main__":
    main()
