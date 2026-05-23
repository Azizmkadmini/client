from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent)

    ai_provider: str = "ollama"       # ollama | openai | groq | template
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # Si true : emails d'outreach toujours via templates/ (ignore AI_PROVIDER pour l'envoi)
    email_use_templates_only: bool = True

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    linkedin_daily_max: int = 25
    instagram_daily_max: int = 40
    instagram_username: str = ""
    instagram_password: str = Field(default="", repr=False)
    email_daily_max: int = 75
    whatsapp_daily_max: int = 20
    whatsapp_verify_mode: str = "off"
    whatsapp_verify_webhook_url: str = ""
    whatsapp_verify_webhook_token: str = ""
    whatsapp_verify_webhook_timeout: float = 12.0
    whatsapp_verify_unknown_keep_link: bool = True

    delay_min: int = 10
    delay_max: int = 60
    pause_every_min: int = 5
    pause_every_max: int = 10
    long_pause_min: int = 120
    long_pause_max: int = 300

    leads_csv: str = "data/outreach_leads.csv"
    log_dir: str = "logs"
    session_dir: str = "sessions"
    app_db_path: str = "data/app.db"
    storage_backend: str = "sqlite"
    # En mode postgres : export CSV miroir pour compat (désactiver = SSOT strict)
    leads_csv_export: bool = True
    opt_out_csv: str = "compliance/opt_out.csv"
    logging_level: str = "INFO"

    scraper_output_csv: str = "leads/scraper_output.csv"
    scraper_instagram_output_csv: str = ""
    scraper_command: str = ""
    orchestrator_interval_hours: float = 6.0
    orchestrator_headless: bool = True
    orchestrator_interactive: bool = False
    scraper_headless: bool = False
    scraper_fast_mode: bool = False
    # Mode stable LinkedIn : rythme humain, limites basses, ignore scraper_fast_mode pour LI.
    scraper_stable_linkedin_mode: bool = True
    scraper_session_max_age_days: float = 10.0
    scraper_linkedin_stable_max_profiles_per_search: int = 25
    scraper_linkedin_stable_max_search_terms: int = 4
    scraper_linkedin_long_pause_every_min: int = 6
    scraper_linkedin_long_pause_every_max: int = 10
    scraper_linkedin_long_pause_seconds_min: int = 45
    scraper_linkedin_long_pause_seconds_max: int = 120
    # Pause entre profils LinkedIn (indépendant de DELAY_MIN du bot outreach).
    scraper_inter_profile_pause_seconds: float = 3.0
    scraper_skip_profile_revisit: bool = True
    scraper_linkedin_skip_company_about_when_contacted: bool = True
    # Timeout du sous-processus scraper lancé depuis le dashboard (secondes). 14 mots-clés × 2 catégories ≈ long.
    scraper_dashboard_subprocess_timeout_seconds: int = 14400
    scraper_linkedin_max_search_terms: int = 0
    scraper_linkedin_enrich_profiles: bool = True
    scraper_linkedin_require_email_or_whatsapp: bool = True
    # True : seuls les profils avec e-mail sont gardés (WhatsApp seul = on continue à chercher).
    scraper_linkedin_prioritize_email: bool = True
    # Continue scroll + enrichissement jusqu'à N profils avec e-mail ou WhatsApp (par recherche / catégorie).
    scraper_linkedin_keep_searching_until_contact: bool = True
    scraper_linkedin_max_profiles_to_try: int = 25
    scraper_linkedin_max_search_scroll_rounds: int = 5
    scraper_linkedin_quick_contact_probe: bool = True
    scraper_linkedin_deep_enrich_on_match: bool = False
    # Si pas de contact LinkedIn : crawl du site + guess e-mail (activé via supplement après quick probe).
    scraper_linkedin_website_when_no_contact: bool = True
    scraper_website_priority_three_pages: bool = True
    scraper_linkedin_use_three_dots_menu: bool = True
    # Mots-clés pays/bio : profils exclus (ex. tunisia,tunisie,tunis,monastir,sfax)
    scraper_exclude_location_keywords: str = ""
    # Si true : sans pays/bio scrapé, le profil est exclu quand l'exclusion Tunisie est active.
    scraper_exclude_location_strict: bool = False
    scraper_fetch_contacts_from_website: bool = True
    scraper_site_crawl_max_pages: int = 55
    scraper_site_crawl_total_seconds: float = 150.0
    scraper_site_deep_sitemap: bool = True
    scraper_site_deep_probe_extra: bool = True
    # En mode rapide : après les 3 pages prioritaires, pas de crawl BFS (évite les timeouts).
    scraper_site_crawl_bfs_in_fast_mode: bool = False
    scraper_profile_wide_contact_scan: bool = True
    scraper_linkedin_company_contact_fallback: bool = True
    scraper_guess_contact_emails: bool = True
    scraper_guess_email_require_mx: bool = True
    # Mode rapide : ne pas exiger MX pour prenom.nom@domaine (sinon beaucoup de rejets DNS).
    scraper_guess_email_relaxed_mx_in_fast_mode: bool = True
    scraper_contact_trace_logs: bool = True
    scraper_linkedin_contact_email_paint_max_ms: int = 6000

    # ── Collecte web (Google / Bing → URLs → enrichissement ou crawl sites) ─
    scraper_web_discovery_enabled: bool = True
    # auto | google_playwright | google | google_cse | bing | duckduckgo
    # google_cse : indisponible pour les nouveaux comptes Google (2024+). Préférer bing ou auto.
    scraper_web_search_provider: str = "bing"
    scraper_web_google_api_key: str = ""
    scraper_web_google_cx: str = ""
    scraper_web_google_use_playwright: bool = True
    scraper_web_google_hl: str = "fr"
    scraper_web_google_gl: str = ""
    scraper_web_output_csv: str = "leads/scraper_web_google.csv"
    scraper_web_max_results_per_query: int = 15
    scraper_web_max_queries_per_run: int = 4
    scraper_web_pause_between_requests_seconds: float = 2.5
    scraper_web_http_timeout_seconds: float = 25.0
    scraper_web_linkedin_include_companies: bool = False
    scraper_web_instagram_playwright_fallback: bool = True

    # ── Cache incrémental (fresh incremental scraping) ──────────────────────
    # Empêche de re-scraper les profils déjà collectés récemment.
    scraper_profile_cache_enabled: bool = True
    scraper_profile_cache_path: str = "data/scraper_cache.db"
    # Durée de validité (jours) si email trouvé — défaut 7 jours.
    scraper_profile_cache_ttl_days: float = 7.0
    # Durée de validité (jours) si pas d'email trouvé — défaut 1 jour.
    scraper_profile_cache_ttl_no_email_days: float = 1.0

    # ── Pipeline email post-enrichissement ───────────────────────────────────
    # Si true : les leads ACCEPTED (email trouvé) sont automatiquement injectés
    # dans LeadStore pour envoi via EmailBot. false par défaut → opt-in explicite.
    scraper_email_pipeline_enabled: bool = False
    # Score minimum (0–10) pour qu'un lead passe dans la file email.
    scraper_email_pipeline_score_threshold: float = 3.0

    # ── Profil expéditeur (utilisé par le générateur IA pour personaliser les emails) ──
    sender_name: str = ""
    sender_email: str = ""
    sender_tagline: str = ""
    sender_offers: str = ""
    sender_results: str = ""

    browser_connection_mode: str = "storage"
    browser_cdp_url: str = "http://127.0.0.1:9222"
    browser_channel: str = ""
    browser_from: str = "chrome"
    browser_profile: str = "Default"

    connector_source_csv: str = "leads/scraper_output.csv"
    connector_queue_path: str = "bot/leads_queue.json"
    connector_sqlite_path: str = "data/connector.db"
    connector_processed_log: str = "logs/connector_processed_leads.jsonl"
    connector_failed_log: str = "logs/connector_failed_leads.jsonl"
    connector_export_mode: str = "both"
    connector_schedule_hours: float = 0
    connector_auto_ingest: bool = True
    mongodb_uri: str = ""
    mongodb_db: str = "outreach"
    mongodb_collection: str = "scraper_leads"

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_key: str = ""
    dashboard_password: str = ""

    # File Redis (Phase 2) — jobs scraper asynchrones
    redis_url: str = ""
    scraper_queue_sync_fallback: bool = True
    # Si true et REDIS_URL défini : dashboard/API utilisent la file (worker requis).
    scraper_use_redis_queue: bool = True
    scraper_queue_poll_seconds: float = 2.0
    database_url: str = ""
    email_warmup_start_date: str = ""

    # ── AI LinkedIn Content OS ───────────────────────────────────────────────
    content_ai_provider: str = ""  # vide = AI_PROVIDER
    content_openai_model: str = ""
    content_claude_api_key: str = Field(default="", repr=False)
    content_claude_model: str = "claude-3-5-sonnet-20241022"
    content_ollama_model: str = ""
    content_max_posts_per_day: int = 2
    content_publish_session_channel: str = "linkedin-publish"
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    jwt_secret: str = Field(default="", repr=False)
    jwt_expire_hours: int = 168

    r2_account_id: str = ""
    r2_access_key_id: str = Field(default="", repr=False)
    r2_secret_access_key: str = Field(default="", repr=False)
    r2_bucket: str = "aios-media"
    r2_public_base_url: str = ""

    oauth_linkedin_client_id: str = ""
    oauth_linkedin_client_secret: str = Field(default="", repr=False)
    oauth_linkedin_redirect_uri: str = "http://127.0.0.1:8000/api/v1/oauth/linkedin/callback"
    web_app_url: str = "http://127.0.0.1:3000"
    browser_pool_max_slots: int = 2

    # Phase 5 — Billing Stripe (optionnel)
    stripe_secret_key: str = Field(default="", repr=False)
    stripe_webhook_secret: str = Field(default="", repr=False)
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    billing_credits_per_scrape: int = 1
    billing_credits_per_send: int = 1

    # Enterprise E0–E5
    secrets_encryption_key: str = Field(default="", repr=False)
    sentry_dsn: str = ""
    otel_enabled: bool = False
    browser_grid_mode: str = "local"  # local | remote
    browser_grid_url: str = "http://127.0.0.1:8090"
    proxy_cooldown_seconds: float = 300.0
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    default_region: str = "eu-west"
    supported_locales: str = "fr,en"
    ai_daily_token_cap_per_tenant: int = 500_000
    redis_stream_maxlen: int = 100_000

    # Production hardening — workers / queue / browser
    app_env: str = "development"
    worker_job_timeout_seconds: int = 3600
    worker_heartbeat_ttl_seconds: int = 60
    worker_processing_stale_seconds: int = 3600
    queue_job_ttl_seconds: int = 604800
    browser_pool_recycle_pages: int = 50
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    retention_events_days: int = 90
    retention_scraper_jobs_days: int = 30

    @property
    def root(self) -> Path:
        return self.project_root

    def path(self, relative: str) -> Path:
        return self.project_root / relative


settings = Settings()
