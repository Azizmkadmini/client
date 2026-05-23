# Fichier Figma — AI Acquisition OS

> **Documentation uniquement.** Le code applicatif (`apps/web/`) n’inclut plus de routes ni scripts dédiés à la capture Figma. Cette doc sert de référence design et d’import manuel dans Figma.

## Lien

**https://www.figma.com/design/dILiXDcsASKX05l1pxcWwR**

File key : `dILiXDcsASKX05l1pxcWwR`

---

## Correspondance pages Figma ↔ routes app (implémentées)

| Page Figma | Routes `apps/web` |
|------------|-------------------|
| 03 Auth & Shell | `/login` |
| 04 SaaS Portal | `/`, `/acquisition`, `/content`, `/content/calendar`, `/analytics`, `/campaigns`, `/accounts`, `/billing`, `/settings` |
| 05 Ops Console | `/ops/overview`, `/ops/scraper`, `/ops/content`, `/ops/pipeline`, `/ops/leads`, `/ops/queue`, `/ops/logs`, `/ops/compliance`, `/ops/guide`, `/ops/settings` |
| 10 Admin | `/admin/audit`, `/admin/feature-flags`, `/admin/gdpr`, `/admin/sso` |

Frames **00 Cover**, **01 Design System**, **02 Components**, **11 States**, **12 Flows** : à créer **dans Figma** à partir de [`FIGMA-COMPLETE-SPEC.md`](./FIGMA-COMPLETE-SPEC.md) — pas de routes dédiées dans le repo.

---

## Import vers Figma (manuel)

1. Lancer l’app : `cd apps/web && npm run dev`
2. Utiliser le MCP Figma `generate_figma_design` depuis Cursor (voir [`CURSOR-FIGMA-SETUP.md`](./CURSOR-FIGMA-SETUP.md)) **ou** saisie manuelle selon la spec.
3. Placer chaque frame sur la page Figma 00–12.
4. Prototypes : [`FIGMA-PROTOTYPE-FLOWS.md`](./FIGMA-PROTOTYPE-FLOWS.md)

---

## Ressources liées

| Fichier | Rôle |
|---------|------|
| [`FIGMA-COMPLETE-SPEC.md`](./FIGMA-COMPLETE-SPEC.md) | Spec complète écrans + composants |
| [`design-tokens.json`](./design-tokens.json) | Tokens (plugin Tokens Studio) |
| [`CURSOR-FIGMA-SETUP.md`](./CURSOR-FIGMA-SETUP.md) | MCP Cursor ↔ Figma |
