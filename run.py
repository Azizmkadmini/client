from __future__ import annotations

import argparse
import json

from config import settings
from connector.logger import ConnectorLogger
from connector.queue_manager import QueueManager
from leads.store import LeadStore
from logs.logger import OutreachLogger
from orchestrator.runner import Orchestrator, summarize_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified outreach automation orchestrator.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run the full pipeline once")
    run_cmd.add_argument(
        "--source",
        choices=["csv", "sqlite", "mongo"],
        default="csv",
        help="Connector input source",
    )
    run_cmd.add_argument("--retry", action="store_true", help="Retry connector failures first")
    run_cmd.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max leads per outreach channel",
    )
    run_cmd.add_argument(
        "--no-scraper",
        action="store_true",
        help="Skip optional external scraper command",
    )
    run_cmd.add_argument(
        "--no-outreach",
        action="store_true",
        help="Run connector and ingest only",
    )

    schedule_cmd = sub.add_parser("schedule", help="Run the full pipeline on an interval")
    schedule_cmd.add_argument(
        "--hours",
        type=float,
        default=settings.orchestrator_interval_hours,
        help="Hours between full pipeline runs",
    )
    schedule_cmd.add_argument(
        "--source",
        choices=["csv", "sqlite", "mongo"],
        default="csv",
    )
    schedule_cmd.add_argument("--retry", action="store_true")
    schedule_cmd.add_argument("--limit", type=int, default=None)

    sub.add_parser("status", help="Show unified pipeline status")
    return parser


def cmd_run(args: argparse.Namespace) -> None:
    orchestrator = Orchestrator()
    result = orchestrator.run_once(
        source=args.source,
        retry_failed=args.retry,
        per_channel_limit=args.limit,
        run_scraper_step=not args.no_scraper,
        run_outreach=not args.no_outreach,
    )
    print(json.dumps(summarize_result(result), indent=2, ensure_ascii=False))


def cmd_schedule(args: argparse.Namespace) -> None:
    orchestrator = Orchestrator()
    orchestrator.run_forever(
        hours=args.hours,
        source=args.source,
        retry_failed=args.retry,
        per_channel_limit=args.limit,
    )


def cmd_status() -> None:
    store = LeadStore()
    outreach_logger = OutreachLogger()
    connector_logger = ConnectorLogger()
    queue = QueueManager()
    outreach_metrics = outreach_logger.metrics()
    connector_summary = connector_logger.summary()

    print("Orchestrator status")
    print(f"  scraper_output: {settings.path(settings.scraper_output_csv)}")
    print(f"  outreach_store: {settings.path(settings.leads_csv)}")
    print(f"  queue_file: {settings.path(settings.connector_queue_path)}")
    print(f"  queue_size: {queue.queue_size()}")
    print(f"  connector_processed: {queue.processed_count()}")
    print(f"  connector_failed: {queue.failed_count()}")
    print(f"  connector_log_processed: {connector_summary['processed']}")
    print(f"  connector_log_rejected: {connector_summary['rejected']}")
    print(f"  connector_log_errors: {connector_summary['errors']}")
    print("  lead_status:")
    for key, value in sorted(store.stats().items()):
        print(f"    {key}: {value}")
    print("  outreach_metrics:")
    print(f"    sent: {outreach_metrics['sent']}")
    print(f"    failed: {outreach_metrics['failed']}")
    print(f"    replies: {outreach_metrics['replies']}")
    print(f"    success_rate: {outreach_metrics['success_rate']}%")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args)
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "status":
        cmd_status()


if __name__ == "__main__":
    main()
