"""Migrations SQLite — module Content OS (dev local sans Postgres)."""

CONTENT_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        plan TEXT NOT NULL DEFAULT 'starter',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_drafts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        title TEXT,
        body TEXT NOT NULL,
        hook TEXT,
        cta TEXT,
        format TEXT NOT NULL DEFAULT 'text',
        category TEXT,
        status TEXT NOT NULL DEFAULT 'draft',
        linkedin_account_id TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_posts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        draft_id TEXT,
        body TEXT NOT NULL,
        hook TEXT,
        cta TEXT,
        format TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        scheduled_at TEXT,
        published_at TEXT,
        linkedin_post_url TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_calendar_slots (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        post_id TEXT NOT NULL,
        slot_start TEXT NOT NULL,
        timezone TEXT NOT NULL DEFAULT 'Europe/Paris',
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_publish_jobs (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        post_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 3,
        payload TEXT,
        result TEXT,
        error TEXT,
        scheduled_for TEXT NOT NULL,
        finished_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_post_metrics (
        id TEXT PRIMARY KEY,
        post_id TEXT NOT NULL,
        snapshot_date TEXT NOT NULL,
        impressions INTEGER NOT NULL DEFAULT 0,
        likes INTEGER NOT NULL DEFAULT 0,
        comments INTEGER NOT NULL DEFAULT 0,
        saves INTEGER NOT NULL DEFAULT 0,
        profile_visits INTEGER NOT NULL DEFAULT 0,
        dm_conversions INTEGER NOT NULL DEFAULT 0,
        engagement_score REAL,
        created_at TEXT NOT NULL,
        UNIQUE (post_id, snapshot_date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_template_scores (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        template_key TEXT NOT NULL,
        format TEXT,
        category TEXT,
        hour_bucket INTEGER,
        sample_count INTEGER NOT NULL DEFAULT 0,
        engagement_ema REAL NOT NULL DEFAULT 0,
        viral_score_ema REAL NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        UNIQUE (tenant_id, template_key, format, category, hour_bucket)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS linkedin_accounts (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        label TEXT NOT NULL,
        profile_url TEXT,
        purpose_scrape INTEGER NOT NULL DEFAULT 0,
        purpose_outreach INTEGER NOT NULL DEFAULT 0,
        purpose_publish INTEGER NOT NULL DEFAULT 0,
        health_score REAL NOT NULL DEFAULT 100,
        max_posts_per_day INTEGER NOT NULL DEFAULT 2,
        disabled_at TEXT,
        proxy_url TEXT,
        session_path TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS tenant_credits (
        tenant_id TEXT PRIMARY KEY,
        balance INTEGER NOT NULL DEFAULT 100,
        plan TEXT NOT NULL DEFAULT 'starter',
        stripe_customer_id TEXT,
        stripe_subscription_id TEXT,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS api_keys (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        name TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        key_prefix TEXT NOT NULL,
        scopes TEXT NOT NULL DEFAULT 'read,write',
        last_used_at TEXT,
        revoked_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS billing_events (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS outbox_events (
        id TEXT PRIMARY KEY,
        tenant_id TEXT,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        trace_id TEXT,
        idempotency_key TEXT,
        published_at TEXT,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS idempotency_keys (
        key TEXT PRIMARY KEY,
        tenant_id TEXT,
        response TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        actor_user_id TEXT,
        action TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS workspace_members (
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'editor',
        created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, user_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_usage_events (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        model TEXT NOT NULL,
        job_type TEXT,
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS analytics_events (
        id TEXT PRIMARY KEY,
        tenant_id TEXT,
        event_type TEXT NOT NULL,
        properties TEXT NOT NULL DEFAULT '{}',
        occurred_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS encrypted_secrets (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        secret_type TEXT NOT NULL,
        ciphertext TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (tenant_id, secret_type)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS content_media (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        draft_id TEXT,
        local_path TEXT,
        r2_key TEXT,
        mime_type TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
)
