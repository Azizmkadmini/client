# AI Acquisition OS — Architecture unifiée

**Extension :** module **AI LinkedIn Content OS** intégré au monorepo `c:\client`  
**Version :** 1.0 · Mai 2026  
**Principe :** pas de nouveau repo — *Strangler Fig* sur la plateforme outreach existante  
**Complète :** [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md)

---

## 1. Vision produit

**AI Acquisition OS** = une plateforme SaaS qui combine :

| Domaine | Nom interne | Référence marché |
|---------|-------------|------------------|
| **Acquisition Engine** | `acquisition` | Apollo + Clay + Instantly |
| **AI LinkedIn Content OS** | `content` | Taplio + Typefully |
| **Analytics & Optimization** | `analytics` | Dashboard ROI + attribution |

L’utilisateur gère **leads + campagnes outbound** et **contenu LinkedIn** depuis **un seul tenant**, **une auth**, **une base Postgres**, **une grille de workers**.

---

## 2. État réel vs stack cible (honnêteté technique)

| Composant | Aujourd’hui (`c:\client`) | Cible AI Acquisition OS |
|-----------|---------------------------|-------------------------|
| Frontend | Streamlit `dashboard/` | **Next.js** (App Router, Shadcn, TanStack Query) |
| API | FastAPI `api/main.py` | FastAPI **modulaire** (+ routes `content/`) |
| DB | SQLite `data/app.db` + CSV | **PostgreSQL** SSOT |
| Queue | Redis LPUSH + `workers/runner.py` | Redis + workers spécialisés |
| Browser | Playwright sync, `sessions/*.json` | **Browser pool** + comptes LI séparés scrape / publish |
| AI outreach | `ai/generator.py` (email/LI message) | + **`content/ai/`** (posts, hooks, CTA) |
| Auth | `API_KEY`, `DASHBOARD_PASSWORD` | **JWT + OAuth LinkedIn** |
| Storage médias | local | **Cloudflare R2** |
| Monitoring | JSONL `logs/` | Grafana + Loki + Sentry |
| NestJS | **Absent** | Optionnel Phase 2+ (realtime only) |
| n8n | **Absent** | Connecteur webhooks externe |

**Décision d’intégration :** le module Content OS est d’abord **Python/FastAPI** (réutilise Playwright, Redis, `ai/generator`, anti-ban LinkedIn). NestJS n’est introduit que si besoin WebSocket temps réel massif — pas au jour 1.

---

## 3. Architecture globale (3 piliers)

```txt
                         ┌────────────────────────────────────────┐
                         │            Frontend Next.js             │
                         │  Acquisition · Content · Analytics      │
                         │  Tailwind · Shadcn · TanStack Query     │
                         └────────────────────┬───────────────────┘
                                              │ HTTPS / WSS
                         ┌────────────────────▼───────────────────┐
                         │         API Gateway — FastAPI             │
                         │  /api/v1/acquisition/*  /content/*      │
                         │  Auth JWT · Tenants · Rate limits         │
                         └────────────────────┬───────────────────┘
          ┌──────────────────────────────────┼──────────────────────────────────┐
          │                                  │                                  │
          ▼                                  ▼                                  ▼
┌─────────────────────┐         ┌─────────────────────┐         ┌─────────────────────┐
│   Acquisition OS    │         │   Content OS          │         │   Analytics OS      │
│   (existant)        │         │   (nouveau)           │         │   (agrégation)      │
├─────────────────────┤         ├─────────────────────┤         ├─────────────────────┤
│ scraper/            │         │ content/generation    │         │ analytics/metrics   │
│ connector/          │         │ content/calendar      │         │ analytics/scoring   │
│ bots/ outreach      │         │ content/publishing    │         │ analytics/attribution│
│ orchestrator/       │         │ content/media         │         │                     │
│ leads/              │         │ content/optimization  │         │                     │
└──────────┬──────────┘         └──────────┬──────────┘         └──────────┬──────────┘
           │                               │                               │
           └───────────────────────────────┼───────────────────────────────┘
                                           ▼
                         ┌─────────────────────────────────────────┐
                         │              PostgreSQL                  │
                         │  tenants · leads · posts · metrics       │
                         └─────────────────────────────────────────┘
                                           ▲
                         ┌─────────────────┴───────────────────────┐
                         │              Redis Queues                │
                         │  acquisition:* · content:* · analytics:*   │
                         └─────────────────┬───────────────────────┘
                                           ▼
                         ┌─────────────────────────────────────────┐
                         │           Worker tier (Python)           │
                         │  workers/runner · content_worker         │
                         │  browser_supervisor (Playwright stealth) │
                         └─────────────────────────────────────────┘
                                           │
                         ┌─────────────────┴───────────────────────┐
                         │  R2 (médias) · OpenAI/Claude · n8n     │
                         └─────────────────────────────────────────┘
```

---

## 4. Cartographie monorepo (cible)

```
c:\client\
├── api/
│   ├── main.py                 # Gateway — inclut routers acquisition + content
│   └── routers/
│       ├── acquisition.py      # Extrait de main.py (phase migration)
│       └── content.py          # Posts, calendar, publish, analytics
├── acquisition/                # Alias logique (réexport scraper+connector+bots)
│   └── README.md
├── content/                    # ★ NOUVEAU — AI LinkedIn Content OS
│   ├── __init__.py
│   ├── models.py               # Pydantic domain
│   ├── generation/             # hooks, posts, cta, carousels
│   ├── calendar/               # slots, drafts, approval
│   ├── publishing/             # Playwright publish, queue, retry
│   ├── media/                  # R2 upload, quote cards, visuals
│   ├── analytics/              # sync metrics from LI, scores
│   └── optimization/           # bandits, best time, templates
├── analytics/                  # Cross-domain ROI (leads ↔ posts)
├── ai/
│   ├── generator.py            # Existant — outreach messages
│   └── content_prompts.py      # Prompts Content OS (à ajouter)
├── workers/
│   ├── runner.py               # Acquisition jobs (existant)
│   ├── jobs.py
│   └── content_jobs.py         # ★ content-generate, content-publish
├── storage/
│   ├── postgres_schema.sql
│   └── postgres_schema_content.sql  # ★
├── apps/web/                   # ★ Next.js (phase 5)
└── dashboard/                  # Streamlit — admin interne jusqu’à migration UI
```

---

## 5. Module Content OS — découpage fonctionnel

### 5.1 Content Generation (`content/generation/`)

| Fonction | Description | Provider AI |
|----------|-------------|-------------|
| `generate_hook` | 5–10 variantes accroche | OpenAI / Claude |
| `generate_post` | Storytelling, expertise, conversion, opinion | Idem |
| `generate_cta` | CTA soft / hard / question | Idem |
| `generate_carousel` | Structure slides + texte | Idem + template |
| `generate_quote_card` | Texte court + rendu image | Pillow / API image |
| `generate_visual` | Architecture diagram, screenshot stylized | R2 + worker image |

**Réutilisation :** étendre `ai/generator.py` ou créer `content/generation/llm.py` avec interface commune :

```python
class ContentLLM(Protocol):
    async def complete(self, system: str, user: str, *, model: str) -> str: ...
```

Formats de post (enum) : `storytelling | expertise | conversion | framework | opinion | carousel`.

### 5.2 Content Management (`content/calendar/`)

| Entité | Champs clés |
|--------|-------------|
| `ContentDraft` | tenant_id, author_id, body, hook, cta, format, status |
| `ContentSlot` | scheduled_at, timezone, linkedin_account_id, draft_id |
| `Approval` | reviewer_id, status, comment |

**Workflow :** `draft → review → scheduled → publishing → published → archived`

UI Next.js : calendrier drag & drop (FullCalendar ou custom), preview LinkedIn (composant mock feed).

### 5.3 LinkedIn Publishing (`content/publishing/`)

| Capacité | Implémentation |
|----------|----------------|
| Scheduling | Cron worker + table `content_publish_jobs` |
| Auto publish | Playwright — session **`linkedin-publish`** (≠ scrape, ≠ outreach DM) |
| Media upload | Fichier local → R2 → upload LI via DOM |
| Queue + retry | Redis `content:publish` + DLQ |
| Anti-ban | Réutiliser `linkedin_stability.py` — limites posts/jour, jitter |
| Warmup | Compte neuf : likes/comments only 7j avant 1er post |

**3 canaux de session LinkedIn (rappel architecture acquisition) :**

| Canal fichier | Usage |
|---------------|--------|
| `linkedin-scrape` | Collecte leads |
| `linkedin-outreach` | Messages DM campagne |
| `linkedin-publish` | **Publication posts** (nouveau) |

### 5.4 Analytics (`content/analytics/`)

Métriques synchronisées (API officielle si disponible OAuth, sinon scrape léger dashboard créateur) :

| Métrique | Usage optimisation |
|----------|-------------------|
| impressions | Score reach |
| likes, comments, saves | Engagement rate |
| profile visits | Top of funnel |
| DM conversions | Lien avec `leads` (attribution) |
| dwell time (estimé) | Heuristique depuis impressions/engagement |

Table `content_post_metrics` — snapshot quotidien par post.

### 5.5 AI Optimization (`content/optimization/`)

Boucle fermée (batch nocturne) :

1. Agréger performances par `(hook_template, cta_type, format, hour_bucket, category)`.
2. Mettre à jour `content_template_scores` (bandit / EMA).
3. Exposer `recommend_slot()` et `predict_engagement()` à la génération.

| Sortie | Algorithme initial | Évolution |
|--------|-------------------|-----------|
| Meilleur horaire | Histogramme engagement | ML léger |
| Meilleur hook | Thompson sampling sur templates | Fine-tune prompts |
| Viral score | Régression features texte + historique | Classifier |

---

## 6. Schéma PostgreSQL — Content OS

Fichier : `storage/postgres_schema_content.sql`

Tables principales :

| Table | Rôle |
|-------|------|
| `tenants` | Multi-tenant SaaS |
| `users` | Membres workspace |
| `linkedin_accounts` | Comptes LI (scrape / outreach / publish flags) |
| `content_drafts` | Brouillons |
| `content_posts` | Post publié ou planifié |
| `content_media` | Assets R2 |
| `content_calendar_slots` | Créneaux |
| `content_publish_jobs` | File publication |
| `content_post_metrics` | Analytics |
| `content_template_scores` | Optimisation IA |
| `content_generation_runs` | Audit prompts / coûts tokens |

**Lien Acquisition ↔ Content :**

- `linkedin_accounts.tenant_id` partagé.
- `content_posts` optionnel `campaign_id` → table `outreach_campaigns`.
- Attribution : UTM / lien profil → `leads.source = 'linkedin_content:{post_id}'`.

---

## 7. Files Redis (queues)

Préfixe unifié : `aios:{tenant_id}:...`

| Queue | Job types | Worker |
|-------|-----------|--------|
| `acquisition:scraper` | `web-run`, `linkedin-run` | `workers/runner.py` (existant) |
| `acquisition:outreach` | `email-send`, `li-dm-send` | `workers/outreach_jobs.py` |
| `content:generate` | `hook`, `post`, `carousel`, `visual` | `workers/content_jobs.py` |
| `content:publish` | `publish-post`, `upload-media` | `workers/content_jobs.py` |
| `content:sync-metrics` | `pull-analytics` | `workers/content_jobs.py` |
| `analytics:rollup` | `daily-tenant-stats` | `workers/analytics_jobs.py` |
| `dead-letter` | tous | replay manuel admin |

**Compatibilité :** garder `outreach:scraper:jobs` actuel ; migration alias vers `acquisition:scraper`.

---

## 8. API REST (FastAPI) — contrat v1

Base : `/api/v1` · Auth : `Authorization: Bearer <jwt>` · Tenant : header `X-Tenant-Id` ou claim JWT.

### 8.1 Acquisition (existant → router dédié)

| Méthode | Route | Statut |
|---------|-------|--------|
| POST | `/orchestrator/run` | ✅ Existant |
| POST | `/jobs/scraper` | ✅ Existant |
| POST | `/connector/run` | ✅ Existant |
| GET | `/leads` | ✅ Existant |

### 8.2 Content OS (nouveau)

| Méthode | Route | Description |
|---------|-------|-------------|
| POST | `/content/hooks/generate` | Génère N hooks |
| POST | `/content/posts/generate` | Génère post complet |
| POST | `/content/posts` | CRUD draft |
| GET | `/content/posts` | Liste + filtres statut |
| POST | `/content/calendar/slots` | Planifier |
| PATCH | `/content/calendar/slots/{id}` | Déplacer (drag drop) |
| POST | `/content/publish` | Enqueue publication |
| GET | `/content/publish/jobs/{id}` | Statut job |
| POST | `/content/media/upload` | Presigned R2 URL |
| GET | `/content/analytics/posts/{id}` | Métriques |
| GET | `/content/optimization/recommendations` | Meilleurs créneaux / templates |

### 8.3 Analytics cross-domain

| Méthode | Route | Description |
|---------|-------|-------------|
| GET | `/analytics/overview` | KPIs acquisition + content |
| GET | `/analytics/attribution` | Post → lead → reply |

---

## 9. Frontend Next.js — structure

```
apps/web/
├── app/
│   ├── (auth)/login
│   ├── (dashboard)/
│   │   ├── acquisition/     # leads, campaigns, scraper status
│   │   ├── content/         # calendar, drafts, composer
│   │   └── analytics/       # recharts dashboards
│   └── api/                 # BFF optionnel
├── components/
│   ├── content/             # PostPreview, CalendarGrid, HookPicker
│   └── acquisition/
├── lib/api.ts                 # TanStack Query clients
└── stores/                    # Zustand — tenant, UI state
```

**Streamlit** reste `dashboard/` pour ops internes jusqu’à parité Next.js ≥ 80 %.

---

## 10. Auth & comptes LinkedIn

```txt
┌─────────────┐     OAuth 2.0      ┌──────────────────┐
│   Next.js   │ ◄────────────────► │ LinkedIn API     │
└──────┬──────┘                    │ (marketing dev)  │
       │ JWT                        └────────┬─────────┘
       ▼                                   │
┌─────────────┐     refresh tokens        │
│  FastAPI    │ ◄─────────────────────────┘
│  tenants    │
└──────┬──────┘
       │ encrypt at rest
       ▼
┌─────────────────────────────┐
│ linkedin_accounts           │
│ oauth_tokens (vault)        │
│ storage_state_publish (blob)│
└─────────────────────────────┘
```

**Fallback actuel :** `outreach.py login linkedin-publish` → `sessions/linkedin-publish.json` (comme scrape/outreach).

---

## 11. Browser & anti-ban (partagé)

Superviseur unique `browser_supervisor/` (extrait futur de `utils/browser_session.py`) :

| Pool | Instances max | Politique |
|------|---------------|-----------|
| `scrape` | 1–2 / compte | Mode stable, `linkedin_stability` |
| `outreach` | 1 / compte | DM limits |
| `publish` | 1 / compte | Posts/jour cap, human delays |

Stealth : `--disable-blink-features=AutomationControlled`, CDP option, rotation UA (phase 4).

---

## 12. Intégrations externes

| Service | Rôle | Intégration |
|---------|------|-------------|
| **OpenAI / Claude** | Génération texte | `content/generation/llm.py` |
| **Cloudflare R2** | Médias | `content/media/r2.py` |
| **n8n** | Automations client | Webhooks `POST /webhooks/n8n/{workflow}` |
| **Sentry** | Errors | SDK FastAPI + workers |
| **Grafana/Loki** | Logs | Docker compose profile `monitoring` |

---

## 13. Docker Compose (profils)

```yaml
# Profil minimal (aujourd’hui + content workers)
services: api, worker-acquisition, worker-content, redis, postgres

# Profil full SaaS
services: + web (Next.js), minio/r2-gateway, n8n, loki, grafana
```

Fichier cible : `docker-compose.saas.yml` (à créer phase 3).

---

## 14. Plan de migration par phases

### Phase C0 — Fondations (semaines 1–2)

| # | Tâche | Fichiers |
|---|-------|----------|
| C0.1 | Schéma Postgres content | `postgres_schema_content.sql` |
| C0.2 | Package `content/` squelette | `content/*` |
| C0.3 | Router API stub | `api/routers/content.py` |
| C0.4 | Session `linkedin-publish` | `session_channels.py`, docs |
| C0.5 | Variables `.env` content AI | `config.py`, `.env.example` |

### Phase C1 — Génération IA (semaines 3–5)

- Implémenter `generate_hook`, `generate_post`, `generate_cta`.
- Templates prompts versionnés (`content/prompts/*.yaml`).
- POST `/content/hooks/generate`, `/content/posts/generate`.
- Tests pytest mocks LLM.

### Phase C2 — Calendar & drafts (semaines 6–8)

- CRUD drafts + slots Postgres.
- Worker `content:generate` async.
- UI Streamlit minimale **ou** première page Next.js calendar.

### Phase C3 — Publishing (semaines 9–12)

- Playwright publish flow (texte + 1 image).
- Queue `content:publish`, retries, DLQ.
- Limites anti-ban publication.

### Phase C4 — Analytics & optimization (semaines 13–16)

- Sync métriques, dashboards Recharts.
- Job nightly `content:sync-metrics`.
- Recommandations templates / horaires.

### Phase C5 — SaaS complet (semaines 17–24)

- Next.js parité Taplio/Typefully.
- OAuth LinkedIn, multi-compte, billing.
- Fusion analytics acquisition + content.

**Parallèle acquisition :** continuer Phases 1–5 du doc [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md) (Postgres SSOT, browser pool).

---

## 15. Matrice « qui réutilise quoi »

| Existant | Content OS |
|----------|------------|
| `ai/generator.py` | Patterns prompts, providers Ollama/OpenAI/Groq |
| `utils/browser_session.py` | Sessions publish + pool |
| `linkedin_stability.py` | Rate limits publication |
| `workers/queue.py` | Modèle `ScraperJob` → `ContentJob` |
| `config.py` | `CONTENT_*`, `R2_*`, `OPENAI_*` |
| `compliance/registry.py` | Opt-out contenu (mentions, AI label) |
| `logs/logger.py` | Audit génération / publish |

---

## 16. Variables d’environnement (nouvelles)

```env
# Content OS
CONTENT_AI_PROVIDER=openai          # openai | claude | ollama
CONTENT_OPENAI_MODEL=gpt-4o-mini
CONTENT_CLAUDE_API_KEY=
CONTENT_MAX_POSTS_PER_DAY=2
CONTENT_PUBLISH_SESSION_CHANNEL=linkedin-publish

# Médias
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=aios-media
R2_PUBLIC_BASE_URL=

# SaaS
JWT_SECRET=
OAUTH_LINKEDIN_CLIENT_ID=
OAUTH_LINKEDIN_CLIENT_SECRET=
```

---

## 17. Risques & garde-fous

| Risque | Mitigation |
|--------|------------|
| Ban LinkedIn publication | Compte dédié, warmup, cap posts/jour |
| Violation ToS automation | OAuth officiel quand possible ; CDP human-in-loop |
| Coût tokens IA | Cache prompts, `content_generation_runs` billing |
| Divergence scrape/publish | 3 sessions distinctes |
| Scope creep NestJS | FastAPI seul jusqu’à preuve de besoin WSS |

---

## 18. Implémentation livrée (C0–C5)

Voir [PHASE-CONTENT-COMPLETE.md](./PHASE-CONTENT-COMPLETE.md).

1. `content/store.py` — drafts, posts, calendrier, publish jobs, métriques  
2. `content/publishing/linkedin.py` — publication Playwright  
3. API `/api/v1/content/*` + `/api/v1/analytics/overview`  
4. Dashboard onglet **Content OS** · Next.js `apps/web/`  
5. `python outreach.py login linkedin-publish` · `python scripts/content_scheduler.py`

---

**Document maintenu avec :** `ARCHITECTURE-CIBLE-MIGRATION.md` · `PHASE-1-2-APPLIQUE.md`  
**Révision :** après chaque phase C0–C5 ; lier les PRs `feat/content-*`.
