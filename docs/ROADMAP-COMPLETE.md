# Roadmap — tout livré

## Implémenté dans cette passe

| Domaine | Livrable |
|---------|----------|
| PostgreSQL | Double-write leads, `migrate_postgres.py`, `apply_all_schemas()` |
| Auth | JWT register/login, `AuthContext` (API key ou Bearer) |
| Queues | Retries, delayed jobs, dead-letter queue |
| Workers | Outreach jobs, runner unifié |
| Content | Approval workflow, R2 upload, analytics smart sync |
| Accounts | `linkedin_accounts` multi-rôles |
| Browser | `browser_supervisor/pool.py` |
| Webhooks | n8n → Redis |
| API | `/auth`, `/accounts`, `/webhooks`, `/platform/status` |
| Next.js | Page calendrier |
| Docker | `docker-compose.saas.yml`, `docker-compose.monitoring.yml` |
| Bootstrap | `scripts/bootstrap_saas.py` |

## Démarrage complet

```powershell
pip install -r requirements.txt
python scripts/bootstrap_saas.py --email vous@domaine.com --password VotreMotDePasse
python scripts/migrate_linkedin_sessions.py
python outreach.py login linkedin-scrape
python outreach.py login linkedin-outreach
python outreach.py login linkedin-publish

# Option Postgres
# .env : STORAGE_BACKEND=postgres DATABASE_URL=postgresql://aios:aios@localhost:5432/aios
docker compose -f docker-compose.yml -f docker-compose.saas.yml up -d postgres redis api worker-all
python scripts/migrate_postgres.py

python scripts/health_check.py
uvicorn api.main:app --reload
streamlit run dashboard.py
```

## Auth API

```http
POST /api/v1/auth/login
{"email":"admin@local.dev","password":"admin123"}

Authorization: Bearer <token>
# ou X-API-Key: <API_KEY>
```

## Limites connues (externes)

- Publish LinkedIn = Playwright (DOM fragile)
- Analytics API LinkedIn = placeholder sans token OAuth enregistré
- Billing / Stripe = non inclus
- NestJS = non utilisé
