# Phase 1–2 appliquée (code)



Résumé des changements livrés (voir `ARCHITECTURE-CIBLE-MIGRATION.md` pour la cible complète).



## Phase 1 — Stabilisation



| Élément | Statut |

|---------|--------|

| Sessions LinkedIn scrape / outreach séparées | `linkedin-scrape` / `linkedin-outreach` + repli `linkedin.json` |

| Scraper → `linkedin-scrape` | `scraper/collectors.py`, `scraper/browser.py` |

| Outreach bot → `linkedin-outreach` | `bots/linkedin.py` |

| Migration one-shot | `python scripts/migrate_linkedin_sessions.py` |

| Login CLI | `login linkedin-scrape` / `linkedin-outreach` |

| Web Bing par défaut | `SCRAPER_WEB_SEARCH_PROVIDER=bing` |

| Health check pré-run | `python scripts/health_check.py` |

| Warm-up + weekend email | `scripts/warmup.py`, `scripts/daily_send.py`, `bots/email.py` |



## Phase 2 — File de jobs



| Élément | Statut |

|---------|--------|

| Redis + worker | `workers/runner.py`, `docker-compose.yml` |

| API | `POST /jobs/scraper`, `GET /jobs/scraper/{id}` |

| Dashboard → queue | Si `REDIS_URL` + worker actif (`workers/dashboard_queue.py`) |

| Types de jobs | `web-run`, `linkedin-run`, `instagram-run` |

| Fallback | Subprocess si pas de Redis ou `SCRAPER_USE_REDIS_QUEUE=false` |

| `/health` API | Checks sessions, SMTP, Redis |



## Outils ajoutés



| Script | Rôle |

|--------|------|

| `scripts/setup_project.py` | Install deps + playwright + dossiers |

| `scripts/health_check.py` | Vérifications avant run |

| `scripts/migrate_linkedin_sessions.py` | Copie `linkedin.json` → scrape/outreach |



## Prochaines étapes (non codées)



- PostgreSQL SSOT (`storage/postgres_schema.sql` prêt)

- Next.js / portail multi-tenant

- Multi-comptes LinkedIn + proxies



Checklist : **`docs/ENVOI-PRET.md`** · État global : **`docs/PROJET-STATUT.md`**.

