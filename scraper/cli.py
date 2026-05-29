from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass

from config import settings
from scraper.collectors import collect_live
from scraper.web.collector import collect_web
from scraper.location_filter import parse_location_keywords
from scraper.models import SearchRequest
from scraper.progress import set_progress_emitter, stderr_json_progress_emitter
from scraper.writer import ScraperWriter, resolve_scraper_csv_path


@dataclass
class ScraperRunResult:
    written: int
    output_path: str
    mode: str
    app: str
    query: str
    error: str = ""


def _parse_exclude_location_arg(raw: str | None) -> tuple[str, ...] | None:
    """None = .env ; chaîne vide / « none » = pas d'exclusion pour ce run."""
    if raw is None:
        return None
    if raw.strip().lower() in {"", "none", "__none__"}:
        return ()
    return parse_location_keywords(raw)


def run_search(
    *,
    mode: str,
    app: str,
    query: str = "",
    limit: int = 20,
    append: bool = True,
    linkedin_scopes: list[str] | None = None,
    include_location: str = "",
    exclude_location: str | None = None,
    no_cache: bool = False,
    clear_cache: bool = False,
) -> ScraperRunResult:
    # Initialise le cache incrémental selon les flags CLI
    if no_cache or clear_cache:
        from scraper.profile_cache import reset_profile_cache
        reset_profile_cache(enabled=not no_cache, clear=clear_cache)

    request = SearchRequest(
        mode="hashtag" if mode == "hashtag" else "keyword",
        query=query.strip(),
        app=app,  # type: ignore[arg-type]
        limit=limit,
        linkedin_scopes=tuple(linkedin_scopes or ()),
        include_location_keywords=parse_location_keywords(include_location),
        exclude_location_keywords=_parse_exclude_location_arg(exclude_location),
    )
    try:
        records = collect_live(request)
    except Exception as exc:  # noqa: BLE001
        return ScraperRunResult(
            written=0,
            output_path=str(resolve_scraper_csv_path(app)),
            mode=request.mode,
            app=request.app,
            query=request.query,
            error=str(exc),
        )
    output = ScraperWriter(output_path=resolve_scraper_csv_path(request.app)).write(
        records,
        append=append,
    )
    return ScraperRunResult(
        written=len(records),
        output_path=str(output),
        mode=request.mode,
        app=request.app,
        query=request.query,
    )


def run_web_search(
    *,
    mode: str,
    query: str = "",
    limit: int = 10,
    append: bool = True,
    include_location: str = "",
    exclude_location: str | None = None,
    search_provider: str | None = None,
) -> ScraperRunResult:
    """Google → sites d'entreprises → extraction contacts (sans LinkedIn/Instagram)."""
    if search_provider:
        settings.scraper_web_search_provider = search_provider.strip().lower()
    excl = _parse_exclude_location_arg(exclude_location)
    if excl is None:
        excl = ()
    request = SearchRequest(
        mode="hashtag" if mode == "hashtag" else "keyword",
        query=query.strip(),
        app="web",
        limit=limit,
        include_location_keywords=(),
        exclude_location_keywords=excl,
    )
    try:
        records = collect_web(request)
    except Exception as exc:  # noqa: BLE001
        return ScraperRunResult(
            written=0,
            output_path=str(resolve_scraper_csv_path("web")),
            mode=request.mode,
            app=request.app,
            query=request.query,
            error=str(exc),
        )
    output = ScraperWriter(output_path=resolve_scraper_csv_path("web")).write(
        records,
        append=append,
    )
    return ScraperRunResult(
        written=len(records),
        output_path=str(output),
        mode=request.mode,
        app=request.app,
        query=request.query,
    )


def prompt_run() -> ScraperRunResult:
    print("Scraper de leads")
    mode = input("Mode [hashtag/keyword] (keyword): ").strip().lower() or "keyword"
    if mode not in {"hashtag", "keyword"}:
        mode = "keyword"
    query = input("Hashtag ou mot-clé (plusieurs : virgules ou lignes): ").strip()
    app = input("App [linkedin/instagram] (linkedin): ").strip().lower() or "linkedin"
    if app not in {"linkedin", "instagram"}:
        app = "linkedin"
    limit_raw = input("Nombre de leads (20): ").strip() or "20"
    limit = max(1, min(100, int(limit_raw)))
    append_raw = input("Ajouter au fichier existant ? [o/n] (o): ").strip().lower() or "o"
    append = append_raw in {"o", "oui", "y", "yes", ""}
    return run_search(mode=mode, app=app, query=query, limit=limit, append=append)


def run_send(*, limit: int = 50, sync_cache: bool = True) -> dict:
    """
    Envoie les emails en attente depuis LeadStore (EmailBot.run_batch).
    Synchronise ensuite le ProfileCache avec les statuts 'contacted'.
    """
    from bots.email import EmailBot
    from leads.store import LeadStore
    from ai.generator import MessageGenerator
    from utils.outreach_logger import OutreachLogger

    store     = LeadStore()
    generator = MessageGenerator()
    logger    = OutreachLogger()
    bot       = EmailBot(store=store, generator=generator, logger=logger)

    sent = bot.run_batch(limit=limit)

    synced = 0
    if sync_cache:
        try:
            from scraper.profile_cache import get_profile_cache
            synced = get_profile_cache().sync_contacted_from_store()
        except Exception:
            pass

    return {"sent": sent, "cache_synced": synced}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scraper de leads pour Outreach Platform")
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser("run", help="Lancer une collecte")
    run_cmd.add_argument("--mode", choices=["hashtag", "keyword"], default="keyword")
    run_cmd.add_argument(
        "--query",
        default="",
        help="Mot-clé(s) ou hashtag(s), séparés par virgule, point-virgule ou retour ligne",
    )
    run_cmd.add_argument("--app", choices=["linkedin", "instagram"], default="linkedin")
    run_cmd.add_argument("--limit", type=int, default=20)
    run_cmd.add_argument(
        "--linkedin-scope",
        action="append",
        default=[],
        dest="linkedin_scopes",
        help="Catégorie LinkedIn (répétable). Omis = toutes les catégories.",
    )
    run_cmd.add_argument(
        "--include-location",
        default="",
        help="Pays à garder (mots-clés séparés par virgules, ou issus du formulaire dashboard)",
    )
    run_cmd.add_argument(
        "--exclude-location",
        default=None,
        help="Pays à exclure (virgules). « none » = désactiver pour ce run. Omis = .env",
    )
    run_cmd.add_argument("--replace", action="store_true", help="Remplacer le CSV au lieu d'ajouter")
    run_cmd.add_argument("--json", action="store_true", help="Sortie JSON pour le dashboard")
    run_cmd.add_argument("--interactive", action="store_true", help="Saisie guidée")
    run_cmd.add_argument(
        "--no-cache",
        action="store_true",
        dest="no_cache",
        help="Désactive le cache incrémental pour ce run (re-scrape tous les profils)",
    )
    run_cmd.add_argument(
        "--clear-cache",
        action="store_true",
        dest="clear_cache",
        help="Vide le cache persisté avant de lancer (repart de zéro)",
    )

    web_cmd = sub.add_parser(
        "web-run",
        help="Google → sites web → crawl (e-mails / WhatsApp). Pas de LinkedIn.",
    )
    web_cmd.add_argument("--mode", choices=["hashtag", "keyword"], default="keyword")
    web_cmd.add_argument(
        "--query",
        default="",
        help='Requête Google (ex. « agence événementiel Tunis contact email »)',
    )
    web_cmd.add_argument(
        "--search-provider",
        default=None,
        dest="search_provider",
        help="google_playwright | google_cse | google | bing | duckduckgo | auto (défaut .env)",
    )
    web_cmd.add_argument("--limit", type=int, default=10, help="Nombre max de sites à crawler")
    web_cmd.add_argument("--include-location", default="")
    web_cmd.add_argument("--exclude-location", default=None)
    web_cmd.add_argument("--replace", action="store_true")
    web_cmd.add_argument("--json", action="store_true")
    web_cmd.add_argument("--no-cache", action="store_true", dest="no_cache")
    web_cmd.add_argument("--clear-cache", action="store_true", dest="clear_cache")

    # ── Commande send ─────────────────────────────────────────────────────────
    send_cmd = sub.add_parser(
        "send",
        help="Envoyer les emails en attente (EmailBot) et synchroniser le ProfileCache",
    )
    send_cmd.add_argument("--limit", type=int, default=50, help="Nombre max d'emails à envoyer")
    send_cmd.add_argument("--json", action="store_true", help="Sortie JSON")
    send_cmd.add_argument(
        "--no-sync",
        action="store_true",
        dest="no_sync",
        help="Ne pas synchroniser le ProfileCache après l'envoi",
    )

    # ── Commande enqueue ──────────────────────────────────────────────────────
    enqueue_cmd = sub.add_parser(
        "enqueue",
        help="Injecter dans LeadStore les leads du cache qui n'ont pas encore été mis en file",
    )
    enqueue_cmd.add_argument("--limit", type=int, default=100)
    enqueue_cmd.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Score minimum (défaut : SCRAPER_EMAIL_PIPELINE_SCORE_THRESHOLD)",
    )
    enqueue_cmd.add_argument("--json", action="store_true")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "send":
        if args.json:
            set_progress_emitter(stderr_json_progress_emitter)
        try:
            result = run_send(
                limit=args.limit,
                sync_cache=not args.no_sync,
            )
        finally:
            if args.json:
                set_progress_emitter(None)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"Emails envoyés : {result['sent']} | Cache mis à jour : {result['cache_synced']}")
        return

    if args.command == "enqueue":
        from scraper.email_pipeline import reset_email_pipeline
        threshold = args.threshold
        pipeline  = reset_email_pipeline(enabled=True, threshold=threshold)
        stats     = pipeline.process_pending_from_cache(limit=args.limit)
        result    = {"injected": stats.injected, "skipped": stats.skipped, "errors": stats.errors}
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(
                f"Enqueue terminé — injectés : {stats.injected} | "
                f"ignorés : {stats.skipped} | erreurs : {stats.errors}"
            )
        return

    if args.command in {"run", "web-run"}:
        if args.json:
            set_progress_emitter(stderr_json_progress_emitter)
        try:
            if getattr(args, "interactive", False):
                result = prompt_run()
            elif args.command == "web-run":
                result = run_web_search(
                    mode=args.mode,
                    query=args.query,
                    limit=args.limit,
                    append=not args.replace,
                    include_location=getattr(args, "include_location", "") or "",
                    exclude_location=getattr(args, "exclude_location", None),
                    search_provider=getattr(args, "search_provider", None),
                )
            else:
                result = run_search(
                    mode=args.mode,
                    app=args.app,
                    query=args.query,
                    limit=args.limit,
                    append=not args.replace,
                    linkedin_scopes=args.linkedin_scopes,
                    include_location=getattr(args, "include_location", "") or "",
                    exclude_location=getattr(args, "exclude_location", None),
                    no_cache=getattr(args, "no_cache", False),
                    clear_cache=getattr(args, "clear_cache", False),
                )
        finally:
            if args.json:
                set_progress_emitter(None)
        if result.error:
            if args.json:
                print(json.dumps(asdict(result), ensure_ascii=False))
            else:
                print(f"Erreur: {result.error}")
            raise SystemExit(1)
        if args.json:
            print(json.dumps(asdict(result), ensure_ascii=False))
            return
        print(
            f"Écrit {result.written} lead(s) dans {result.output_path} "
            f"[mode={result.mode}, app={result.app}]"
        )


if __name__ == "__main__":
    main()
