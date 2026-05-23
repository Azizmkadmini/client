# Mise en route — plateforme outreach

## 1. Installation

```powershell
python scripts/setup_project.py
# Éditer .env (copié depuis .env.example si absent)
```

## 2. Santé du système

```powershell
python scripts/health_check.py
```

Corriger tout `[FAIL]` avant un run long.

## 3. Sessions LinkedIn

```powershell
python scripts/migrate_linkedin_sessions.py
python outreach.py login linkedin-scrape
python outreach.py login linkedin-outreach
python outreach.py session-check linkedin-scrape
python outreach.py session-check linkedin-outreach
```

## 4. Scraping web

```powershell
python -m scraper.cli web-run --query "agence marketing digitale" --limit 10 --replace
```

Fichier : `leads/scraper_web_google.csv`

## 5. Redis + worker (optionnel)

```powershell
# .env
REDIS_URL=redis://localhost:6379/0

docker compose up -d redis worker
# ou : python -m workers.runner
```

Sans worker, le dashboard repasse en subprocess automatiquement.

## 6. Warm-up email

```powershell
python scripts/warmup.py --apply
python scripts/daily_send.py
```

## 7. Dashboard & API

```powershell
streamlit run dashboard.py
uvicorn api.main:app --reload --port 8000
```

## Documentation

- [PROJET-STATUT.md](./PROJET-STATUT.md) — fait / reste à faire
- [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md) — roadmap
