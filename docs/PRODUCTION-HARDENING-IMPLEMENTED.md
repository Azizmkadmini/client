# Production Hardening — Implémenté

> Complète `PRODUCTION-HARDENING-AUDIT.md` avec les patches réels appliqués.

## Architecture finale (simplifiée)

```
                    ┌─────────────┐
                    │  FastAPI    │
                    │  + CORS     │
                    └──────┬──────┘
                           │ LPUSH + idempotency
                           ▼
              ┌────────────────────────┐
              │ Redis                  │
              │  pending ──BRPOPLPUSH──► processing
              │     ▲                      │
              │     │ recover_stale        │ LREM (ack)
              │     └──────────────────────┘
              │  delayed (ZSET backoff)    DLQ
              └────────────┬───────────────┘
                           │
              ┌────────────▼───────────────┐
              │ worker_runtime             │
              │  heartbeat / timeout /     │
              │  graceful shutdown         │
              └────────────┬───────────────┘
                           │
              ┌────────────▼───────────────┐
              │ browser_pool (singleton)   │
              │  context/page reuse        │
              └────────────────────────────┘
```

## 1. Queue fiable

| | |
|---|---|
| **Problème** | `BRPOP` supprime le job avant exécution → perte si crash worker |
| **Risque** | Jobs fantômes, double exécution, pas de recovery |
| **Solution** | `BRPOPLPUSH pending → processing`, `ack()` = `LREM processing`, `recover_stale()`, idempotence `SET NX` |
| **Fichiers** | `workers/queue.py`, `workers/worker_runtime.py`, `workers/runner.py`, `workers/content_runner.py` |

## 2. Browser reuse

| | |
|---|---|
| **Problème** | `sync_playwright()` à chaque publish → ~200 Mo/job, lent |
| **Risque** | OOM worker, coût infra, timeouts |
| **Solution** | `utils/browser_pool.py` — singleton browser, contextes par canal, recycle après N pages |
| **Fichiers** | `utils/browser_pool.py`, `content/publishing/linkedin.py` |

## 3. Workers robustes

| | |
|---|---|
| **Problème** | Pas de heartbeat, shutdown brutal, pas de timeout |
| **Risque** | Jobs zombies, perte en cours, workers morts non détectés |
| **Solution** | `worker_runtime.py` — SIGTERM, `worker:heartbeat:{id}`, timeout thread pool, backoff exponentiel + jitter |
| **Fichiers** | `workers/worker_runtime.py`, `workers/run_all.py` |

## 4. Production security

| | |
|---|---|
| **Problème** | Redis sans auth, CORS ouvert, secrets optionnels |
| **Risque** | Fuite données, CSRF cross-origin, tokens en clair |
| **Solution** | `services/env_validation.py` fail-fast prod, CORS restrictif, `SECRETS_ENCRYPTION_KEY` check |
| **Fichiers** | `services/env_validation.py`, `api/main.py`, `.env.example` |

## 5. Postgres performance

| | |
|---|---|
| **Problème** | `GET /leads` charge tout en mémoire |
| **Risque** | OOM API, requêtes lentes |
| **Solution** | `fetch_leads_page`, `LeadStore.list_page`, retention + VACUUM scripts |
| **Fichiers** | `storage/postgres_backend.py`, `leads/store.py`, `scripts/retention.py`, `scripts/vacuum_maintenance.py` |

---

## Checklist production

- [ ] `ENV=production` + `validate_all(strict=True)` au boot API/worker
- [ ] `REDIS_URL=redis://:password@private-host:6379/0`
- [ ] `JWT_SECRET` + `SECRETS_ENCRYPTION_KEY` (32+ chars)
- [ ] `STORAGE_BACKEND=postgres` + `DATABASE_URL` privé
- [ ] Workers : `python -m workers.runner` + `python -m workers.content_runner`
- [ ] Cron : `python scripts/retention.py` (quotidien), `python scripts/vacuum_maintenance.py` (hebdo)
- [ ] `/api/v1/platform/jobs/queue/stats` monitoring
- [ ] Streamlit **non exposé** publiquement
- [ ] `CORS_ORIGINS` = domaine Next.js uniquement

## Métriques importantes

| Métrique | Source |
|----------|--------|
| `queue pending/processing/dlq` | `GET /api/v1/platform/jobs/queue/stats` |
| `worker:heartbeat:*` TTL | Redis |
| `linkedin_risk_score` | `services/linkedin_risk.py` |
| Job duration / timeout | logs worker `[worker:id]` |
| Postgres slow queries | `pg_stat_statements` |
| Browser recycle count | logs `browser_pool` (à ajouter OTel) |

## Tests ajoutés

- `tests/test_queue_reliable.py` (nécessite `REDIS_URL`)
- `tests/test_worker_runtime.py` (unit, sans Redis)

```bash
pytest tests/test_worker_runtime.py -q
REDIS_URL=redis://localhost:6379/0 pytest tests/test_queue_reliable.py -q
```

## Limites restantes (honnêtes)

1. **LinkedIn DOM** — toujours fragile ; circuit breaker = throttle, pas garantie anti-ban.
2. **Idempotence** — clé Redis 24h ; pas de dedup cross-tenant sans `tenant_id` dans la clé.
3. **Browser pool** — par process worker ; pas de grid distribué sauf `browser_grid_mode=remote`.
4. **RLS Postgres** — `SET LOCAL` pas câblé partout ; filtrage tenant côté app.
5. **Exactly-once** — at-least-once + idempotence métier requise côté handlers.
6. **Scrapers acquisition** — pas encore migrés sur `browser_pool` (publish LinkedIn oui).

## Commandes

```powershell
python -m workers.runner --worker-id w1
python -m workers.content_runner --worker-id content-1
python -m workers.run_all
python scripts/retention.py
python scripts/vacuum_maintenance.py
```
