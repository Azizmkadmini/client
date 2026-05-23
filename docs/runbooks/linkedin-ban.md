# Runbook — Restrictions LinkedIn

## Symptômes

- Publish success rate < 50%
- Errors: checkpoint, captcha, restrict
- `linkedin_risk` circuit open

## Actions immédiates

1. Pause workers : stop `worker-all`
2. `GET /api/v1/platform/rate-limits` — vérifier quotas
3. Désactiver comptes touchés (health → disabled)
4. Augmenter délais : `config/rate_limits.yaml` ÷2 sur daily_max
5. Vérifier proxies morts

## Recovery

1. Login manuel compte via `outreach.py login linkedin-publish`
2. Warm-up 48h : max 5 actions/jour
3. Réactiver un compte à la fois

## Prévention

- Risk engine v2 actif
- Jamais scrape + publish même session
