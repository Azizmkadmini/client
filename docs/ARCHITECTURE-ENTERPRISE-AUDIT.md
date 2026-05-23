# AI Acquisition OS — Audit Enterprise & Architecture Scale

**Version :** 2.0 Enterprise Blueprint  
**Date :** Mai 2026  
**Audience :** CTO, Staff Engineers, Platform, Security, Growth  
**Principe :** évolution progressive du monorepo existant — **pas de rewrite**

**Documents liés :** [ARCHITECTURE-AI-ACQUISITION-OS.md](./ARCHITECTURE-AI-ACQUISITION-OS.md) · [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md) · [PHASE-3-5-COMPLETE.md](./PHASE-3-5-COMPLETE.md)

---

## Table des matières

1. [Audit complet du système actuel](#1-audit-complet-du-système-actuel)
2. [Enterprise architecture final](#2-enterprise-architecture-final)
3. [Distributed Browser Grid v2](#3-distributed-browser-grid-v2)
4. [Event-driven architecture](#4-event-driven-architecture)
5. [Advanced AI system](#5-advanced-ai-system)
6. [Vector database + memory](#6-vector-database--memory)
7. [Advanced analytics engine](#7-advanced-analytics-engine)
8. [Multi-tenant enterprise](#8-multi-tenant-enterprise)
9. [Billing & monetization](#9-billing--monetization)
10. [Observability & monitoring](#10-observability--monitoring)
11. [DevOps & infrastructure](#11-devops--infrastructure)
12. [Security hardening](#12-security-hardening)
13. [Cost optimization](#13-cost-optimization)
14. [Real LinkedIn risks](#14-real-linkedin-risks)
15. [Scaling roadmap](#15-scaling-roadmap)
16. [Final file structure](#16-final-file-structure)
17. [Final CTO recommendations](#17-final-cto-recommendations)

---

# 1. AUDIT COMPLET DU SYSTÈME ACTUEL

## 1.1 Vue d’ensemble

```txt
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ÉTAT ACTUEL (Mai 2026)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Clients: Next.js (apps/web) + Streamlit (dashboard/) — dual UI             │
│  API: FastAPI monolith (api/) — ~15 routers / legacy routes                 │
│  Workers: Python processes (workers/) — Redis LPUSH, pas Celery             │
│  Data: SQLite default + CSV leads + Postgres optionnel (strangler)          │
│  Browser: Playwright sync in-process + semaphore pool (2 slots)             │
│  Auth: JWT (SQLite users) + API key env + api_keys table                    │
│  Tests: ~124 pytest — bon signal qualité dev, pas charge                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Verdict global :** plateforme **MVP+ / early production** opérationnelle pour 1–10 workspaces. **Pas encore** enterprise multi-région sans investissement ciblé (browser grid, OLAP, RBAC, secrets, observabilité).

---

## 1.2 Backend (FastAPI)

| Aspect | État actuel | Bon | Manque / risque | Recommandation enterprise |
|--------|-------------|-----|-----------------|---------------------------|
| Structure | Monolith `api/main.py` + routers modulaires | Routers par domaine (content, billing, oauth) | Pas de séparation read/write, pas de versioning strict | `/api/v2` + BFF Next.js ; extraire services par domaine à la demande |
| Auth | JWT HS256, `api/deps.py` | API key + Bearer | Pas de refresh token, pas de rotation, users en SQLite | Auth service dédié, refresh, RS256, Postgres users |
| Multi-tenant | `tenant_id` dans JWT + colonnes PG | Fondation présente | **Pas de RLS Postgres**, filtres inconsistants SQLite | RLS + middleware tenant obligatoire sur chaque query |
| Rate limits | `services/rate_limit_engine.py` | Redis + fichier fallback | Pas de limites par plan billing | Quotas liés à `tenant_credits` + plan |
| Idempotency | Absent sur POST critiques | — | Double publish / double charge crédits | `Idempotency-Key` header + table `idempotency_keys` |
| API docs | OpenAPI auto | — | Pas de contrats SDK générés | OpenAPI → client TS dans `packages/sdk` |

**Bottleneck :** tout le trafic API + orchestration sur un seul process uvicorn — scaler horizontalement **possible** (stateless API) mais workers/browser **non**.

---

## 1.3 Frontend (Next.js + Streamlit)

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Next.js | `apps/web` — 9 pages | Login JWT, Recharts analytics | Pas Shadcn/TanStack Query utilisés, pas SSR auth guard | App Router + middleware auth + React Query |
| Streamlit | `dashboard/app.py` — ops lourd | Rapide pour admin interne | **Dual UI** = dette produit | Garder en **admin-only** (`ADMIN=true`) |
| Realtime | Aucun WebSocket | — | Jobs status = polling | SSE ou WS via Redis pub/sub |
| i18n | FR implicite | — | Pas de locale | `next-intl` si international |

---

## 1.4 Queues & workers

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Redis | `workers/queue.py` — LPUSH/BRPOP, DLQ, delayed (ZSET) | Retries, DLQ | Pas de priorités multi-queue, pas de visibility timeout | Celery/ARQ ou BullMQ bridge ; dead-letter replay UI |
| Workers | `run_all`, `runner`, `content_runner` | Séparation content/acquisition | **Subprocess scraper** encore possible (dashboard) | Jobs 100 % queue, jamais subprocess UI |
| Persistance jobs | `scraper_jobs` PG si configuré | Double-write amorcé | Redis = runtime truth, PG = audit partiel | Outbox pattern : job créé en PG puis enqueue |
| Scaling | 1 worker container | docker-compose.saas | Pas d’autoscale sur lag | HPA K8s sur `queue_depth` metric |

**Risque production :** worker crash mid-job → job perdu si pas persisté avant dequeue (améliorer : ack après traitement).

---

## 1.5 Browser system

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Playwright | Sync, in-process | Sessions séparées scrape/outreach/publish | **Pas de grid distribué** | Browser Grid v2 (section 3) |
| Pool | `browser_supervisor/pool.py` — Semaphore(2) + lock/channel | Évite OOM local | In-process only | Remote browsers (Browserless, custom grid) |
| Proxy | `proxy_url` sur compte, passé à launch | Fondation | Pas de pool proxy health, pas de rotation auto | Proxy manager service |
| Fingerprints | CDP / storage_state JSON | stable mode LI | Pas de fingerprint service central | Profils persistés chiffrés + affinity par compte |
| Telemetry | Logs fichiers | — | Pas de métriques ban/captcha | OTel spans par session browser |

**Bottleneck #1 à l’échelle :** 1 machine = ~2–5 browsers concurrents safe → **100 comptes LI = grid obligatoire**.

---

## 1.6 Account system

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Modèle | `linkedin_accounts` SQLite + PG schema | purpose_scrape/outreach/publish | `storage_state_enc` PG non utilisé | Chiffrer sessions en DB |
| Pool | `content/account_pool.py` | health_score, disable | Pas de round-robin distribué, pas de warmup state machine | Account lifecycle FSM |
| Sessions fichiers | `sessions/*.json` | Simple ops | **Secrets on disk**, pas backup chiffré | Vault + rotation |

---

## 1.7 OAuth LinkedIn

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Flow | `api/routers/oauth_linkedin.py` | authorize + callback | Token en `data/oauth_linkedin.json` **clair** | Vault, per-tenant, refresh token |
| Scopes | w_member_social, analytics | — | Approbation LinkedIn Marketing requise | Documenter scopes par feature flag |
| Analytics | `linkedin_metrics.py` — API + fallback simulate | Smart sync | API fragile selon urn/scopes | Normaliser urn storage à la publish |

---

## 1.8 Analytics

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Métriques content | `content_post_metrics` SQLite/PG | Snapshots journaliers | Pas de pipeline événements | Event ingestion → ClickHouse |
| Overview | `analytics/overview.py` | KPI simples | Pas cohortes, pas attribution multi-touch | OLAP + dbt models |
| Dashboard | Next Recharts basique | — | Pas temps réel | Metabase / embedded analytics |

---

## 1.9 AI generation

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Providers | ollama/openai/groq via `ai/generator.py`, `content/generation/` | Multi-provider config | Pas d’orchestration, pas de cache tokens | AI gateway (section 5) |
| Prompts | Inline / templates fichiers | Templates email | Pas de versioning prompts | Prompt registry + A/B |
| Memory | Absent | — | Pas de RAG | Vector store (section 6) |
| Coût | Non tracké par tenant | `cost_usd` colonne PG | Pas enforced | Metering + billing credits |

---

## 1.10 Publishing

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Méthode | Playwright DOM `content/publishing/linkedin.py` | Pool compte + proxy | **Fragile** (selectors) | API officielle où possible + fallback Playwright |
| Workflow | approve → publish sync/async | approval.py | Pas de preview feed | Composant preview + dry-run |
| Limites | `content_max_posts_per_day` | rate limit engine | Par tenant faible | Par compte LI + global tenant |

---

## 1.11 PostgreSQL

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| SSOT | Option `STORAGE_BACKEND=postgres` | Lead read/write PG, content PG store | Default SQLite ; pas de RLS | Postgres obligatoire prod |
| Migrations | SQL fichiers + sqlite migrate | `migrate_all`, `migrate_content` | Pas Flyway/Alembic versionné | Alembic ou golang-migrate |
| Scale | Single instance compose | — | Pas read replicas, pas partitioning | Partition `leads` par tenant_hash, réplicas read |

**SQL manquant enterprise :**

```sql
-- Row Level Security (à activer Phase Enterprise E1)
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON leads
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

---

## 1.12 Redis

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Usage | Queues + rate limits | Simple, efficace | Single DB index 0 | Cluster Redis, séparation cache/queue |
| Pub/sub | Non utilisé | — | Pas realtime UI | `job.progress` events |
| Persistence | Non configuré compose | — | Perte queue si crash Redis | AOF + replicas |

---

## 1.13 Monitoring & Docker

| Aspect | État | Bon | Manque | Enterprise |
|--------|------|-----|--------|------------|
| Logs | JSONL `logs/` | — | Pas Loki agent configuré | Promtail → Loki |
| Metrics | `/health`, `/metrics` basique | — | Pas Prometheus exporter | `prometheus-fastapi-instrumentator` |
| Tracing | Absent | — | Pas OTel | OTel SDK API + workers |
| Sentry | Mentionné docs, **non câblé** | — | Pas d’alerting | Sentry + PagerDuty |
| Docker | API image sans Playwright | compose modulaire | **Worker image incomplete** | `Dockerfile.worker` + chromium |
| CI | pytest + ruff | — | Pas e2e, pas deploy | GH Actions → staging/prod |

---

## 1.14 Synthèse risques production

| Risque | Sévérité | Probabilité | Mitigation prioritaire |
|--------|----------|-------------|------------------------|
| Ban LinkedIn massif | Critique | Haute | Grid + proxies + limites strictes |
| Fuite sessions/OAuth | Critique | Moyenne | Chiffrement + Vault |
| Fuite données cross-tenant | Critique | Moyenne | RLS + tests isolation |
| Worker single point | Haute | Haute | Multi replicas + DLQ replay |
| Publish DOM break | Haute | Haute | Monitoring + fallback manuel |
| Coût AI incontrôlé | Haute | Moyenne | Token metering + cache |
| Postgres non SSOT prod | Moyenne | Haute | Forcer PG en prod |
| Streamlit exposé public | Moyenne | Moyenne | Réseau interne only |

---

# 2. ENTERPRISE ARCHITECTURE FINAL

## 2.1 Principes

1. **Strangler Fig** — garder `c:\client` monorepo, extraire services seulement quand SLO ou équipe l’exigent.
2. **Postgres SSOT** — SQLite interdit en production multi-tenant.
3. **Browser workloads isolés** — jamais sur le même pod que l’API.
4. **Events pour tout ce qui est async** — queues = transport, bus = vérité métier long terme.
5. **Observability by default** — chaque job a `trace_id`, `tenant_id`.

## 2.2 Architecture cible (logical)

```txt
                                    ┌──────────────────────┐
                                    │   CDN (assets web)    │
                                    └──────────┬───────────┘
                                               │
┌──────────────────────────────────────────────▼──────────────────────────────────────────────┐
│                              EDGE / WAF (Cloudflare)                                         │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │
         ┌─────────────────────────────────────┼─────────────────────────────────────┐
         │                                     │                                     │
         ▼                                     ▼                                     ▼
┌─────────────────┐                 ┌─────────────────────┐              ┌──────────────────┐
│  Next.js (web)  │                 │  API Gateway         │              │  Webhook ingress  │
│  apps/web       │─── HTTPS ──────▶│  FastAPI → future   │◀── n8n/Stripe│  (signed)         │
│  + admin UI     │                 │  Kong/Traefik opt.   │              └────────┬─────────┘
└─────────────────┘                 └──────────┬──────────┘                       │
                                               │                                    │
                    ┌──────────────────────────┼──────────────────────────┐        │
                    │                          │                          │        │
                    ▼                          ▼                          ▼        ▼
           ┌──────────────┐          ┌──────────────┐          ┌──────────────┐  ┌─────────┐
           │ Auth service │          │ Core API      │          │ Billing svc  │  │ Notify  │
           │ JWT/OAuth/SSO│          │ (acquisition) │          │ Stripe       │  │ email/  │
           └──────┬───────┘          └──────┬───────┘          └──────┬───────┘  │ slack   │
                  │                         │                         │          └─────────┘
                  └─────────────────────────┼─────────────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
           ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
           │ AI service    │        │ Analytics svc │        │ Scheduler     │
           │ gen/score/RAG │        │ ingest/OLAP   │        │ cron/tick     │
           └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
                  │                       │                       │
                  └───────────────────────┼───────────────────────┘
                                          │
                                          ▼
                               ┌─────────────────────┐
                               │   Event Bus          │
                               │ Redis Streams → Kafka│
                               │ (phase progressive)  │
                               └──────────┬──────────┘
                                          │
          ┌───────────────────────────────┼───────────────────────────────┐
          │                               │                               │
          ▼                               ▼                               ▼
 ┌─────────────────┐            ┌─────────────────┐            ┌─────────────────┐
 │ Queue cluster    │            │ Browser Grid     │            │ ETL / Analytics  │
 │ workers (K8s)    │            │ Playwright nodes │            │ ClickHouse opt.  │
 └────────┬─────────┘            └────────┬─────────┘            └────────┬─────────┘
          │                               │                               │
          └───────────────────────────────┼───────────────────────────────┘
                                          ▼
                               ┌─────────────────────┐
                               │ PostgreSQL (primary) │
                               │ + read replicas      │
                               │ + R2 media           │
                               └─────────────────────┘
                                          │
                               ┌──────────┴──────────┐
                               ▼                     ▼
                        ┌───────────┐         ┌───────────┐
                        │ Redis      │         │ Vector DB   │
                        │ cluster    │         │ Qdrant      │
                        └───────────┘         └───────────┘
```

## 2.3 Mapping services → code actuel

| Service cible | Implémentation actuelle | Évolution |
|---------------|-------------------------|-----------|
| API Gateway | `api/main.py` | Garder ; ajouter Traefik + rate limit edge |
| Auth | `api/auth_jwt.py` | Extraire `services/auth/` |
| AI | `ai/`, `content/generation/` | `services/ai/` + gateway |
| Analytics | `analytics/`, `content/analytics/` | `services/analytics/` + pipeline |
| Queue | `workers/` | ARQ/Celery wrapper |
| Browser | `browser_supervisor/`, `utils/browser_session.py` | `browser-grid/` agent |
| Scheduler | `scripts/content_scheduler.py` | K8s CronJob + leader election |
| Billing | `billing/service.py` | Stripe webhooks hardened |
| Webhooks | `api/routers/webhooks.py` | Signature + replay protection |
| Admin | `dashboard/` Streamlit | Internal only |

---

# 3. DISTRIBUTED BROWSER GRID V2

## 3.1 Problème actuel

```txt
[API Pod] ──spawn──▶ Playwright (sync) ──▶ LinkedIn
     ▲                      │
     │                      └── bloque event loop / CPU / RAM
     └── max ~2 slots (browser_pool_max_slots)
```

## 3.2 Architecture cible

```txt
                    ┌─────────────────────────────────────┐
                    │     Browser Orchestrator API       │
                    │  POST /grid/sessions               │
                    │  POST /grid/jobs/{type}            │
                    └─────────────────┬───────────────────┘
                                      │
                    ┌─────────────────▼───────────────────┐
                    │        Redis / NATS job queue      │
                    │  queue:browser:scrape|publish      │
                    └─────────────────┬───────────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
 ┌──────────────┐              ┌──────────────┐              ┌──────────────┐
 │ Browser Node │              │ Browser Node │              │ Browser Node │
 │ EU-West      │              │ US-East      │              │ EU-West #2   │
 │ playwright   │              │ playwright   │              │ playwright   │
 │ + proxy 1:1  │              │ + proxy 1:1  │              │ + proxy 1:1  │
 └──────────────┘              └──────────────┘              └──────────────┘
```

## 3.3 Composants

| Composant | Rôle |
|-----------|------|
| **Orchestrator** | Assigne job → node avec affinity compte (`linkedin_account_id`) |
| **Browser Node** | Container `mcr.microsoft.com/playwright` + agent Python |
| **Session Store** | S3/R2 chiffré — storage_state par compte |
| **Proxy Manager** | Health check, rotation, géo = compte |
| **Telemetry Agent** | Expose métriques : crash_rate, captcha_rate, avg_duration |

## 3.4 Kubernetes strategy

```yaml
# infra/k8s/browser-node-deployment.yaml (extrait conceptuel)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: browser-worker
spec:
  replicas: 5  # HPA sur queue_depth_browser
  template:
    spec:
      containers:
        - name: agent
          image: aios/browser-grid:v1
          resources:
            requests: { memory: "2Gi", cpu: "1" }
            limits:   { memory: "4Gi", cpu: "2" }
          env:
            - name: REDIS_URL
              valueFrom: { secretKeyRef: { name: redis } } }
          volumeMounts:
            - name: dshm
              mountPath: /dev/shm
      volumes:
        - name: dshm
          emptyDir: { medium: Memory, sizeLimit: 1Gi }
```

**Session affinity :** label `account_id` sur job → scheduler préfère node ayant déjà chargé le profil (cache local `/sessions/{account_id}.json`).

**Fingerprint persistence :** ne pas régénérer contexte à chaque job ; TTL refresh 24h.

## 3.5 Failover

| Scénario | Action |
|----------|--------|
| Node crash | Job → DLQ → retry autre node |
| Captcha | Event `captcha.detected` → pause compte 24h |
| Proxy dead | Rotate proxy → retry 1x |
| LI checkpoint | Event `account.health_degraded` → notify user |

## 3.6 Migration depuis code actuel

1. Encapsuler `publish_text_post` / scrapers derrière interface `BrowserJobExecutor`.
2. Impl local = code actuel.
3. Impl remote = HTTP vers Browser Node.
4. Feature flag `BROWSER_GRID_MODE=local|remote`.

---

# 4. EVENT-DRIVEN ARCHITECTURE

## 4.1 Phase 0 (actuel) — Redis queues seulement

Jobs = payloads JSON dans Redis. Pas de journal d’événements métier.

## 4.2 Phase 1 — Redis Streams (compatible existant)

```txt
Producer (API/Worker) ──XADD──▶ stream:domain.events
Consumer groups ──▶ workers spécialisés
```

## 4.3 Phase 2 — Kafka / RabbitMQ (scale)

Quand : >500 événements/s, besoin replay 7j, analytics streaming.

## 4.4 Catalogue d’événements domaine

| Event | Producer | Consumers | Idempotency key |
|-------|----------|-----------|-----------------|
| `lead.discovered` | scraper worker | connector, analytics | `fingerprint` |
| `lead.enriched` | scraper | outreach queue, CRM webhook | `lead_id+version` |
| `outreach.sent` | bots | analytics, billing (credits) | `lead_id+channel+stage` |
| `outreach.replied` | webhook/manual | stop sequences | `lead_id` |
| `content.draft_created` | AI service | — | `draft_id` |
| `content.approved` | API | scheduler | `draft_id` |
| `content.scheduled` | API | scheduler tick | `post_id` |
| `content.published` | publish worker | analytics sync, webhooks | `post_id` |
| `content.metrics_synced` | analytics | optimization AI | `post_id+date` |
| `account.health_changed` | browser grid | pool manager, notify | `account_id` |
| `captcha.detected` | browser | account disable | `account_id+ts` |
| `billing.credits_consumed` | billing | — | `tenant_id+op+idempotency` |
| `job.failed` | any worker | DLQ UI, Sentry | `job_id` |

## 4.5 Envelope standard

```json
{
  "event_id": "uuid",
  "event_type": "content.published",
  "occurred_at": "2026-05-21T12:00:00Z",
  "tenant_id": "uuid",
  "trace_id": "otel-trace-id",
  "idempotency_key": "post_id",
  "payload": { "post_id": "...", "linkedin_url": "..." },
  "version": 1
}
```

## 4.6 Outbox pattern (recommandé)

```txt
API Handler
    │
    ├─ BEGIN TX (Postgres)
    │     ├─ UPDATE business row
    │     └─ INSERT outbox_events
    └─ COMMIT
         │
         ▼
Outbox Relay Worker ──publish──▶ Redis Stream / Kafka
```

Table :

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_outbox_unpublished ON outbox_events (created_at)
    WHERE published_at IS NULL;
```

## 4.7 Retry patterns

| Pattern | Usage |
|---------|--------|
| Exponential backoff | scrape, publish |
| Max 3 retries | outreach send |
| DLQ + manual replay | après 3 échecs |
| Circuit breaker | provider AI, proxy pool |

---

# 5. ADVANCED AI SYSTEM

## 5.1 Architecture

```txt
┌─────────────────────────────────────────────────────────────┐
│                    AI Orchestration Layer                    │
│  services/ai/orchestrator.py                                 │
│  - route request → provider                                  │
│  - fallback chain                                            │
│  - token budget per tenant                                   │
│  - cache (semantic + exact)                                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
     ┌──────────────────────┼──────────────────────┐
     ▼                      ▼                      ▼
┌─────────┐          ┌─────────┐          ┌─────────┐
│ OpenAI  │          │ Claude  │          │ Ollama  │
│ GPT-4o  │          │ Sonnet  │          │ local   │
└─────────┘          └─────────┘          └─────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ Prompt Registry  │
                   │ prompts/v{hash}  │
                   └─────────────────┘
```

## 5.2 Modules à ajouter (évolution `ai/` + `content/`)

| Module | Rôle | Fichier cible |
|--------|------|---------------|
| Prompt templates versionnés | Hooks, posts, CTA, outreach | `ai/prompts/registry.yaml` |
| Memory / RAG | Contexte marque + posts viraux | `ai/memory/retriever.py` |
| Hook scoring | Classifier engagement prédit | `ai/scoring/hooks.py` |
| CTA scoring | A/B prior | `ai/scoring/cta.py` |
| Rewriting | Variantes ton | `ai/rewrite/service.py` |
| Personalization | Lead → message LI | étendre `ai/generator.py` |
| Content clustering | Thèmes / calendrier auto | `ai/clustering/posts.py` |
| Engagement prediction | ML léger sur metrics | étendre `content/optimization/` |

## 5.3 Fallback chain

```txt
request → cache exact (hash prompt) → cache semantic (embedding)
       → primary provider (settings)
       → secondary provider
       → template static (zero cost)
```

## 5.4 Token optimization

- Truncate context (top-k chunks RAG).
- `max_tokens` par type de job.
- Batch generation nocturne (moins cher).
- Log `prompt_tokens`, `completion_tokens` → table `ai_usage_events`.

```sql
CREATE TABLE ai_usage_events (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INT,
    completion_tokens INT,
    cost_usd NUMERIC(10,6),
    job_type TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 6. VECTOR DATABASE + MEMORY

## 6.1 Stack recommandée

| Option | Quand |
|--------|--------|
| **Qdrant** (self-host K8s) | Coût maîtrisé, bon filtre metadata |
| **Pinecone** | Time-to-market, peu ops |
| **Weaviate** | Hybrid search + GraphQL |

**Recommandation CTO :** Qdrant pour coût + tenant filter natif.

## 6.2 Collections

| Collection | Contenu | Metadata |
|------------|---------|----------|
| `posts` | Corps posts publiés + hooks | tenant_id, engagement_score, format |
| `hooks` | Bibliothèque hooks | category, language |
| `leads` | Bio + notes enrichies | industry, tag |
| `brand_voice` | Docs marque uploadés | tenant_id |

## 6.3 Workflows

```txt
Post publié ──▶ embed ──▶ Qdrant
                         │
Nouveau sujet ──▶ retrieve top-k similar ──▶ prompt context
                         │
Duplicate check ──▶ cosine > 0.92 ──▶ warn user
```

## 6.4 Embedding pipeline

- Model : `text-embedding-3-small` (OpenAI) ou `bge-m3` local.
- Worker async : `content-published` event → embed job.
- Dimension : 1536 — index HNSW.

---

# 7. ADVANCED ANALYTICS ENGINE

## 7.1 Architecture lambda + OLAP

```txt
Sources                    Stream                    OLAP
────────                   ──────                    ────
API/Workers ──▶ events ──▶ Redis Stream ──▶ Flink/consumer ──▶ ClickHouse
Postgres (dims) ─────────────────────────────────────────────▶      │
                                                                    ▼
                                                          Metabase / Grafana
                                                          Next.js dashboards
```

## 7.2 Tables ClickHouse (exemple)

```sql
CREATE TABLE events_raw (
    event_time DateTime64(3),
    tenant_id UUID,
    event_type LowCardinality(String),
    properties String -- JSON
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (tenant_id, event_type, event_time);
```

## 7.3 KPI engine

| KPI | Formule | Fréquence |
|-----|---------|-----------|
| Publish success rate | published / attempts | hourly |
| Avg engagement | weighted likes+comments | daily |
| Lead → reply rate | replied / contacted | daily |
| Ban rate | accounts_disabled / active | daily |
| AI cost per post | sum(cost)/posts | daily |
| Queue lag p99 | redis lag metric | realtime |

## 7.4 Attribution

```txt
content.published ──▶ UTM / link in post ──▶ lead.discovered (notes match)
                                              └──▶ attribution: content_post_id
```

## 7.5 Cohort analysis

- Cohort = semaine d’inscription tenant.
- Retention = % tenants actifs (publish ou scrape) semaine N.

---

# 8. MULTI-TENANT ENTERPRISE

## 8.1 Modèle de données

```txt
Organization (billing)
    └── Workspace (tenant_id) — équipe
            └── Users (RBAC)
            └── LinkedIn Accounts
            └── Leads / Campaigns / Content
```

## 8.2 RBAC

| Role | Permissions |
|------|-------------|
| owner | all + billing |
| admin | users, accounts, campaigns |
| editor | content, publish (approval optional) |
| analyst | read analytics |
| viewer | read only |

Table :

```sql
CREATE TABLE workspace_members (
    workspace_id UUID REFERENCES tenants(id),
    user_id UUID,
    role TEXT NOT NULL,
    PRIMARY KEY (workspace_id, user_id)
);
```

## 8.3 Isolation

| Niveau | Mécanisme |
|--------|-----------|
| App | Middleware `SET app.tenant_id` |
| DB | Postgres RLS |
| Redis | Prefix keys `t:{tenant_id}:*` |
| R2 | Prefix `media/{tenant_id}/` |
| Browser | Session blob per account per tenant |
| AI | Token budget per tenant |

## 8.4 Enterprise SSO

- SAML/OIDC via Auth0/Clerk/WorkOS.
- Mapper `organization_id` → `tenant_id`.

## 8.5 Audit logs

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_user_id UUID,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    ip INET,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 8.6 Feature flags

- LaunchDarkly ou Flagsmith.
- Ex : `content.ai.claude`, `browser.grid.remote`, `analytics.clickhouse`.

---

# 9. BILLING & MONETIZATION

## 9.1 Architecture Stripe

```txt
Next.js ──▶ API billing ──▶ Stripe Checkout / Portal
                ▲                    │
                │                    ▼ webhooks
                └──── billing_events / tenant_credits
```

**Existant :** `billing/service.py` — mock + checkout basique.  
**À faire :** webhooks signés prod, usage records, portal, tax, invoices.

## 9.2 Modèle : subscriptions + usage

| Composant | Stripe object |
|-----------|---------------|
| Plan mensuel | Product + Price recurring |
| Crédits scrape | Metered usage |
| Crédits AI | Metered usage |
| Overages | Price tier |

## 9.3 Plans SaaS (prix indicatifs EU B2B)

| Plan | Prix/mois | Workspaces | Comptes LI | Crédits scrape/mois | Posts/mois | AI tokens | Support |
|------|-----------|------------|------------|---------------------|------------|-----------|---------|
| **Starter** | 79 € | 1 | 1 | 500 | 30 | 200k | Email |
| **Growth** | 199 € | 3 | 3 | 3 000 | 120 | 1M | Priority |
| **Agency** | 499 € | 10 | 15 | 15 000 | 500 | 5M | Slack |
| **Enterprise** | Sur devis | ∞ | ∞ | Custom | Custom | Custom | SLA 99.9% |

**Overages :** scrape +0,02 €/profil · AI +0,002 €/1k tokens · post extra +1 €.

## 9.4 Usage metering (workflow)

```txt
scrape job done ──▶ billing.credits_consumed (1 per profile)
AI generate ──▶ ai_usage_events + stripe usage record (batch hourly)
publish ──▶ check plan posts limit ──▶ reject or overage charge
```

## 9.5 Tables complémentaires

```sql
ALTER TABLE tenant_credits ADD COLUMN stripe_meter_scrape TEXT;
ALTER TABLE tenant_credits ADD COLUMN period_start TIMESTAMPTZ;
ALTER TABLE tenant_credits ADD COLUMN period_end TIMESTAMPTZ;
```

---

# 10. OBSERVABILITY & MONITORING

## 10.1 Stack cible

```txt
Apps (API/Workers/Browser)
    │
    ├── OpenTelemetry SDK ──▶ OTLP Collector
    │                              ├── Tempo (traces)
    │                              ├── Prometheus (metrics)
    │                              └── Loki (logs)
    │
    └── Sentry (errors + performance)
                │
                ▼
           Grafana (dashboards + alerts)
```

## 10.2 Métriques critiques

| Métrique | Type | Alerte |
|----------|------|--------|
| `browser_crash_total` | counter | >5/h/node |
| `queue_lag_seconds` | gauge | p99 > 300s |
| `linkedin_ban_events` | counter | >3/jour/tenant |
| `captcha_rate` | ratio | >10% jobs |
| `ai_request_duration_seconds` | histogram | p95 > 30s |
| `ai_tokens_total` | counter | budget 80% |
| `db_query_duration_seconds` | histogram | p95 > 500ms |
| `api_request_duration_seconds` | histogram | p99 > 2s |
| `publish_success_rate` | gauge | < 85% 1h |

## 10.3 Dashboards Grafana (minimum)

1. **Platform Overview** — API, DB, Redis.
2. **LinkedIn Operations** — bans, captchas, publish rate.
3. **Queue Health** — depth, DLQ, processing time.
4. **AI Costs** — tokens par tenant / jour.
5. **Business** — signups, MRR proxy, active tenants.

## 10.4 Intégration code (à ajouter)

```python
# api/main.py — pattern
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

**Existant :** `docker-compose.monitoring.yml` — Loki/Grafana profiles, **pas d’instrumentation app**.

---

# 11. DEVOPS & INFRASTRUCTURE

## 11.1 Environnements

| Env | Usage | Data |
|-----|-------|------|
| local | dev | SQLite OK |
| staging | QA, e2e | Postgres, Redis, mock LI |
| prod | clients | Postgres HA, Redis cluster, browser grid |

## 11.2 CI/CD (évolution `.github/workflows/`)

```txt
PR ──▶ lint (ruff) + pytest + typecheck
    ──▶ build images (api, worker, browser-grid, web)
    ──▶ push GHCR
main ──▶ deploy staging (auto)
tag v* ──▶ deploy prod (manual approval)
         ──▶ canary 10% → 50% → 100%
```

## 11.3 Infra as Code

```
infra/
├── terraform/
│   ├── modules/vpc
│   ├── modules/eks
│   ├── modules/rds
│   └── envs/prod
└── k8s/
    ├── helm/aios/
    │   templates/api.yaml
    │   templates/worker.yaml
    │   templates/browser-grid.yaml
    │   templates/web.yaml
    └── overlays/staging|prod
```

## 11.4 Autoscaling

| Workload | HPA metric |
|----------|------------|
| API | CPU 70% + RPS |
| Worker | `redis_queue_depth` |
| Browser grid | `browser_queue_depth` |
| Web | CPU |

## 11.5 Rollback

- Helm rollback revision N-1.
- Migrations DB : backward-compatible only (expand-contract).
- Feature flags désactivent nouvelles features sans redeploy.

---

# 12. SECURITY HARDENING

## 12.1 Priorités P0

| Item | Actuel | Cible |
|------|--------|-------|
| Sessions LI | `sessions/*.json` disk | AES-256-GCM en DB/S3, clé KMS |
| OAuth tokens | `data/oauth_linkedin.json` | Vault / Postgres encrypted |
| JWT secret | env, fallback api_key | KMS, rotation, RS256 |
| API keys | SHA256 hash ✓ | + scopes + IP allowlist |
| Tenant isolation | partiel | RLS obligatoire |
| Secrets CI | .env | GitHub Secrets + Vault |

## 12.2 API security

- WAF (Cloudflare) : OWASP, bot fight.
- Rate limit edge + app (`services/rate_limit_engine`).
- CORS strict sur API.
- Webhook signatures : Stripe, n8n HMAC.

## 12.3 Audit & compliance

- GDPR : export/delete tenant endpoint.
- Opt-out : `compliance/registry` → étendre Postgres.
- SOC2 path : audit logs + access reviews.

---

# 13. COST OPTIMIZATION

## 13.1 Estimation infra mensuelle (ordre de grandeur)

| Scale | Users | Infra/mois | Notes |
|-------|-------|------------|-------|
| MVP | 1–20 | 150–400 € | 1 VPS, Redis, PG small |
| Growth | 50–200 | 800–2 500 € | K8s small, 3 browser nodes |
| Scale | 500+ | 5 000–15 000 € | Multi-AZ, ClickHouse, grid |
| Enterprise | 1000+ | 15 000–50 000 € | SLA, SSO, dedicated proxies |

## 13.2 Postes de coût

| Poste | % typique | Optimisation |
|-------|-----------|--------------|
| Browser compute | 35–50% | Grid autoscale, autosleep nodes |
| AI tokens | 15–30% | Cache, small models, batch |
| Postgres | 5–10% | Replicas read, archive old leads |
| Proxies résidentiels | 10–25% | 1:1 account, recycle dead |
| Egress | 5% | CDN, compress |

## 13.3 Tactiques

- **Browser reuse** : même contexte 24h par compte.
- **Cold workers** : scale to zero nuit (scheduler off).
- **AI cache** : hash(prompt) → response 7j TTL Redis.
- **Queue batching** : scrape 50 profiles/job.
- **Storage lifecycle** : leads >2 ans → S3 Glacier export.

---

# 14. REAL LINKEDIN RISKS

## 14.1 Limites officielles

| Capacité | API officielle | Votre stack |
|----------|----------------|-------------|
| Publier posts | Marketing API (partenaire) | Playwright DOM |
| Analytics posts | Scopes analytics approuvés | OAuth partiel + simulate |
| Search people | Très restreint | Scrape UI |
| InMail / messages | Sales Navigator API | Playwright outreach |

**Conséquence :** vous opérez en **gray zone** pour scrape/publish DOM — acceptable pour outil interne, **risque légal/ToS** pour SaaS public multi-tenant.

## 14.2 Risques techniques

| Risque | Impact | Mitigation enterprise |
|--------|--------|----------------------|
| Ban compte | Perte canal acquisition | Pool, limits, warmup, 1 proxy/account |
| Checkpoint / CAPTCHA | Jobs bloqués | Détection + pause + alert |
| DOM change | Publish/scrape casse | Monitoring success rate, feature flags selectors versionnés |
| Fingerprinting | Ban silencieux | Stealth plugins, CDP, human delays (stable mode ✓) |
| Scale 100+ comptes | IP correlation | Proxy résidentiel dédié, région cohérente |

## 14.3 Stratégie anti-ban enterprise

```txt
1. Séparation stricte scrape / outreach / publish (déjà fait)
2. Budgets : CentralRateLimiter + per-account max
3. Warmup scheduler : J1-7 ramp-up nouveaux comptes
4. Health FSM : healthy → warned → paused → disabled
5. Human behavior : stable mode, long pauses (déjà partiel)
6. No parallel scrape + publish même compte
7. Alerting ban rate > seuil → auto-pause tenant
```

## 14.4 Recommandation produit

- Positionner **publish assisté** (human-in-the-loop) pour Enterprise compliance.
- Offrir **API-only mode** pour clients avec accès Marketing Developer.

---

# 15. SCALING ROADMAP

## Phase E0 — Production hardening (0–6 semaines)

**Objectif :** 1 prod stable, 50 tenants max.

- [ ] Postgres obligatoire prod + RLS
- [ ] Chiffrer OAuth + sessions
- [ ] OTel + Sentry + Prometheus
- [ ] `Dockerfile.worker` Playwright
- [ ] Outbox events table
- [ ] Idempotency publish/billing
- [ ] Streamlit admin-only (VPN)
- [ ] Stripe webhooks prod

## Phase E1 — Distributed workers (6–12 semaines)

- [ ] Celery/ARQ migration (garder contrat jobs)
- [ ] Worker HPA
- [ ] Browser Grid v1 (remote option)
- [ ] Proxy manager service
- [ ] Job ack pattern + PG job store SSOT

## Phase E2 — Analytics scale (12–18 semaines)

- [ ] Event ingestion Redis Streams
- [ ] ClickHouse ou Timescale
- [ ] Dashboards business Grafana
- [ ] Attribution pipeline

## Phase E3 — Enterprise SaaS (18–24 semaines)

- [ ] RBAC complet
- [ ] SSO SAML/OIDC
- [ ] Audit logs
- [ ] Feature flags
- [ ] Stripe plans + metering prod

## Phase E4 — AI optimization engine (24–30 semaines)

- [ ] AI gateway + usage metering
- [ ] Vector DB Qdrant
- [ ] Hook/CTA scoring
- [ ] Engagement prediction

## Phase E5 — International (30+ semaines)

- [ ] Multi-région browser nodes
- [ ] i18n Next.js
- [ ] Data residency EU/US

```txt
Timeline
────────
M0────E0────E1────E2────E3────E4────E5────▶
     harden  workers analytics ent.  AI    global
```

---

# 16. FINAL FILE STRUCTURE

Structure **évolution** du monorepo (pas nouveau repo) :

```txt
c:\client\
├── apps/
│   ├── web/                    # Next.js SaaS (client)
│   └── admin/                  # Streamlit → migrer ou garder internal
├── packages/
│   ├── sdk-ts/                 # OpenAPI generated client
│   └── shared-types/           # Events, DTOs
├── api/                        # FastAPI gateway (existant)
│   └── routers/
├── services/                   # Domain services (extraire progressivement)
│   ├── auth/
│   ├── billing/
│   ├── rate_limit_engine.py    # (existant)
│   ├── ai/
│   │   ├── orchestrator.py
│   │   ├── prompts/
│   │   └── memory/
│   └── analytics/
│       ├── ingest.py
│       └── kpi.py
├── acquisition/                # alias logique (scraper+connector+bots)
│   ├── scraper/
│   ├── connector/
│   ├── bots/
│   └── orchestrator/
├── content/                      # Content OS (existant)
├── analytics/                    # Cross-domain (existant)
├── workers/
│   ├── acquisition/
│   ├── content/
│   └── outbox_relay/
├── browser-grid/                 # NEW — remote browser agents
│   ├── agent/
│   ├── orchestrator/
│   └── Dockerfile
├── ai/                           # Legacy → wrap via services/ai
├── storage/
│   ├── postgres/
│   └── migrations/               # Alembic
├── infra/
│   ├── terraform/
│   ├── k8s/helm/aios/
│   └── docker/
│       ├── Dockerfile.api
│       ├── Dockerfile.worker
│       └── Dockerfile.browser
├── monitoring/
│   ├── grafana/dashboards/
│   ├── prometheus/rules/
│   └── loki/config/
├── config/
│   ├── rate_limits.yaml
│   └── feature_flags.yaml
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    ├── ARCHITECTURE-ENTERPRISE-AUDIT.md  # ce document
    └── runbooks/
```

---

# 17. FINAL CTO RECOMMENDATIONS

## 17.1 Prioriser (P0 — 90 jours)

| # | Initiative | Pourquoi |
|---|------------|----------|
| 1 | **Postgres SSOT + RLS** | Fondation multi-tenant sécurisée |
| 2 | **Secrets & chiffrement sessions** | Risque critique actuel |
| 3 | **Observability (OTel + Sentry)** | Debug prod impossible sans |
| 4 | **Browser worker image + isolation** | Scale + stabilité |
| 5 | **Stripe metering réel** | Monétisation |
| 6 | **Outbox + idempotency** | Fiabilité jobs |

## 17.2 Retarder (après PMF scale)

| Item | Raison |
|------|--------|
| Kafka | Redis Streams suffit jusqu’~500 evt/s |
| ClickHouse | Postgres + agrégats OK jusqu’~10M events |
| NestJS realtime | SSE depuis FastAPI suffit |
| Multi-région | Complexité prématurée |
| Full microservices split | Monolith modulaire OK |

## 17.3 Supprimer / réduire

| Item | Action |
|------|--------|
| Dual UI publique Streamlit + Next | Streamlit **internal only** |
| CSV leads en prod | Export-only |
| Subprocess scraper dashboard | 100 % queue |
| `platform/` package name collision | Déjà corrigé → `services/` |

## 17.4 Réécrire (ciblé, pas global)

| Module | Scope rewrite |
|--------|---------------|
| `workers/queue.py` | ARQ/Celery adapter, garder interface |
| `content/publishing/linkedin.py` | Executor abstraction + selector versioning |
| `billing/service.py` | Stripe prod patterns |
| `leads/store.py` | Repository pattern + PG only |

## 17.5 Scaler en premier

1. Browser grid (coût mais unavoidable).
2. Worker pool horizontal.
3. Postgres read replicas.
4. Redis cluster.

## 17.6 Coûteux — décisions conscientes

| Décision | Coût | Alternative cheap |
|----------|------|---------------------|
| Proxies résidentiels | €€€ | Moins de comptes, human-in-loop |
| Browser grid K8s | €€ | Moins de parallélisme |
| ClickHouse | € | Postgres materialized views |
| Pinecone | € | Qdrant self-host |

## 17.7 Risqué — mitiger

| Risque | Mitigation |
|--------|------------|
| ToS LinkedIn SaaS | Legal review + disclaimers + API mode enterprise |
| Cross-tenant leak | RLS + tests + pen test |
| AI cost blowout | Hard caps per plan |
| DOM publish break | Canary selectors + alerts |

## 17.8 MVP vs Enterprise

| Capability | MVP (aujourd’hui) | Enterprise (E3+) |
|------------|-------------------|------------------|
| Tenants | 1 default + JWT | Workspaces + RBAC |
| Browser | Local 2 slots | Grid 50+ |
| Analytics | Recharts + simulate | ClickHouse + real LI API |
| Billing | Mock + basic | Metered + portal |
| SSO | Email/password | SAML |
| SLA | Best effort | 99.9% |

---

## Annexes

### A. Workflow publish enterprise (cible)

```txt
User ──▶ Approve draft ──▶ schedule post
                              │
Scheduler tick ──▶ outbox: content.scheduled
                              │
Worker ──▶ pick account (pool) ──▶ browser grid job
                              │
                    success ──▶ content.published ──▶ sync metrics
                    fail    ──▶ retry / DLQ ──▶ notify user
```

### B. Checklist go-live production

- [ ] `STORAGE_BACKEND=postgres` en prod
- [ ] Secrets dans Vault, pas `.env` sur disque
- [ ] Redis AOF + backup PG daily
- [ ] Sentry DSN + alertes PagerDuty
- [ ] Rate limits par plan actifs
- [ ] Backup `sessions` chiffré
- [ ] WAF + TLS terminé
- [ ] Runbook ban LinkedIn documenté
- [ ] GDPR delete tenant testé

### C. Références internes

| Document | Contenu |
|----------|---------|
| [PHASE-3-5-COMPLETE.md](./PHASE-3-5-COMPLETE.md) | Livré phases 3–5 |
| [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md) | Migration acquisition |
| [PROJET-STATUT.md](./PROJET-STATUT.md) | Ops quotidien |

---

**Document maintenu par :** Platform Engineering  
**Prochaine revue :** après Phase E0 (hardening) ou changement majeur infra
