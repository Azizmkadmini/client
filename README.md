# AI Acquisition OS

Plateforme unifiée : **Acquisition Engine** (scraper, enrichment, outreach) + **AI LinkedIn Content OS** (posts, hooks, calendrier, publication).

Doc complète : [docs/ARCHITECTURE-AI-ACQUISITION-OS.md](docs/ARCHITECTURE-AI-ACQUISITION-OS.md)

## Démarrage rapide

```powershell
python scripts/setup_project.py
copy .env.example .env
# Éditer .env : SMTP, REDIS_URL (optionnel), SCRAPER_WEB_SEARCH_PROVIDER=bing

python outreach.py login linkedin-scrape
python outreach.py login linkedin-outreach
python scripts/health_check.py
```

## Entrées principales

```powershell
python run.py run --source csv
python run.py status
streamlit run dashboard.py
uvicorn api.main:app --reload --port 8000
```

## Scraper

```powershell
# Web (Bing → sites → emails)
python -m scraper.cli web-run --query "agence marketing digitale Tunis" --limit 10 --replace

# LinkedIn
python -m scraper.cli run --app linkedin --query "CEO startup" --limit 5

# Instagram
python -m scraper.cli run --app instagram --mode hashtag --query "marketing" --limit 10
```

## File Redis (optionnel)

```powershell
# .env : REDIS_URL=redis://localhost:6379/0
python -m workers.runner
# Le dashboard et POST /jobs/scraper utilisent la file si Redis est joignable
```

## Email (warm-up)

```powershell
python scripts/warmup.py
python scripts/daily_send.py
```

`EMAIL_DAILY_MAX` et `EMAIL_WARMUP_START_DATE` dans `.env`. Pas d’envoi le week-end (sauf `--force`).

## Sessions LinkedIn

| Fichier | Usage |
|---------|--------|
| `sessions/linkedin-scrape.json` | Collecte |
| `sessions/linkedin-outreach.json` | Messages outreach |
| `sessions/linkedin.json` | Legacy (repli automatique) |

```powershell
python scripts/migrate_linkedin_sessions.py
python outreach.py session-check linkedin-scrape
```

## Content OS (génération IA)

```powershell
uvicorn api.main:app --reload
# POST /api/v1/content/hooks/generate  (header X-API-Key)
# POST /api/v1/content/posts/generate
python outreach.py login linkedin-publish
python -m workers.content_runner
python scripts/content_scheduler.py
python outreach.py login linkedin-publish

# Next.js (phase C5)
cd apps/web && npm install && copy .env.local.example .env.local && npm run dev
```

## Documentation

| Doc | Contenu |
|-----|---------|
| [docs/ARCHITECTURE-AI-ACQUISITION-OS.md](docs/ARCHITECTURE-AI-ACQUISITION-OS.md) | Vision 3 piliers + phases C0–C5 |
| [docs/PROJET-STATUT.md](docs/PROJET-STATUT.md) | Fait / à faire |
| [docs/ENVOI-PRET.md](docs/ENVOI-PRET.md) | Checklist opérationnelle |
| [docs/ARCHITECTURE-CIBLE-MIGRATION.md](docs/ARCHITECTURE-CIBLE-MIGRATION.md) | Roadmap technique |
| [docs/LINKEDIN-AUTOMATION.md](docs/LINKEDIN-AUTOMATION.md) | Mode stable LinkedIn |
| [docs/SOCIAL-WEB-SCRAPING.md](docs/SOCIAL-WEB-SCRAPING.md) | Collecte web |

Docs commerciaux par client : `docs/clients/` (non versionnés).

## Tests

```powershell
python -m pytest -q
```

Utilisez uniquement sur vos comptes, dans le respect des conditions d’utilisation des plateformes et de la loi applicable.
