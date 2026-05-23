# Production Hardening Audit — AI Acquisition OS

> **Implémentation appliquée (queue BRPOPLPUSH, browser pool, workers, security, PG)** — [`PRODUCTION-HARDENING-IMPLEMENTED.md`](./PRODUCTION-HARDENING-IMPLEMENTED.md)

**Type :** revue Staff Engineer / SRE — basée sur le code réel (`c:\client`)  
**Prérequis :** phases E0–E5 livrées, 128+ tests  
**Principe :** stabilité et coût réels — pas de couches enterprise décoratives

**Correctifs code livrés dans cette passe :**
- `services/linkedin_risk.py` — Risk Engine v2 + intégration worker/publish
- `services/pg_tenant.py` — fix RLS (`SET LOCAL` sur la bonne connexion)
- `content/publishing/linkedin.py` — `page.close()`, risk gate
- `services/events.py` — `XADD MAXLEN`, `XTRIM`
- `services/ai/orchestrator.py` — budget tokens, routing cheap model
- `storage/postgres_indexes.sql` — indexes manquants

---

## Table des matières

1. [Production hardening — findings](#1-production-hardening--findings)
2. [Remove fake enterprise](#2-remove-fake-enterprise)
3. [Scalability limits](#3-scalability-limits)
4. [Cost analysis](#4-cost-analysis)
5. [Playwright hardening](#5-playwright-hardening)
6. [LinkedIn Risk Engine v2](#6-linkedin-risk-engine-v2)
7. [Postgres hardening](#7-postgres-hardening)
8. [Redis hardening](#8-redis-hardening)
9. [Analytics scale v2](#9-analytics-scale-v2)
10. [AI cost optimization v2](#10-ai-cost-optimization-v2)
11. [Security hardening](#11-security-hardening)
12. [Observability v2](#12-observability-v2)
13. [Disaster recovery](#13-disaster-recovery)
14. [SRE playbooks](#14-sre-playbooks)
15. [Architecture cleanup](#15-architecture-cleanup)

---

# 1. Production hardening — findings

## Légende

| Sévérité | Signification |
|----------|----------------|
| P0 | Incident prod probable |
| P1 | Dégradation / coût / data risk |
| P2 | Dette à planifier |

## 1.1 API FastAPI (sync dans async)

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| A1 | **Publish sync bloque event loop** | `api/routers/content.py` `sync=true` → `execute_content_job` → Playwright | P0 — API freeze sous charge | `sync=false` par défaut ; ou `run_in_executor` |
| A2 | **RLS Postgres cassé** | `api/middleware.set_postgres_tenant` ouvre connexion, SET, ferme — variable **non visible** aux autres connexions | P1 — fuite cross-tenant si on croit RLS actif | `services/pg_tenant.tenant_cursor()` sur chaque requête PG |
| A3 | **Pas de pool HTTP** | `httpx.post` one-shot dans AI/OAuth | P2 — latence | `httpx.Client` singleton |
| A4 | **Idempotency race** | deux POST parallèles même clé | P1 — double publish | `INSERT ... ON CONFLICT` + lock Redis `SETNX idem:{key}` |

**Code fix RLS (utiliser partout où lecture leads PG) :**

```python
from services.pg_tenant import tenant_cursor

with tenant_cursor(tenant_id) as cur:
    cur.execute("SELECT * FROM leads WHERE status = %s", ("new",))
    rows = cur.fetchall()
```

**Code fix publish async (API) :**

```python
# Défaut PublishRequest
class PublishRequest(BaseModel):
    sync: bool = False  # était True — bloquant
```

## 1.2 Workers & queues

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| W1 | **Orphan jobs** | `BRPOP` mais blob `GET` vide (TTL 7j expiré) | P2 — job perdu silencieusement | Log + métrique `orphan_queue_entries` |
| W2 | **Retry storm** | `requeue` sans jitter global | P1 — thundering herd | `delay + random(0, 30)` |
| W3 | **Pas d'ack atomique** | job retiré de queue avant succès | P0 — perte si crash après BRPOP | Pattern: `RPOPLPUSH` vers `processing` list |
| W4 | **Double worker** | `run_all` + `runner` + `content_runner` même Redis | P1 — jobs dupliqués si mal isolés | Une queue par type ou consumer group |
| W5 | **Subprocess 4h timeout** | `workers/jobs.py` scrape CLI | P1 — zombie process | Timeout 30–60 min + kill tree |

**Architecture queue recommandée (minimal change) :**

```txt
LPUSH queue:pending → worker BRPOP
                 → RPUSH queue:processing
                 → on success: LREM processing + save done
                 → on fail: requeue delayed
```

## 1.3 Playwright

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| B1 | **Nouveau browser par publish** | `sync_playwright()` chaque job | P0 — RAM 300–800 Mo/pic | Pool long-lived (1 browser/worker process) |
| B2 | **Page non fermée** (avant fix) | `linkedin.py` | P1 — memory leak | `page.close()` dans `finally` ✅ |
| B3 | **API sync dans worker OK** | workers dédiés | — | Ne jamais Playwright dans uvicorn |
| B4 | **Zombie Chromium** | crash sans `close_session` | P1 | `try/finally` + supervisor kill >30min |

## 1.4 Redis

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| R1 | **Stream infini** | `aios:events` sans MAXLEN (avant fix) | P1 — OOM Redis | `XADD MAXLEN ~100000` ✅ |
| R2 | **Pas de XPENDING reclaim** | consumer crash | P1 — messages bloqués | `XAUTOCLAIM` cron |
| R3 | **DLQ sans trim** | `outreach:dead-letter` | P2 | `LTRIM` + alert si len>1000 |
| R4 | **Nouveau client/redis call** | chaque opération | P2 | Connection pool `redis.ConnectionPool` |

## 1.5 Postgres

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| D1 | **Pas de tenant_id sur leads** (schema legacy) | `postgres_schema.sql` | P1 | migration + backfill ✅ enterprise sql |
| D2 | **LeadStore full table scan** | `fetch_all_leads_df` | P1 à 100k+ leads | pagination + index ✅ `postgres_indexes.sql` |
| D3 | **Double-write silencieux** | `_sync_postgres` swallow errors | P2 | log warning + métrique |
| D4 | **JSONB outbox = double stockage** | payload = envelope complet dans outbox | P2 | payload léger |

## 1.6 Events / duplication

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| E1 | **Double emit** | `outbox.emit` + `analytics.ingest` + `content_jobs` publish | P2 | Une seule source: outbox only |
| E2 | **Outbox relay 5s** | perte si Redis down entre PG write et relay | P2 | relay dans même TX ou dual-write accepté |

## 1.7 AI cost leaks

| ID | Problème | Où | Risque | Fix |
|----|----------|-----|--------|-----|
| AI1 | **Pas de cap tenant** (avant fix) | generator/content | P1 | `ai_daily_token_cap_per_tenant` ✅ |
| AI2 | **Cache fichier sans TTL** | `data/ai_cache/` | P2 | cleanup cron 7j |
| AI3 | **Génération sync API** | content router generate | P1 | queue job |

---

# 2. Remove fake enterprise

## Garder (utile en prod)

| Module | Raison |
|--------|--------|
| `services/outbox.py` + relay | Fiabilité events |
| `services/idempotency.py` | Publish/billing |
| `services/crypto.py` + `secrets_store` | OAuth |
| `services/linkedin_risk.py` | Anti-ban réel |
| `services/rate_limit_engine.py` | Quotas |
| `browser_grid/executor.py` | Scale browsers |
| `postgres_indexes.sql` | Perf |

## Simplifier / fusionner

| Module | Action |
|--------|--------|
| `api/routers/enterprise.py` GDPR stubs | → une route admin, pas un router entier |
| `api/middleware.set_postgres_tenant` | **Supprimer** — remplacer par `pg_tenant` |
| `analytics/ingest` + `outbox.emit` | **Un seul chemin** : outbox → consumer → analytics table |
| `browser_grid/agent.py` | Garder seulement si `BROWSER_GRID_MODE=remote` |
| Double UI Streamlit + Next | Streamlit **VPN internal only** |

## Ne pas ajouter maintenant

- Kafka, ClickHouse déployés
- Service auth séparé
- Vector DB
- NestJS realtime

**Règle :** si ça ne résout pas un SLO ou un incident observé → pas de code.

---

# 3. Scalability limits

Hypothèses machine worker : **8 vCPU, 16 GB RAM**, Playwright chromium headless.

## Capacité théorique

| Ressource | Limite conservatrice | Bottleneck |
|-----------|---------------------|------------|
| Playwright concurrent | **2–3** (`browser_pool_max_slots=2`) | RAM ~1 GB/browser |
| Workers processes | 4–8 (1/job chacun) | CPU |
| Redis ops/sec | 50k+ (single instance) | Rarement le bottleneck |
| Postgres writes/sec | 500–2k (simple inserts) | Disque IOPS |
| API RPS (sans Playwright) | 200–500 | uvicorn workers |
| Tenants (logical) | 1000+ | DB size + isolation |
| Events/sec | 1k (Redis stream) | Consumer throughput |

## Tableau par charge

| Métrique | 1 worker | 4 workers | Grid 10 nodes |
|----------|----------|-----------|---------------|
| Publish LI/heure | 20–40 | 80–120 | 400+ |
| Scrape profiles/heure | 100–200 | 400–800 | 2000+ |
| Leads en DB | 1M OK avec index | — | — |
| Analytics events/jour | 500k | 2M | 10M+ (→ ClickHouse) |

## RAM budget (1 host)

```txt
OS + Redis + Postgres client     ~1 GB
API uvicorn x2                   ~1 GB
Worker x2 + Playwright x2          ~4–6 GB
Marge                            ~2 GB
```

**Au-delà :** séparer `api`, `worker`, `browser-grid` sur hosts différents.

---

# 4. Cost analysis

Prix indicatifs EU 2026 (VPS/cloud moyen).

## 100 users actifs (~10% heavy)

| Poste | Coût/mois |
|-------|-----------|
| API VPS 4 vCPU | 40 € |
| Worker VPS 8 vCPU | 80 € |
| Postgres managed small | 50 € |
| Redis 1 GB | 20 € |
| Proxies résidentiels (50 IP) | 150 € |
| OpenAI (~5M tokens) | 80 € |
| Monitoring | 20 € |
| **Total** | **~440 €** |
| Revenu (mix Starter/Growth) | ~8k € |
| **Marge brute** | **~95%** |

## 1 000 users

| Poste | Coût/mois |
|-------|-----------|
| K8s 3 nodes | 400 € |
| Postgres HA | 200 € |
| Redis | 60 € |
| Browser grid 5 nodes | 500 € |
| Proxies 200 IP | 600 € |
| AI 50M tokens | 800 € |
| R2 + egress | 100 € |
| **Total** | **~2 660 €** |
| Revenu moyen 120 €/user | 120k € |

## 10 000 users

| Poste | Coût/mois |
|-------|-----------|
| Infra scale | 15–25k € |
| AI + proxies | 10–15k € |
| **Total** | **25–40k €** |
| Revenu | ~1.2M € |

**Point critique coût :** proxies + browser compute + AI tokens — pas Postgres.

---

# 5. Playwright hardening

## Architecture cible (1 worker process)

```txt
Worker process start
    └── launch Browser once (chromium)
            └── reuse BrowserContext per channel/account
                    └── new Page per job
                            └── page.close() always
```

## Checklist

- [x] `page.close()` finally
- [ ] Browser singleton per worker (`utils/browser_pool_persistent.py` à ajouter)
- [ ] Max job duration 10 min watchdog
- [ ] `context.tracing` on failure only (S3)
- [ ] Disable images/fonts (`route`) pour scrape

## Fingerprint

- Garder `storage_state` par compte
- Ne pas mélanger scrape/publish context
- CDP mode doc pour ops avancées

---

# 6. LinkedIn Risk Engine v2

**Implémenté :** `services/linkedin_risk.py`

## Signaux

| Signal | Action |
|--------|--------|
| Quota journalier <15% | score +40, throttle |
| 3+ failures /1h | score +25 |
| 5+ failures | circuit open 30 min |
| health < 50 | score +20 |
| captcha in error | disable account, Redis flag 24h |

## Intégration

- `workers/runner.py` — gate avant job
- `content/publishing/linkedin.py` — gate avant publish

## API (optionnel)

```http
GET /api/v1/platform/risk?channel=linkedin
```

---

# 7. Postgres hardening

## Indexes (livré)

`storage/postgres_indexes.sql` — appliquer via migrate-postgres.

## Partitioning (à 1M+ leads)

```sql
-- Par mois sur created_at
CREATE TABLE leads_2026_05 PARTITION OF leads
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

## Retention

| Table | Rétention | Archive |
|-------|-----------|---------|
| analytics_events | 90j | S3 parquet |
| audit_logs | 1 an | cold storage |
| scraper_jobs | 30j | delete |
| leads | client-defined | export CSV |

## Vacuum

- `autovacuum` ON
- `analytics_events` : `VACUUM ANALYZE` weekly cron

## Slow queries à surveiller

```sql
SELECT * FROM leads;  -- sans tenant_id + limit
SELECT * FROM content_posts WHERE status = 'scheduled';  -- index scheduled ✅
```

---

# 8. Redis hardening

## Streams

```python
# Déjà fait
XADD aios:events MAXLEN ~ 100000

# Cron quotidien
EventBus().trim_stream()
```

## Consumer groups

```bash
XINFO GROUPS aios:events
XPENDING aios:events aios-workers
XAUTOCLAIM aios:events aios-workers c1 60000 0 COUNT 100
```

## DLQ policy

```python
# workers/queue.py — à ajouter
def trim_dlq(max_len=5000):
    client.ltrim(DLQ_KEY, 0, max_len - 1)
```

## Retry policy

| Job type | max_attempts | backoff |
|----------|--------------|---------|
| scrape | 3 | 30s, 120s, 600s |
| publish | 2 | 300s, 1800s |
| outreach | 2 | 60s, 300s |

---

# 9. Analytics scale v2

## Pipeline actuel (OK jusqu’~500k events/j)

```txt
emit_event → outbox PG + Redis Stream
    → event_consumer → analytics_events table
    → kpi_engine / Grafana
```

## Migration ClickHouse (>5M events/j)

```txt
Redis Stream → consumer → ClickHouse INSERT
Postgres garde dimensions (tenants, users)
Metabase/Grafana sur ClickHouse
```

## Pre-aggregation (sans ClickHouse)

```sql
CREATE MATERIALIZED VIEW daily_tenant_kpis AS
SELECT tenant_id, date_trunc('day', occurred_at) AS day,
       event_type, count(*)
FROM analytics_events
GROUP BY 1, 2, 3;
```

---

# 10. AI cost optimization v2

**Livré partiel :**

| Tactique | Status |
|----------|--------|
| Exact cache (hash prompt) | ✅ `data/ai_cache/` |
| Token cap / tenant / day | ✅ `AI_DAILY_TOKEN_CAP_PER_TENANT` |
| Route groq for hooks/cta | ✅ `_route_provider` |
| Template fallback | ✅ |
| Semantic cache | ❌ — Qdrant plus tard |
| Prompt dedup batch | ❌ |

## Estimation tokens

```python
est = len(prompt) // 4  # avant appel
```

## Routing rules

```txt
tokens > 3000 → template
job hook/cta + groq key → groq
else → configured provider (openai/ollama)
budget exceeded → template
```

---

# 11. Security hardening

| Risque | Sévérité | Mitigation |
|--------|----------|------------|
| OAuth token plaintext legacy file | P0 | `secrets_store` + rotate |
| Redis sans AUTH | P0 | `requirepass` + TLS |
| Postgres public | P0 | private network only |
| SSRF via scraper URL | P1 | allowlist domains |
| Prompt injection in user topic | P1 | sanitize + system prompt guard |
| Webhook n8n unsigned | P1 | HMAC header verify |
| RBAC bypass open mode | P1 | force API_KEY in prod |
| Tenant isolation SQLite | P1 | Postgres only prod |
| Playwright sandbox | P2 | run as non-root user in Docker |

## Prod checklist

```env
API_KEY=required
STORAGE_BACKEND=postgres
SECRETS_ENCRYPTION_KEY=...
REDIS_URL=redis://:password@redis:6379/0
```

---

# 12. Observability v2

## Métriques Prometheus (existant `/metrics/prometheus`)

**À ajouter (custom) :**

```python
browser_jobs_total{status}
queue_depth{queue}
linkedin_risk_score
ai_tokens_total{tenant}
publish_duration_seconds
```

## Dashboards Grafana (panels)

1. **Platform** — API latency p95, error rate, RPS
2. **Queues** — pending, processing, DLQ length
3. **LinkedIn** — risk score, ban rate, publish success
4. **AI** — tokens/day, cost USD, cache hit rate
5. **Postgres** — connections, slow queries

Voir `monitoring/grafana/aios-overview.json` (squelette).

## Tracing

```env
OTEL_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
```

Instrument workers : span par job_id.

---

# 13. Disaster recovery

## RPO / RTO cibles

| Composant | RPO | RTO |
|-----------|-----|-----|
| Postgres | 5 min (PITR) | 30 min |
| Redis | 1 min (AOF) | 15 min |
| Sessions LI | 24h (backup S3) | 1h |
| R2 media | 0 (replicated) | — |

## Backup

```bash
pg_dump -Fc aios > backup.dump
aws s3 cp backup.dump s3://backups/
redis-cli BGSAVE
tar czf sessions.tar.gz sessions/
```

## Restore

```bash
pg_restore -d aios backup.dump
# Redis: replay AOF
# Workers: drain DLQ manually
```

## Queue recovery

1. Lister DLQ `outreach:dead-letter`
2. Re-enqueue jobs valides
3. Purger jobs >7j

---

# 14. SRE playbooks

Voir `docs/runbooks/` :

| Runbook | Fichier |
|---------|---------|
| Redis down | `runbooks/redis-down.md` |
| Postgres slow | `runbooks/postgres-slow.md` |
| Browser grid crash | `runbooks/browser-grid.md` |
| LinkedIn restrictions | `runbooks/linkedin-ban.md` |
| AI provider outage | `runbooks/ai-outage.md` |

## Incident template

1. Ack alert
2. Check Grafana dashboard
3. Identify tenant impact
4. Mitigate (throttle, pause workers)
5. Root cause + postmortem

---

# 15. Architecture cleanup

## Structure maintenable (cible 6 mois)

```txt
api/           # HTTP only — no Playwright
workers/       # all blocking work
services/      # domain logic (risk, outbox, ai, billing)
content/       # content domain
acquisition/   # scraper+connector+bots (move gradual)
browser_grid/  # optional remote
storage/       # SQL schemas only
monitoring/    # grafana/prometheus
docs/          # runbooks + architecture
```

## Dependency rules

```txt
api → services → storage
workers → services → storage
services → NOT api
content → services (risk) OK
```

## Naming

- `execute_*` = workers
- `get_*` / `list_*` = read
- `emit_*` = events

---

## Prochaines actions (ordre recommandé)

1. **P0** — `PublishRequest.sync = False` par défaut
2. **P0** — Redis AUTH + Postgres private
3. **P1** — `RPOPLPUSH` processing queue
4. **P1** — Browser singleton per worker
5. **P1** — Supprimer double event path
6. **P2** — ClickHouse quand analytics_events > 5M rows

---

**Document maintenu par :** Platform / SRE  
**Référence code :** commit courant `c:\client`
