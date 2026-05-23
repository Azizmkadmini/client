from __future__ import annotations

import argparse

from config import settings
from orchestrator.runner import Orchestrator, summarize_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connector stage of the unified outreach pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run connector + ingest through the orchestrator")
    run_cmd.add_argument("--source", choices=["csv", "sqlite", "mongo"], default="csv")
    run_cmd.add_argument("--retry", action="store_true")
    run_cmd.add_argument("--no-scraper", action="store_true")

    schedule_cmd = sub.add_parser("schedule", help="Run the unified pipeline on an interval")
    schedule_cmd.add_argument("--hours", type=float, default=settings.orchestrator_interval_hours)
    schedule_cmd.add_argument("--source", choices=["csv", "sqlite", "mongo"], default="csv")
    schedule_cmd.add_argument("--retry", action="store_true")
    schedule_cmd.add_argument("--limit", type=int, default=None)

    sub.add_parser("status", help="Show unified pipeline status")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    orchestrator = Orchestrator()

    if args.command == "run":
        result = orchestrator.run_once(
            source=args.source,
            retry_failed=args.retry,
            run_scraper_step=not args.no_scraper,
            run_outreach=False,
        )
        print(summarize_result(result))
    elif args.command == "schedule":
        orchestrator.run_forever(
            hours=args.hours,
            source=args.source,
            retry_failed=args.retry,
            per_channel_limit=getattr(args, "limit", None),
        )
    elif args.command == "status":
        from run import cmd_status

        cmd_status()


if __name__ == "__main__":
    main()
