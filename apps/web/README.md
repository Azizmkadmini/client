# AI Acquisition OS — Web (Next.js)

Portail SaaS B2B — acquisition, Content OS, analytics, ops.

## Dev

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

## UI

- Composants : `components/ui/`, `components/AppShell`, `components/ops/OpsLayout`
- Spec design (doc) : `../../docs/FIGMA-COMPLETE-SPEC.md`
- Tokens : `../../docs/design-tokens.json`

## Auth

Login → JWT dans `localStorage` (`aios_token`). Routes protégées via `AppShell` (sauf `/login`, `/ops/*`, `/admin/*`).
