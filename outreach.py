from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from config import settings
from orchestrator.runner import Orchestrator, summarize_result
from utils.browser_session import session_path


CHANNELS = ("linkedin", "instagram", "whatsapp", "email")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Outreach utilities for the unified outreach pipeline.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run one outreach channel via the orchestrator")
    run_cmd.add_argument("channel", choices=CHANNELS)
    run_cmd.add_argument("--limit", type=int, default=None)
    run_cmd.add_argument("--headless", action="store_true")

    sub.add_parser("status", help="Show unified pipeline status")

    reply_cmd = sub.add_parser("reply", help="Mark a lead as replied")
    reply_cmd.add_argument("lead_id")
    reply_cmd.add_argument("--snippet", default="")

    login_cmd = sub.add_parser("login", help="Save an interactive browser session")
    login_cmd.add_argument(
        "channel",
        choices=[
            "linkedin",
            "linkedin-scrape",
            "linkedin-outreach",
            "linkedin-publish",
            "instagram",
            "whatsapp",
        ],
    )
    login_cmd.add_argument("--headless", action="store_true")
    login_cmd.add_argument(
        "--from-browser",
        choices=["chrome", "edge", "firefox", "brave"],
        help="Importer la session depuis un navigateur déjà connecté sur ce PC",
    )
    login_cmd.add_argument(
        "--cdp",
        action="store_true",
        help="Tester la connexion au navigateur ouvert en mode débogage (port 9222)",
    )

    session_cmd = sub.add_parser(
        "session-check",
        help="Vérifier que sessions/linkedin.json existe et n'est pas expirée",
    )
    session_cmd.add_argument(
        "channel",
        nargs="?",
        default="linkedin",
        choices=[
            "linkedin",
            "linkedin-scrape",
            "linkedin-outreach",
            "linkedin-publish",
            "instagram",
            "whatsapp",
        ],
    )

    import_cmd = sub.add_parser("import", help="Copy a CSV into the scraper input and run the pipeline")
    import_cmd.add_argument("csv", type=Path)
    import_cmd.add_argument("--replace", action="store_true")

    schedule_cmd = sub.add_parser("schedule", help="Run the unified pipeline on an interval")
    schedule_cmd.add_argument("--hours", type=float, default=settings.orchestrator_interval_hours)
    schedule_cmd.add_argument("--limit", type=int, default=None)

    opt_out_cmd = sub.add_parser("opt-out", help="Register an opt-out identifier")
    opt_out_cmd.add_argument("identifier")
    opt_out_cmd.add_argument("--reason", default="user_request")

    return parser


def cmd_import(args: argparse.Namespace) -> None:
    target = settings.path(settings.scraper_output_csv)
    target.parent.mkdir(parents=True, exist_ok=True)
    if args.replace:
        shutil.copyfile(args.csv, target)
    else:
        if target.exists():
            existing = target.read_text(encoding="utf-8").splitlines()
            incoming = args.csv.read_text(encoding="utf-8").splitlines()
            merged = existing + incoming[1:] if incoming else existing
            target.write_text("\n".join(merged) + "\n", encoding="utf-8")
        else:
            shutil.copyfile(args.csv, target)
    result = Orchestrator().run_once(source="csv", run_scraper_step=False)
    print(summarize_result(result))


def cmd_run(args: argparse.Namespace) -> None:
    settings.orchestrator_interactive = not args.headless
    orchestrator = Orchestrator()
    sent = orchestrator.run_channel(
        args.channel,
        per_channel_limit=args.limit,
        headless=args.headless or settings.orchestrator_headless,
    )
    print(f"Sent {sent} message(s) on {args.channel}")


def cmd_reply(args: argparse.Namespace) -> None:
    from leads.store import LeadStore
    from utils.outreach_logger import OutreachLogger

    store = LeadStore()
    logger = OutreachLogger()
    store.mark_replied(args.lead_id)
    logger.log_reply(args.lead_id, channel="manual", snippet=args.snippet)
    print(f"Marked lead {args.lead_id} as replied")


def cmd_login(args: argparse.Namespace) -> None:
    from playwright.sync_api import sync_playwright

    from utils.browser_session import (
        close_session,
        import_system_browser_cookies,
        login_in_app_browser,
        open_channel_context,
        persist_context_state,
        session_path,
    )
    from utils.session_channels import normalize_login_channel

    if args.from_browser:
        try:
            storage = import_system_browser_cookies(
                args.channel,
                browser_source=args.from_browser,
            )
        except RuntimeError as exc:
            print(str(exc))
            print(
                "Astuce: fermez Chrome, ou lancez-le avec "
                "--remote-debugging-port=9222 puis utilisez --cdp."
            )
            raise SystemExit(1) from exc
        print(
            f"Session {args.channel} importée depuis {args.from_browser} vers {storage}. "
            "Vous pouvez lancer le scraper ou l'outreach sans vous reconnecter."
        )
        return

    if args.cdp:
        storage_channel, url_key = normalize_login_channel(args.channel)
        settings.browser_connection_mode = "cdp"
        with sync_playwright() as playwright:
            browser, context, owns_browser = open_channel_context(
                playwright,
                storage_channel,
                headless=False,
            )
            page = context.new_page()
            page.goto(
                {
                    "linkedin": "https://www.linkedin.com/feed/",
                    "instagram": "https://www.instagram.com/",
                    "whatsapp": "https://web.whatsapp.com/",
                }[url_key],
                wait_until="domcontentloaded",
            )
            print(
                "Navigateur PC connecté en mode CDP. "
                "Laissez BROWSER_CONNECTION_MODE=cdp dans .env pour le scraper et l'outreach."
            )
            input("Vérifiez que le compte est connecté, puis appuyez sur Entrée.")
            previous_mode = settings.browser_connection_mode
            settings.browser_connection_mode = "storage"
            persist_context_state(storage_channel, context)
            settings.browser_connection_mode = previous_mode
            close_session(browser, context, owns_browser=owns_browser)
        print(f"Session {args.channel} sauvegardée depuis le navigateur PC.")
        return

    settings.orchestrator_interactive = True
    storage = login_in_app_browser(args.channel, headless=args.headless)
    print(f"Session enregistrée dans {storage}")


def cmd_schedule(args: argparse.Namespace) -> None:
    Orchestrator().run_forever(
        hours=args.hours,
        per_channel_limit=args.limit,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "import":
        cmd_import(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        from run import cmd_status

        cmd_status()
    elif args.command == "reply":
        cmd_reply(args)
    elif args.command == "login":
        cmd_login(args)
    elif args.command == "session-check":
        if args.channel in ("linkedin", "linkedin-scrape"):
            from scraper.linkedin_stability import (
                session_file_age_days,
                validate_linkedin_session_file,
            )

            path = validate_linkedin_session_file()
            age = session_file_age_days("linkedin")
            print(f"OK scrape — {path} (âge {age:.1f} j)" if age is not None else f"OK — {path}")
        elif args.channel == "linkedin-outreach":
            from utils.session_channels import first_existing_session

            path = first_existing_session("linkedin", role="outreach")
            if path is None:
                raise SystemExit(
                    "Pas de session outreach. Lancez: python outreach.py login linkedin-outreach"
                )
            print(f"OK outreach — {path}")
        elif args.channel == "instagram":
            from scraper.instagram_stability import (
                session_file_age_days,
                validate_instagram_session_file,
            )

            path = validate_instagram_session_file()
            age = session_file_age_days("instagram")
            print(f"OK — {path} (âge {age:.1f} j)" if age is not None else f"OK — {path}")
        else:
            p = session_path(args.channel)
            if not p.is_file():
                raise SystemExit(
                    f"Pas de session {args.channel}. "
                    f"Lancez: python outreach.py login {args.channel}"
                )
            print(f"OK — {p}")
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "opt-out":
        from compliance.registry import ComplianceRegistry

        ComplianceRegistry().register_opt_out(args.identifier, args.reason)
        print(f"Registered opt-out for {args.identifier.strip().lower()}")


if __name__ == "__main__":
    main()
