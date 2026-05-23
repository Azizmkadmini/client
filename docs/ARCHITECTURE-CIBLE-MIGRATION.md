# Architecture cible & plan de migration — Acquisition Engine (`c:\client`)

> **Plateforme unifiée :** voir [ARCHITECTURE-AI-ACQUISITION-OS.md](./ARCHITECTURE-AI-ACQUISITION-OS.md) pour le module **AI LinkedIn Content OS** (génération, calendrier, publication, analytics contenu).

**Version:** 1.0  
**Date:** 21 mai 2026  
**Rôle:** Audit senior + roadmap de refactor (pas de rewrite from scratch)  
**Public:** CTO / lead dev / ops

---

## Résumé exécutif

Le projet actuel est un **monolithe Python mature** (scraper LinkedIn/Instagram/Web, connector, outreach SMTP, dashboard Streamlit, API FastAPI légère) qui **fonctionne en production locale** mais **n’est pas structuré comme un SaaS distribué** (Apollo/Clay).

| Dimension | Aujourd’hui (`c:\client`) | Cible (12–18 mois, progressif) |
|-----------|---------------------------|--------------------------------|
| UI | Streamlit (`dashboard/`) | Next.js + design system (portail spec existe, non codé) |
| API | FastAPI minimal (`api/main.py`) | FastAPI domain API + auth + webhooks |
| Queue | JSON + SQLite (`bot/leads_queue.json`) | Redis + BullMQ |
| DB | SQLite + CSV | PostgreSQL (CSV = export seulement) |
| Scraper | Playwright sync in-process / subprocess | Workers isolés + browser pool |
| Sessions | `sessions/*.json` | Vault chiffré + account pool |
| Observabilité | JSONL logs | Loki + Grafana + Sentry + traces |

**Principe directeur :** *Strangler Fig Pattern* — extraire progressivement les modules existants derrière des interfaces, sans couper la production actuelle.

---

## 1. État actuel du système (diagnostic)

### 1.1 Cartographie des composants réutilisables

```
c:\client\
├── config.py                 # ✅ Garder — centraliser secrets via Vault plus tard
├── scraper/                  # ✅ Cœur métier — extraire en workers
│   ├── collectors.py         # ⚠️ Monolithe ~920 lignes — découper par canal
│   ├── linkedin_*.py         # ✅ Bonne modularisation LI
│   ├── linkedin_stability.py # ✅ Politique anti-ban — promouvoir en "rate engine"
│   ├── web/                  # ✅ Web Bing→sites OK ; LI/IG web non branchés CLI
│   ├── profile_cache.py      # ✅ → table `lead_enrichment_cache` Postgres
│   ├── site_contact_fetch.py # ✅ → worker `company-enrichment`
│   └── email_pipeline.py     # ✅ → queue `outreach-ingest`
├── bots/                     # ✅ Réutiliser logique — isoler sessions d'envoi
├── connector/                # ✅ Pipeline clean/enqueue — 1er candidat service
├── orchestrator/             # ⚠️ Remplacer par scheduler + queues
├── leads/store.py            # ⚠️ CSV+SQLite → repository Postgres
├── dashboard/                # 🔄 Streamlit temporaire — remplacer par Next.js
├── api/main.py               # 🔄 Étendre — point d'entrée SaaS
├── utils/browser_session.py  # ✅ Base account manager — refactor nommé
└── sessions/                 # 🔄 → `linkedin_accounts.storage_state_enc`
```

### 1.2 Flux de données actuel

```
┌─────────────┐     subprocess      ┌──────────────┐
│ Streamlit   │ ──────────────────► │ scraper.cli  │
│ dashboard   │                     │ (Playwright) │
└─────────────┘                     └──────┬───────┘
                                           │ CSV
┌─────────────┐     run.py           ┌─────▼────────┐     JSON/SQLite   ┌─────────────┐
│ FastAPI     │ ───────────────────► │ Connector    │ ───────────────► │ LeadStore   │
│ (optionnel) │                      │ Pipeline     │                  │ + bots SMTP │
└─────────────┘                      └──────────────┘                  └─────────────┘
```

**Problèmes structurels :**

| # | Symptôme | Cause racine | Risque prod |
|---|----------|--------------|-------------|
| R1 | LinkedIn checkpoint / ban | Volume + Playwright headless + session partagée scrape/send | Perte compte |
| R2 | Runs dashboard bloquants (heures) | Subprocess monolithique, timeout 4h | UX / ops |
| R3 | Mêmes 3 leads web | Bing requêtes faibles + CSV append | Données stales |
| R4 | Google CSE 403 | API fermée nouveaux comptes | Pas de SERP Google |
| R5 | Memory / crash navigateur | Pas de browser pool / recycle | Worker OOM |
| R6 | Doublons leads | CSV + SQLite + queue JSON | Outreach double |
| R7 | Pas de retry distribué | Pas de queue | Jobs perdus |

### 1.3 Ce qui fonctionne et ne doit pas être jeté

- **Extraction LinkedIn** : `linkedin_contacts.py`, three-dots, website supplement.
- **Mode stable** : `linkedin_stability.py`, `timing.py`.
- **Web scrape** : `web/search_engine.py` (Bing Playwright), `sites.py`.
- **Enrichissement email** : `contact_recovery.py`, guess MX, `site_contact_fetch.py`.
- **Compliance** : `compliance/registry.py`, opt-out.
- **Templates email** : `templates/email/`, warm-up scripts.
- **Tests** : `tests/test_scraper.py` — filet de sécurité migration.

---

## 2. Architecture cible (vision SaaS)

### 2.1 Vue globale (microservices logiques — peut rester monorepo au début)

```
                         ┌─────────────────────────────────────┐
                         │         Next.js (App Router)         │
                         │  Campaigns · Leads · Workers · Admin  │
                         └──────────────────┬──────────────────┘
                                            │ REST + WebSocket
                         ┌──────────────────▼──────────────────┐
                         │           API Gateway (FastAPI)        │
                         │  Auth · Tenants · Campaigns · Webhooks │
                         └──────────────────┬──────────────────┘
            ┌──────────────────────────────┼──────────────────────────────┐
            │                              │                              │
   ┌────────▼────────┐           ┌─────────▼─────────┐           ┌────────▼────────┐
   │  Redis + BullMQ │           │   PostgreSQL       │           │  Secrets Vault  │
   │  Job queues     │           │   SSOT données     │           │  (sessions)     │
   └────────┬────────┘           └────────────────────┘           └─────────────────┘
            │
   ┌────────┴────────────────────────────────────────────────────────────┐
   │                         Worker tier                                  │
   │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐ │
   │  │ linkedin-    │ │ enrichment-  │ │ smtp-verify- │ │ outreach-   │ │
   │  │ scrape-worker│ │ worker       │ │ worker       │ │ worker      │ │
   │  └──────┬───────┘ └──────────────┘ └──────────────┘ └─────────────┘ │
   │         │                                                            │
   │  ┌──────▼───────────────────────────────────────────────────────┐  │
   │  │              Browser Grid (Playwright + stealth)                │  │
   │  │  Pool · Context per account · CDP option · Memory recycle       │  │
   │  └────────────────────────────────────────────────────────────────┘  │
   └──────────────────────────────────────────────────────────────────────┘
            │
   ┌────────▼────────┐     ┌─────────────────┐
   │ Proxy Manager   │     │ Account Manager │
   │ (residential)   │     │ health + warmup │
   └─────────────────┘     └─────────────────┘
```

### 2.2 Communication inter-services

| De → Vers | Protocole | Payload |
|-----------|-----------|---------|
| UI → API | HTTPS REST | CRUD campaigns, leads, jobs |
| UI → API | WebSocket | `job.progress`, `worker.health`, `captcha.detected` |
| API → Queue | Redis LPUSH | Job JSON (idempotent key) |
| Worker → DB | SQLAlchemy async | Upsert leads, job state |
| Worker → Browser Grid | gRPC/HTTP interne | `AcquireContext(account_id)` |
| Workers → Loki | HTTP push | Structured logs |
| Workers → Sentry | SDK | Exceptions, performance |

### 2.3 Découpage microservices (phases — pas jour 1)

| Service logique | Code source initial | Priorité |
|-----------------|---------------------|----------|
| `api` | `api/main.py` + nouvelles routes | P0 |
| `connector-service` | `connector/*` | P1 |
| `scraper-linkedin-worker` | `scraper/collectors.py` + `linkedin_*` | P0 |
| `scraper-web-worker` | `scraper/web/*` | P1 |
| `enrichment-worker` | `site_contact_fetch`, `contact_recovery` | P1 |
| `verify-worker` | nouveau (SMTP handshake) | P2 |
| `outreach-worker` | `bots/*` | P2 |
| `scheduler` | `orchestrator/runner.py` | P2 |
| `browser-supervisor` | extrait de `utils/browser_session.py` | P0 |

**Phase 0 (monorepo compat):** tout reste importable ; workers = `python -m workers.linkedin` derrière Redis.

---

## 3. Plan de migration par phases

### PHASE 1 — Stabilisation critique (semaines 1–4) — *sans changer la stack*

**Objectif :** production stable avec le code actuel.

| Action | Fichiers | Effort | Impact |
|--------|----------|--------|--------|
| Séparer sessions scrape / send | `sessions/linkedin-scrape.json` vs `linkedin-outreach.json` | S | ↓ ban |
| CDP par défaut doc + `.env` | `BROWSER_CONNECTION_MODE=cdp` | S | ↓ checkpoint |
| Limiter dashboard : mots-clés, limites | `dashboard/app.py` | S | ↓ timeout |
| Web : pas de filtre pays | déjà fait `sites.py` | — | ↓ erreurs geo |
| Bing Playwright seul SERP | `SCRAPER_WEB_SEARCH_PROVIDER=bing` | S | web OK |
| Commande health pré-run | `scripts/check_*` | S | ops |
| Feature flag `SCRAPER_EMAIL_PIPELINE` off jusqu'à stable | `.env` | S | — |

**Livrable :** playbook ops mis à jour, 0 régression tests pytest.

### PHASE 2 — Extraction queue + jobs (semaines 5–10)

**Objectif :** fin des subprocess dashboard 4h ; jobs rejouables.

```
┌──────────┐    enqueue     ┌─────────────┐    consume    ┌─────────────────┐
│ FastAPI  │ ─────────────► │ Redis       │ ────────────► │ worker-linkedin │
│ POST/job │                │ BullMQ      │               │ (ancien collect)│
└──────────┘                └─────────────┘               └─────────────────┘
```

| Queue BullMQ | Ancien équivalent | Retry |
|--------------|-------------------|-------|
| `linkedin-search` | `_collect_linkedin` search phase | 3x exp backoff |
| `profile-scrape` | enrich profile | 5x |
| `company-enrichment` | `site_contact_fetch` | 3x |
| `web-discovery` | `web-run` | 3x |
| `outreach-send` | `bots/email.py` | 2x |
| `dead-letter` | — | manual replay |

**Compat layer :** `scraper/cli.py` peut encore tourner en mode `--sync` pour debug.

**Migration données :** CSV inchangé en sortie Phase 2 ; ingest async vers SQLite puis Postgres Phase 3.

### PHASE 3 — PostgreSQL SSOT (semaines 11–16)

**Strangler :** `leads/store.py` devient façade :

```python
# pseudo — compat
class LeadStore:
    def __init__(self, backend: Literal["csv", "postgres"] = "csv"):
        ...
```

- `STORAGE_BACKEND=postgres` en staging.
- Double-write CSV + Postgres 2 semaines.
- Puis CSV = export uniquement.

### PHASE 4 — Anti-ban & account pool (semaines 17–24)

- Multi-comptes LinkedIn table `linkedin_accounts`.
- Proxy binding 1:1.
- Health score auto-disable.
- Rate limit engine central (remplace `logs/rate_limits/*.json`).

### PHASE 5 — Frontend Next.js + SaaS (semaines 25–40)

- Remplacer Streamlit par app Next.js (portail client multi-tenant).
- Multi-tenant, billing, API keys.
- Streamlit reste **admin interne** optionnel.

---

## 4. LinkedIn Account System

### 4.1 État actuel

| Élément | Implémentation |
|---------|----------------|
| Stockage | `sessions/linkedin.json` (Playwright storage state) |
| Login | `outreach.py login` — interactive, `--from-browser`, `--cdp` |
| Validation | `linkedin_stability.validate_linkedin_session_file()` |
| Limites | `config.py` : `linkedin_daily_max`, stable mode caps |
| Multi-compte | **Absent** |

### 4.2 Cible

```sql
CREATE TABLE linkedin_accounts (
  id UUID PRIMARY KEY,
  tenant_id UUID NOT NULL,
  label TEXT NOT NULL,
  storage_state_enc BYTEA,          -- chiffré AES-GCM
  fingerprint_json JSONB NOT NULL,  -- stable par compte
  proxy_id UUID REFERENCES proxies(id),
  health_score INT DEFAULT 100,
  status TEXT CHECK (status IN ('active','warmup','cooldown','restricted','disabled')),
  daily_action_budget INT DEFAULT 25,
  last_used_at TIMESTAMPTZ,
  captcha_count_24h INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.3 Account Pool Manager (extrait de `browser_session.py`)

```python
# packages/accounts/pool.py — NOUVEAU, appelle l'existant
class LinkedInAccountPool:
    def acquire(self, *, purpose: Literal["scrape", "outreach"]) -> AccountLease:
        """Round-robin + health_score + cooldown + proxy affinity."""
        ...

    def release(self, lease: AccountLease, *, outcome: JobOutcome) -> None:
        """Met à jour health_score, captcha_count, cooldown."""
        ...
```

### 4.4 Warmup system

| Jour | Actions autorisées |
|------|-------------------|
| 1–3 | Feed scroll only, 5–10 min |
| 4–7 | 5 profile views/day |
| 8–14 | 10 searches, 5 enrich |
| 15+ | full budget avec monitoring |

**Migration :** compte email actuel = statut `warmup_complete` manuel en DB.

### 4.5 Fingerprint persistence

- **Règle :** 1 fingerprint JSON stable / compte (UA, viewport, timezone, locale, WebGL noise seed).
- **Ne pas** rotate par session (LinkedIn détecte l'incohérence).
- Implémentation : playwright-extra + `fingerprint-generator` stocké en DB.

---

## 5. Anti-Detection System

### 5.1 Comment LinkedIn détecte

| Signal | Présent aujourd'hui ? | Mitigation cible |
|--------|----------------------|------------------|
| `navigator.webdriver` | Partiellement masqué | playwright-extra stealth |
| Headless Chromium | Oui si `SCRAPER_HEADLESS=true` | CDP Chrome réel ou headless=new+stealth |
| Vitesse clic/scroll | Stable mode aide | Humanization engine |
| IP datacenter | Sans proxy résidentiel | Proxy résidentiel sticky |
| Volume/heure | Caps en config | Rate limit engine dynamique |
| Session partagée scrape+send | **Oui** | Sessions séparées P1 |
| Fingerprint drift | Non géré | fingerprint_json stable |

### 5.2 Humanization Engine (nouveau package)

```
packages/humanization/
├── delays.py          # Gaussian delays, long pauses
├── mouse.py           # Bézier moves, hesitation
├── scroll.py          # Variable velocity, read simulation
├── typing.py          # Per-char delay sur champs rares
└── session_rhythm.py  # Tab switch, idle, feed-only blocks
```

Brancher **avant** chaque `page.goto` / `click` dans `linkedin_profile.py` via decorator `@humanized`.

### 5.3 Adaptive Scraping Engine

```python
# Si captcha_rate_1h > 0.1 → throttle 50%
# Si timeout_rate > 0.2 → reduce concurrency
# Si health_score < 40 → pause account 24h
```

Connecté aux métriques Redis / Prometheus.

---

## 6. Browser Cluster System

### 6.1 État actuel

- 1 browser / run, fermé en fin de `collect_live`.
- Pas de recycle mémoire mid-run.
- Crash = tout le job échoue.

### 6.2 Cible

```
BrowserSupervisor
├── max_browsers = 3 per worker VM
├── max_contexts_per_browser = 5
├── max_pages_per_context = 20 → recycle context
└── memory_threshold_mb = 1200 → restart browser
```

```python
# packages/browser/supervisor.py
class BrowserSupervisor:
    async def with_page(self, account_id: str, fn: Callable[[Page], Awaitable[T]]) -> T:
        context = await self._get_context(account_id)
        page = await context.new_page()
        try:
            return await fn(page)
        finally:
            await self._maybe_recycle(context)
```

**Migration :** wrapper sync Playwright existant d'abord ; async Phase 4.

---

## 7. Scraping Pipeline (cible unifiée)

```
                    ┌─────────────────┐
                    │ Campaign config │
                    │ (query, geo,    │
                    │  limit, app)    │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ LinkedIn path  │  │ Web path       │  │ Instagram path │
│ (existant)     │  │ (sites.py)     │  │ (collectors)   │
└───────┬────────┘  └───────┬────────┘  └───────┬────────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
                 ┌──────────────────────┐
                 │ Profile extraction   │
                 │ nom, role, company,  │
                 │ location, li_url     │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │ Company enrichment   │
                 │ domain, site crawl   │
                 │ (site_contact_fetch) │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │ Email generation     │
                 │ (contact_recovery)   │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │ Verification         │
                 │ MX + SMTP optional   │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │ Lead scoring         │
                 │ + dedup              │
                 └──────────┬───────────┘
                            ▼
                 ┌──────────────────────┐
                 │ PostgreSQL + events  │
                 └──────────────────────┘
```

### 7.1 État par étape

| Étape | Fichier actuel | Statut | Action migration |
|-------|----------------|--------|------------------|
| LinkedIn Search | `linkedin_search.py` | ✅ | Worker job |
| Profile Extract | `linkedin_profile.py` | ✅ | + selector recovery |
| Company Detect | `linkedin_company.py` | ✅ | — |
| Website Scrape | `site_contact_fetch.py` | ✅ | Limiter pages en job config |
| Email Guess | `contact_recovery.py` | ✅ | — |
| SMTP Verify | MX only | ⚠️ | Nouveau `verify-worker` |
| Lead Scoring | `email_pipeline` score | ⚠️ | Table `lead_scores` |
| Storage | CSV | ⚠️ | Postgres |

---

## 8. Profile Extraction — champs & selectors

### 8.1 Champs cibles

| Champ | Source actuelle | Fallback |
|-------|-----------------|----------|
| full_name | `ScraperRecord.nom` | title parse |
| first/last | **Absent** | split + AI cleanup |
| role | `poste` | headline selectors |
| company | `entreprise` | experience block |
| company_linkedin | partiel | `/company/` href |
| company_domain | `domaine` | site_contact_fetch |
| location | `pays` + about | geo filters |
| linkedin_url | `link` | canonical /in/ |

### 8.2 Selector Recovery System

```
packages/scraper/selectors/
├── linkedin_profile.yaml   # primary selectors
├── linkedin_company.yaml
├── fallbacks[]             # ordered list
├── semantic.py             # get_by_role, aria
└── ai_recovery.py          # LLM + DOM snippet → selector suggestion
```

**DOM diffing :** nightly job compare snapshot DOM vs baseline → alert Slack.

**Migration :** extraire selectors hardcodés de `linkedin_contacts.py` vers YAML progressivement.

---

## 9. Company Enrichment

| Capacité | Aujourd'hui | Cible |
|----------|-------------|-------|
| Domain from LI | `extract_website_from_linkedin_contact_panel` | ✅ |
| Google/Bing domain | web discovery non branché LI | Brancher ou API SERP payante |
| Site crawl | `site_contact_fetch` jusqu'à 55 pages | Configurable per campaign |
| Metadata | limité | JSON `company_metadata` |

---

## 10. Email Generation Engine

**Existant :** `guess_emails_from_name_and_domain`, patterns prenom.nom, MX check.

**Cible :**

```python
@dataclass
class EmailCandidate:
    email: str
    pattern: str  # first.last, f.last, etc.
    confidence: float  # 0-1
    mx_valid: bool
    smtp_status: Literal["valid","risky","invalid","catch_all","unknown"]
```

| Pattern | Détection |
|---------|-----------|
| first@ | si email trouvé matche |
| first.last@ | default B2B |
| f.last@ | startup |
| firstlast@ | rare |

**Merge strategy :** garder le meilleur score ; ne pas écraser email vérifié SMTP.

---

## 11. SMTP Verification System

**Aujourd'hui :** MX via `dns.resolver` ; pas de handshake SMTP.

**Cible worker `verify-worker` :**

1. MX lookup (existant)
2. SMTP RCPT TO (timeout 8s, greylisting aware)
3. Catch-all probe `random123@domain`
4. Disposable domain list
5. Résultat → table `email_verifications`

**Ne pas** hammer SMTP — queue dédiée,  concurrency 5.

---

## 12. PostgreSQL — schéma cible (extrait)

```sql
-- Tenants (Phase 5)
CREATE TABLE tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  plan TEXT DEFAULT 'starter',
  credits_balance INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE campaigns (
  id UUID PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id),
  name TEXT NOT NULL,
  channel TEXT CHECK (channel IN ('linkedin','instagram','web','email')),
  config_json JSONB NOT NULL,
  status TEXT DEFAULT 'draft',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE companies (
  id UUID PRIMARY KEY,
  domain TEXT UNIQUE,
  name TEXT,
  metadata_json JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE leads (
  id UUID PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id),
  campaign_id UUID REFERENCES campaigns(id),
  company_id UUID REFERENCES companies(id),
  linkedin_url TEXT,
  linkedin_url_hash TEXT GENERATED ALWAYS AS (encode(sha256(linkedin_url::bytea), 'hex')) STORED,
  full_name TEXT,
  first_name TEXT,
  last_name TEXT,
  role TEXT,
  location TEXT,
  email TEXT,
  email_status TEXT,
  email_confidence REAL,
  whatsapp TEXT,
  score INT,
  enrichment_status TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tenant_id, linkedin_url_hash)
);

CREATE INDEX idx_leads_campaign ON leads(campaign_id);
CREATE INDEX idx_leads_email ON leads(email) WHERE email IS NOT NULL;
CREATE INDEX idx_leads_domain ON leads(company_id);

CREATE TABLE jobs (
  id UUID PRIMARY KEY,
  tenant_id UUID,
  queue TEXT NOT NULL,
  state TEXT CHECK (state IN ('pending','running','retrying','cooldown','captcha','failed','completed')),
  payload_json JSONB,
  attempts INT DEFAULT 0,
  last_error TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ
);

-- Voir aussi: linkedin_accounts, proxies, email_verifications,
-- outreach_sequences, audit_logs, suppression_list
```

**Migration depuis SQLite :** script `scripts/migrate_sqlite_to_postgres.py` — one-shot + vérif counts.

---

## 13. Queue System (BullMQ)

### 13.1 Architecture

```
Redis
├── bull:linkedin-search
├── bull:profile-scrape
├── bull:company-enrichment
├── bull:email-generation
├── bull:smtp-verification
├── bull:outreach
└── bull:dead-letter
```

### 13.2 Job state machine

```
pending → running → completed
              ↓
           retrying (backoff) → failed → dead-letter
              ↓
           captcha → cooldown (account) → pending
```

### 13.3 Exemple worker Node/TS ou Python RQ

**Recommandation pragmatique :** BullMQ nécessite Node ; alternative Python = **RQ** ou **Celery** pour réutiliser le code Playwright existant sans réécrire workers.

| Option | Pro | Con |
|--------|-----|-----|
| BullMQ (spec user) | Écosystème riche | Workers TS séparés du scraper Py |
| Celery + Redis | Python natif | Moins "SaaS modern" |
| ARQ (async Redis) | Python async | Bon pour FastAPI |

**Décision migration :** Phase 2 = **Celery ou ARQ** (Python) avec même contrat queues ; BullMQ si équipe full-stack TS.

```python
# workers/tasks/linkedin.py — Celery example
@celery.task(bind=True, max_retries=5, default_retry_delay=60)
def scrape_linkedin_profile(self, job_id: str, profile_url: str, account_id: str):
    from scraper.linkedin_profile import enrich_linkedin_profile_fast_email
    # ... existing code wrapped
```

---

## 14. CAPTCHA & Checkpoint System

### 14.1 Détection (existant + étendre)

| Type | Détection actuelle | Action |
|------|-------------------|--------|
| LinkedIn checkpoint | `linkedin_stability`, URL | pause account 24–48h |
| LinkedIn authwall | idem | relogin CDP |
| Google CAPTCHA | `search_engine.py` | fallback Bing |
| Instagram reCAPTCHA | `instagram_login.py` | session import |
| Arkose | **Absent** | DOM + network hooks |

### 14.2 Workflow

```
captcha detected
    → job.state = captcha
    → emit websocket alert
    → pause queue for account_id (Redis key)
    → optional: human-in-the-loop UI (admin resolve)
    → on resolve: rotate proxy OR refresh session
    → resume with reduced rate
```

**Providers (optionnel) :** 2Captcha / CapSolver — **déconseillé LinkedIn** (ToS) ; préférer humain + CDP.

---

## 15. Health Scoring

| Entité | Signaux | Seuil disable |
|--------|---------|---------------|
| Account | captcha/h, success rate, restrictions | score < 30 |
| Proxy | timeout %, blocks | score < 40 |
| Worker | crash/h, memory | auto restart |

```python
health_score = 100
health_score -= captcha_rate_24h * 40
health_score -= failure_rate * 30
health_score -= restriction_events * 50
```

Auto-disable dans `AccountPool.acquire()`.

---

## 16. Rate Limit Engine

Remplace `utils/behavior.py` + fichiers JSON.

```yaml
# config/rate_limits.yaml
linkedin:
  scrape:
    profiles_per_hour: 12
    profiles_per_day: 80
    jitter_pct: 25
  outreach:
    messages_per_day: 25
```

**Dynamic throttle :** Adaptive engine modifie multipliers.

---

## 17. Proxy System

| Aujourd'hui | Cible |
|-------------|-------|
| Aucun proxy codé | Table `proxies`, binding account |
| — | Residential sticky session |
| — | Geo match account country |

**Pourquoi cheap proxies échouent :** IP datacenter blacklistée par LinkedIn → checkpoint immédiat.

**Migration :** optionnel Phase 4 ; démarrage possible sans proxy si CDP Chrome local.

---

## 18. Outreach System

**Existant :** `bots/email.py`, `linkedin.py`, `instagram.py`, templates, `daily_send.py`, warm-up scripts.

**Cible :**

- Séquences table `outreach_sequences` + steps
- Inbox rotation multi-SMTP
- Bounce webhook → suppression list
- SPF/DKIM check avant campagne (DNS lookup)

**Compat :** `EmailBot.run_batch` reste ; wrapper enqueue `outreach-send` jobs.

---

## 19. Monitoring & Observability

| Aujourd'hui | Cible |
|-------------|-------|
| `logs/*.jsonl` | Loki labels: tenant, job, account |
| — | Grafana dashboards (ban rate, success) |
| — | Sentry SDK workers + API |
| FastAPI `/metrics` | Prometheus exporter |

**Dashboards Grafana :**

1. Scraping success / captcha rate
2. Queue depth / DLQ size
3. Browser memory / crash
4. SMTP verify rate
5. Email send / bounce

---

## 20. Docker Architecture

### 20.1 `docker-compose.yml` cible (évolution de l'existant)

```yaml
services:
  api:
    build: ./apps/api
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis]

  worker-linkedin:
    build: ./apps/workers
    command: celery -A workers worker -Q linkedin-search,profile-scrape
    deploy:
      replicas: 2
    shm_size: "2gb"  # Playwright

  worker-enrichment:
    build: ./apps/workers
    command: celery -A workers worker -Q company-enrichment,email-generation

  worker-outreach:
    build: ./apps/workers
    command: celery -A workers worker -Q outreach

  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine

  frontend:
    build: ./apps/frontend
    ports: ["3000:3000"]

  loki:
    image: grafana/loki:2.9.0
  grafana:
    image: grafana/grafana:10.2.0

volumes:
  pgdata:
```

**Aujourd'hui :** `Dockerfile` = API only ; Playwright absent image → **nouveau** `Dockerfile.worker` avec `playwright install chromium`.

---

## 21. Frontend — Product & UX Architecture

### 21.1 État actuel vs cible

| Aujourd'hui | Cible |
|-------------|-------|
| Streamlit 3 colonnes scrape | Next.js App Router |
| Pas de WebSocket | Socket.io / Pusher / WS FastAPI |
| Tables pandas | TanStack Table virtualized |

### 21.2 Arborescence Next.js

```
apps/frontend/
├── app/
│   ├── (dashboard)/
│   │   ├── campaigns/
│   │   ├── leads/
│   │   ├── workers/
│   │   ├── accounts/
│   │   └── settings/
│   ├── admin/
│   └── api/                    # BFF routes optionnelles
├── components/ui/              # shadcn
├── features/
│   ├── campaigns/
│   ├── leads/
│   ├── scraper-live/           # WebSocket progress
│   └── admin/
├── stores/                     # Zustand
├── hooks/
└── lib/api.ts                  # TanStack Query
```

### 21.3 Pages prioritaires (remplacent Streamlit)

| Page Streamlit actuelle | Page Next.js |
|-------------------------|--------------|
| Scraper 3 colonnes | `/campaigns/new` wizard |
| Résultats CSV | `/leads` explorer |
| Pipeline | `/campaigns/[id]/pipeline` |
| Email send | `/outreach/send` |
| Logs | `/workers/logs` live |

### 21.4 Design tokens (extrait)

```css
/* globals.css — dark-first enterprise */
--background: 222 47% 5%;
--primary: 217 91% 60%;
--success: 142 76% 36%;
--warning: 38 92% 50%;
--destructive: 0 84% 60%;
```

### 21.5 Realtime

```
FastAPI --publish--> Redis pub/sub --subscribe--> Next.js WS gateway
Events: job.progress, job.completed, captcha.detected, account.health
```

---

## 22. Multi-tenant, Billing, API (Phase 5)

- `tenant_id` sur toutes tables.
- Credits : scrape=1 credit/profile, verify=0.1, send=1.
- API keys : `api_keys` table, rate limit Redis.
- Webhooks : `lead.found`, `email.verified`, `campaign.completed`.
- GDPR : opt-out existant → `suppression_list` Postgres + export/delete tenant.

---

## 23. Technical Debt Register

| ID | Dette | Priorité | Fix |
|----|-------|----------|-----|
| TD-01 | `collectors.py` monolith | P0 | Split par canal |
| TD-02 | Subprocess scraper dashboard | P0 | Queue jobs |
| TD-03 | CSV SSOT | P1 | Postgres strangler |
| TD-04 | Session partagée scrape/send | P0 | 2 fichiers session |
| TD-05 | `collect_web_linkedin` dead code | P2 | Wire ou delete |
| TD-06 | Pas proxy layer | P3 | Phase 4 |
| TD-07 | Pas SMTP verify | P2 | verify-worker |
| TD-08 | Streamlit prod UI | P3 | Next.js Phase 5 |
| TD-09 | shell=True orchestrator | P1 | Structured jobs |
| TD-10 | 100+ env vars | P2 | Config service |

---

## 24. Matrice composant (format demandé)

Pour chaque bloc : **État actuel → Problèmes → Risques → Solution → Priorité → Difficulté → Impact → Refactor → Compat**

### Exemple : LinkedIn Scraper

| Champ | Valeur |
|-------|--------|
| État actuel | `collectors._collect_linkedin` + modules `linkedin_*`, stable mode |
| Problèmes | Monolithe, sync blocking, session partagée, pas de queue |
| Risques prod | Ban, timeout dashboard, data loss on crash |
| Solution | Celery jobs + account pool + browser supervisor |
| Priorité | **P0** |
| Difficulté | M (6–8 semaines partiel) |
| Impact perf | +stabilité, +parallélisme limité |
| Refactor progressif | Wrapper job autour `enrich_linkedin_*` sans réécrire |
| Compat | `scraper.cli run` reste en mode legacy |

*(Répéter mentalement pour chaque section du prompt — document complet ci-dessus.)*

---

## 25. Arborescence cible monorepo

```
c:\client\                          # repo existant — évolution
├── apps/
│   ├── api/                        # FastAPI (migrate api/main.py)
│   ├── frontend/                   # Next.js NEW
│   └── workers/                    # Celery/BullMQ consumers NEW
├── packages/                       # shared libs NEW
│   ├── accounts/
│   ├── browser/
│   ├── humanization/
│   ├── scraper-core/               # move scraper/ progressivement
│   └── enrichment/
├── scraper/                        # LEGACY — imports stable jusqu'à move
├── bots/
├── connector/
├── dashboard/                      # LEGACY Streamlit — deprecated Phase 5
├── docker/
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   └── Dockerfile.worker
├── monitoring/
│   ├── grafana/dashboards/
│   └── loki/config.yml
├── docs/
│   └── ARCHITECTURE-CIBLE-MIGRATION.md  # ce document
└── scripts/
    └── migrate_*.py
```

---

## 26. Exemples code (migration-safe)

### 26.1 Wrapper job LinkedIn (sans réécrire enrich)

```python
# apps/workers/tasks/linkedin.py
from scraper.models import ScraperRecord, SearchRequest
from scraper.collectors import collect_live  # legacy import OK

def run_linkedin_campaign_job(payload: dict) -> dict:
    request = SearchRequest(**payload["request"])
    records = collect_live(request)  # inchangé Phase 2
    return {"written": len(records), "records": [r.to_row() for r in records]}
```

### 26.2 FastAPI enqueue

```python
# apps/api/routes/jobs.py
@router.post("/campaigns/{id}/run")
async def enqueue_campaign(id: UUID, body: RunConfig):
    job = queue.enqueue("linkedin-search", {"campaign_id": str(id), **body.dict()})
    return {"job_id": job.id}
```

### 26.3 Docker Compose extrait

Voir section 20.1.

---

## 27. Best Practices — erreurs à éviter

| Erreur | Pourquoi ça casse | Ce projet |
|--------|-------------------|-----------|
| Rewrite total | 6 mois sans prod | **Interdit** |
| BullMQ jour 1 sans workers Py | Double stack | Celery d'abord |
| Headless massif | CAPTCHA | CDP + stable |
| Un compte LI pour tout | Ban | Pool + split session |
| Ignorer tests existants | Régressions | pytest CI obligatoire |
| Google CSE nouveaux comptes | 403 | Bing/SERP API payante |

---

## 28. Prochaines actions immédiates (cette semaine)

1. **`.env` prod :** `SCRAPER_WEB_SEARCH_PROVIDER=bing`, sessions scrape/send séparées.
2. **Valider pytest** après chaque extract.
3. **File Redis :** `python -m workers.runner` ou `docker compose up -d redis worker`.
4. **Roadmap :** ce document = vision technique interne, pas livrable client par défaut.
5. **Ne pas démarrer Next.js** avant Phase 2 queue stable.

---

## 29. Diagramme ASCII — Strangler migration

```
2026 Q2          2026 Q3              2026 Q4+
────────         ────────             ────────
[Streamlit]      [Streamlit]          [Next.js UI]
     │                │                    │
     ▼                ▼                    ▼
[scraper.cli]    [API + Redis]        [API + Redis]
     │                │                    │
     ▼                ▼                    ▼
[CSV files] ──► [CSV + Postgres] ──► [Postgres SSOT]
                      │
                      ▼
                 [Workers Py]
                      │
                      ▼
              [Browser Supervisor]
```

---

**Document maintenu par :** équipe technique `c:\client`  
**Révision :** après chaque phase ; lier les PRs aux IDs TD-xx.
