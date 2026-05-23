# Phases 3 à 5 — complet

## Phase 3 — PostgreSQL SSOT

| Élément | Fichier |
|---------|---------|
| Lectures/écritures leads Postgres | `leads/store.py`, `storage/postgres_backend.py` |
| Content OS Postgres | `content/postgres_store.py` |
| Migration leads + content | `scripts/migrate_all_to_postgres.py`, `scripts/migrate_content_to_postgres.py` |
| Jobs scraper persistés | `workers/queue._persist_postgres` |

## Phase 4 — Anti-ban & account pool

| Élément | Fichier |
|---------|---------|
| Rate limits central | `services/rate_limit_engine.py`, `config/rate_limits.yaml` |
| Pool comptes + publish | `content/account_pool.py`, `content/publishing/linkedin.py` |
| Proxy navigateur | `utils/browser_session.open_channel_context(proxy_url=...)` |
| API rate limits | `GET /api/v1/platform/rate-limits` |

## Phase 5 — Next.js + SaaS

| Élément | Fichier |
|---------|---------|
| Billing + API keys | `billing/service.py`, `api/routers/billing.py` |
| OAuth LinkedIn | `api/routers/oauth_linkedin.py` |
| Analytics API LI | `content/analytics/linkedin_metrics.py` |
| Next.js | login, billing, accounts, settings, campaigns, analytics (Recharts) |
| Content UI | approve + publish depuis `apps/web/app/content` |

## Pages web

| URL | Rôle |
|-----|------|
| `/login` | JWT |
| `/content` | Génération, approbation, publication |
| `/content/calendar` | Calendrier |
| `/campaigns` | Jobs scraper + rate limits |
| `/accounts` | Comptes LinkedIn |
| `/billing` | Crédits / checkout |
| `/settings` | OAuth LinkedIn + clés API |
| `/analytics` | KPIs + graphiques |

## Configuration OAuth LinkedIn

```env
OAUTH_LINKEDIN_CLIENT_ID=...
OAUTH_LINKEDIN_CLIENT_SECRET=...
OAUTH_LINKEDIN_REDIRECT_URI=http://127.0.0.1:8000/api/v1/oauth/linkedin/callback
WEB_APP_URL=http://127.0.0.1:3000
```

Token enregistré : `data/oauth_linkedin.json`

## Commandes

```powershell
pip install -r requirements.txt
python scripts/bootstrap_saas.py --email admin@local.dev --password admin123
python scripts/migrate_all_to_postgres.py   # si Postgres
uvicorn api.main:app --reload
cd apps/web && npm install && npm run dev
```

## Limites production

- Publish LI reste Playwright (DOM LinkedIn peut changer)
- Scopes OAuth Marketing doivent être approués par LinkedIn pour analytics réels
- Stripe : renseigner `STRIPE_*` en prod
