# État du projet — AI Acquisition OS

## ✅ Fonctionnel

| Module | Détail |
|--------|--------|
| **Acquisition** | Scrape LI / IG / Web, connecteur, outreach, warm-up email |
| **Content OS** | Génération IA, drafts, calendrier, publish, analytics, optimisation |
| **API** | `/api/v1` — auth JWT, content, analytics, accounts, webhooks n8n |
| **Workers** | Redis, retries, DLQ, acquisition + content + outreach |
| **Stockage** | SQLite + CSV (défaut) · double-write **Postgres** si configuré |
| **UI** | Streamlit (onglet Content OS) · Next.js `apps/web/` |
| **Tests** | 120+ pytest |

## Démarrage rapide

```powershell
pip install -r requirements.txt
python scripts/bootstrap_saas.py --email admin@local.dev --password admin123
python scripts/health_check.py
python outreach.py login linkedin-scrape
python outreach.py login linkedin-outreach
python outreach.py login linkedin-publish
uvicorn api.main:app --reload
streamlit run dashboard.py
```

## Auth (JWT ou API key)

```http
POST /api/v1/auth/login
{"email":"admin@local.dev","password":"admin123"}

Authorization: Bearer <access_token>
# ou header X-API-Key: <API_KEY>
```

## Postgres (optionnel)

```env
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://aios:aios@localhost:5432/aios
```

```powershell
docker compose -f docker-compose.yml -f docker-compose.saas.yml up -d postgres redis api worker-all
python scripts/migrate_postgres.py
```

## Redis + workers

```env
REDIS_URL=redis://localhost:6379/0
```

```powershell
python -m workers.run_all
python scripts/content_scheduler.py
```

## Docs

| Fichier | Contenu |
|---------|---------|
| [ROADMAP-COMPLETE.md](./ROADMAP-COMPLETE.md) | Tout ce qui a été ajouté (dernière passe) |
| [ARCHITECTURE-ENTERPRISE-AUDIT.md](./ARCHITECTURE-ENTERPRISE-AUDIT.md) | Audit senior + phases E0–E5 enterprise |
| [ARCHITECTURE-AI-ACQUISITION-OS.md](./ARCHITECTURE-AI-ACQUISITION-OS.md) | Vision produit |
| [ENVOI-PRET.md](./ENVOI-PRET.md) | Checklist ops |

## Phases architecture (livré)

| Phase | Statut | Doc |
|-------|--------|-----|
| 1–2 Acquisition | ✅ | [PHASE-1-2-APPLIQUE.md](./PHASE-1-2-APPLIQUE.md) |
| C0–C5 Content OS | ✅ | [PHASE-CONTENT-COMPLETE.md](./PHASE-CONTENT-COMPLETE.md) |
| 3 Postgres SSOT | ✅ | [PHASE-3-5-COMPLETE.md](./PHASE-3-5-COMPLETE.md) |
| 4 Rate limits + pool | ✅ | idem |
| 5 Next.js + billing | ✅ | idem |
| E0–E5 Enterprise | ✅ | [PHASE-E0-E5-COMPLETE.md](./PHASE-E0-E5-COMPLETE.md) |

## OAuth & analytics LinkedIn

1. Renseigner `OAUTH_LINKEDIN_*` dans `.env`
2. Ouvrir http://127.0.0.1:3000/settings → **Connecter LinkedIn**
3. Token : `data/oauth_linkedin.json` → analytics réels via API

## Limites (dépendances externes)

- **Publish LinkedIn** : Playwright + pool comptes (DOM fragile)
- **Stripe prod** : clés `STRIPE_*` requises (mode mock sans clé)
- **NestJS** : non utilisé (FastAPI + workers Python)
