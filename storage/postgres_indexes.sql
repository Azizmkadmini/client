-- Indexes production — exécuter après schémas principaux

CREATE INDEX IF NOT EXISTS idx_leads_tenant_status ON leads (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_leads_tenant_created ON leads (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scraper_jobs_status ON scraper_jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_tenant_time ON analytics_events (tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON outbox_events (created_at) WHERE published_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_content_posts_tenant_status ON content_posts (tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_content_posts_scheduled ON content_posts (status, scheduled_at) WHERE status = 'scheduled';
