# Phases Enterprise E0–E5 — livré (code)

Implémentation progressive dans le monorepo existant. Voir [ARCHITECTURE-ENTERPRISE-AUDIT.md](./ARCHITECTURE-ENTERPRISE-AUDIT.md) pour le blueprint complet.

## E0 — Production hardening

| Livrable | Fichier |
|----------|---------|
| Schéma enterprise Postgres | `storage/postgres_schema_enterprise.sql` |
| Outbox events | `services/outbox.py`, `workers/outbox_relay.py` |
| Idempotency API | `services/idempotency.py` — header `Idempotency-Key` |
| Secrets chiffrés | `services/crypto.py`, `services/secrets_store.py` |
| OAuth chiffré | `api/routers/oauth_linkedin.py` |
| OTel / Sentry hooks | `api/telemetry.py` |
| Prometheus | `/metrics/prometheus` via instrumentator |
| Trace middleware | `api/middleware.py` |
| Worker Playwright image | `Dockerfile.worker` |

## E1 — Distributed workers & browser grid

| Livrable | Fichier |
|----------|---------|
| Browser grid local/remote | `browser_grid/executor.py`, `browser_grid/agent.py` |
| Flag `browser.grid.remote` | `config/feature_flags.yaml` |
| Proxy manager | `services/proxy_manager.py` |
| Publish via grid | `workers/content_jobs.py` |

```env
BROWSER_GRID_MODE=remote
BROWSER_GRID_URL=http://browser-grid:8090
```

```powershell
python -m browser_grid.agent   # port 8090
```

## E2 — Event-driven & analytics

| Livrable | Fichier |
|----------|---------|
| Redis Streams bus | `services/events.py` |
| Event consumer | `workers/event_consumer.py` |
| Analytics ingest | `analytics/ingest.py` |
| KPI engine | `analytics/kpi_engine.py` |
| API KPIs | `GET /api/v1/enterprise/kpis` |

## E3 — Enterprise SaaS

| Livrable | Fichier |
|----------|---------|
| RBAC | `services/rbac.py` |
| Audit logs | `services/audit.py` |
| Feature flags | `config/feature_flags.yaml`, `services/feature_flags.py` |
| GDPR stubs | `api/routers/enterprise.py` |
| SSO config stub | `GET /api/v1/enterprise/sso/config` |

## E4 — AI system

| Livrable | Fichier |
|----------|---------|
| AI orchestrator | `services/ai/orchestrator.py` |
| Prompt registry | `services/ai/prompts.yaml` |
| Usage metering | table `ai_usage_events` |

## E5 — International (foundation)

| Livrable | Config |
|----------|--------|
| Région défaut | `DEFAULT_REGION=eu-west` |
| Locales | `SUPPORTED_LOCALES=fr,en` |

## Docker enterprise

```powershell
docker compose -f docker-compose.yml -f docker-compose.saas.yml -f docker-compose.enterprise.yml --profile enterprise --profile grid up -d
```

## API enterprise

| Route | Description |
|-------|-------------|
| `GET /api/v1/enterprise/feature-flags` | Flags tenant |
| `GET /api/v1/enterprise/kpis` | KPIs agrégés |
| `GET /api/v1/enterprise/audit` | Audit logs |
| `GET /api/v1/enterprise/proxies` | Pool proxies |

## Variables `.env` (nouvelles)

```env
SECRETS_ENCRYPTION_KEY=change-me-32-chars-min
SENTRY_DSN=
OTEL_ENABLED=false
BROWSER_GRID_MODE=local
BROWSER_GRID_URL=http://127.0.0.1:8090
```

## Migration Postgres

```powershell
python scripts/migrate_all_to_postgres.py
# ou POST /api/v1/admin/migrate-postgres
```

## Limites (infra externe)

- ClickHouse / Kafka : schéma prêt via events, pas déployé
- K8s / Terraform : `docker-compose.enterprise.yml` seulement
- SSO OIDC : stub — configurer `OIDC_ISSUER`
- Vector DB Qdrant : documenté dans audit, pas câblé

## Tests

```powershell
python -m pytest tests/test_enterprise.py -q
```
