# Runbook — Redis indisponible

## Symptômes

- Workers log `REDIS_URL manquant`
- API `503` sur `/jobs/scraper`
- Rate limits basculent fichier (OK dégradé)

## Impact

- Pas de jobs async
- Outbox relay ne publie pas vers stream
- Risk engine compteurs failures limités

## Actions

1. Vérifier `redis-cli ping` / container `redis`
2. Redémarrer Redis : `docker compose restart redis`
3. Vérifier AOF/RDB si corruption
4. Workers reprennent automatiquement
5. Relay outbox : `python -m workers.outbox_relay` (once)

## Escalade

Si perte données queue : re-enqueue depuis Postgres `scraper_jobs` où status=queued
