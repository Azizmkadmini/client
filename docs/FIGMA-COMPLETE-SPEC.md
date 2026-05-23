# AI Acquisition OS — Spécification Figma complète

> **Usage :** référence design (Figma, présentation, Tokens Studio).  
> **Code :** `apps/web/` — portail Next.js sans routes « showcase » Figma.  
> **Import Figma :** voir [`FIGMA-FILE.md`](./FIGMA-FILE.md) et [`CURSOR-FIGMA-SETUP.md`](./CURSOR-FIGMA-SETUP.md).

---

## 0. Structure du fichier Figma

| Page Figma | Contenu |
|------------|---------|
| `00 — Cover` | Cover + version + lien repo |
| `01 — Design System` | Tokens, typo, atomes |
| `02 — Components` | Molécules / organismes |
| `03 — Auth & Shell` | Login, layout, nav |
| `04 — SaaS Portal` | Écrans portail |
| `05 — Ops Console` | 10 onglets ops |
| `06 — Content OS` | Flow éditorial |
| `07 — Acquisition` | Leads, scraper |
| `08 — Analytics & Campaigns` | KPIs, jobs |
| `09 — Accounts & Billing` | Comptes LI, Stripe |
| `10 — Settings & Admin` | OAuth, API keys, enterprise |
| `11 — States` | Empty, error, loading |
| `12 — User Flows` | Diagrammes prototype |

**Frame desktop :** 1440 × 900  
**Frame mobile (option) :** 390 × 844  
**Grille :** 8px, 12 colonnes, gutter 24, margin 80

---

## 1. Design System

### Marque

- **Nom :** AI Acquisition OS  
- **Tagline :** Acquisition + Content OS + Analytics  
- **Langue UI :** Français  

### Couleurs (dark SaaS)

| Token | Hex | Usage |
|-------|-----|--------|
| `bg/base` | `#020617` | Fond |
| `bg/elevated` | `#0f172a` | Cartes |
| `accent/primary` | `#059669` | CTA |
| `accent/ops` | `#6366f1` | Ops sidebar |
| `danger` | `#f87171` | Erreurs |

Tokens JSON : [`design-tokens.json`](./design-tokens.json)

### Typographie

Inter — Display 36, H1 28, Body 14, Label 12. Mono : JetBrains Mono.

### Composants (atoms → organisms)

Button (primary/secondary/ghost/danger), Input, Badge, MetricCard, PageHeader, DraftCard, EmptyState, ErrorBanner, Modal, Toast, AppShell, OpsLayout.

Implémentation : `apps/web/components/`

---

## 2. Écrans portail (`apps/web`)

### `Screen/Login` — `/login`

- Email, mot de passe, « Se connecter »
- États : loading, error
- API : `POST /api/v1/auth/login`

### `Screen/Home` — `/`

- KPIs, cartes modules (Acquisition, Content, Analytics, Campagnes, Ops, Billing)
- Bloc configuration API

### `Screen/Acquisition` — `/acquisition`

- KPI leads, table paginée, import CSV
- Lien Ops Console

### `Screen/Content` — `/content`

- Topic, génération IA, liste DraftCard (approuver, publier)
- Lien calendrier

### `Screen/Calendar` — `/content/calendar`

- Créneaux planifiés, badges statut

### `Screen/Analytics` — `/analytics`

- KPIs content, graphique leads par statut

### `Screen/Campaigns` — `/campaigns`

- Rate limits par canal, jobs scraper

### `Screen/Accounts` — `/accounts`

- Comptes LinkedIn, health score, purposes

### `Screen/Billing` — `/billing`

- Plan, crédits, cartes Starter / Pro

### `Screen/Settings` — `/settings`

- OAuth LinkedIn, clés API, liens admin

---

## 3. Ops Console — `/ops/*`

Layout : sidebar indigo + contenu.

| Frame | Route | Contenu |
|-------|-------|---------|
| Overview | `/ops/overview` | 6 KPIs, 2 graphiques |
| Scraper | `/ops/scraper` | 3 colonnes LI / IG / Web + table résultats |
| Content | `/ops/content` | Génération, hooks, post |
| Pipeline | `/ops/pipeline` | Source, run pipeline, outreach |
| Leads | `/ops/leads` | Filtres, table, import CSV |
| Queue | `/ops/queue` | File d’attente |
| Logs | `/ops/logs` | Onglets Envoyés / Échecs / Réponses |
| Compliance | `/ops/compliance` | Opt-out |
| Guide | `/ops/guide` | 7 étapes opérationnelles |
| Settings | `/ops/settings` | Config JSON, rate limits |

---

## 4. Admin — `/admin/*`

| Frame | Route |
|-------|-------|
| Audit | `/admin/audit` |
| Feature flags | `/admin/feature-flags` |
| GDPR | `/admin/gdpr` |
| SSO | `/admin/sso` |

---

## 5. Prototype (page 12)

Flows : Auth → Home ; Content → Calendar → Analytics ; Acquisition → Ops ; Billing → Settings → Admin.

Détail des liens : [`FIGMA-PROTOTYPE-FLOWS.md`](./FIGMA-PROTOTYPE-FLOWS.md)

---

## 6. API & alignement code

| Domaine | Endpoints clés |
|---------|----------------|
| Auth | `/api/v1/auth/login` |
| Content | `/api/v1/content/drafts`, posts, calendar |
| Analytics | `/api/v1/analytics/overview` |
| Billing | `/api/v1/billing/credits`, checkout |
| Platform | jobs, rate-limits |

---

## 7. Import Figma — checklist

1. Créer les 12 pages dans le fichier Figma
2. Importer tokens (`design-tokens.json`)
3. Capturer ou dessiner les frames listées ci-dessus
4. Brancher prototypes (§5)
5. Ne pas dupliquer la logique métier dans Figma — le code reste la source d’exécution
