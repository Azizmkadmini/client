# Content OS — phases C0 à C5 (livré)

| Phase | Livrable | Statut |
|-------|----------|--------|
| C0 | Schéma SQLite + Postgres, package `content/`, session `linkedin-publish` | ✅ |
| C1 | Génération hooks/posts/CTA + API | ✅ |
| C2 | `ContentStore`, drafts, calendrier, API CRUD | ✅ |
| C3 | `content/publishing/linkedin.py`, publish sync/async | ✅ |
| C4 | `content/analytics/sync.py`, optimisation, métriques | ✅ |
| C5 | `apps/web` Next.js (Acquisition, Content, Analytics, Settings, Campaigns) | ✅ |

## Commandes

```powershell
python outreach.py login linkedin-publish
uvicorn api.main:app --reload
python -m workers.content_runner
python scripts/content_scheduler.py
streamlit run dashboard.py   # onglet Content OS

cd apps/web && npm install && npm run dev
```

## API principales

- `POST /api/v1/content/posts/generate`
- `GET /api/v1/content/drafts`
- `POST /api/v1/content/posts/{id}/schedule`
- `POST /api/v1/content/posts/{id}/publish` body `{"sync": true}`
- `GET /api/v1/analytics/overview`
