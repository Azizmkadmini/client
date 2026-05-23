# Runbook — Postgres lent

## Symptômes

- API timeout
- Workers `save` lent
- CPU disque 100%

## Diagnostic

```sql
SELECT pid, now() - query_start AS dur, query
FROM pg_stat_activity
WHERE state = 'active' ORDER BY dur DESC;

SELECT relname, seq_scan, idx_scan FROM pg_stat_user_tables;
```

## Actions

1. `VACUUM ANALYZE;`
2. Vérifier indexes : `postgres_indexes.sql` appliqué
3. Kill requête longue : `SELECT pg_cancel_backend(pid);`
4. Scale up IOPS / read replica pour reads

## Archive

Si `analytics_events` > 10M rows → export + truncate + plan ClickHouse
