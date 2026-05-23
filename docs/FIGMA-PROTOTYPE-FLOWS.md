# Figma — Prototype, animations & navigation

> Référence pour brancher le mode **Prototype** dans Figma. L’app Next.js implémente la navigation réelle ; Figma reste optionnel pour présentation client.

## Fichier

https://www.figma.com/design/dILiXDcsASKX05l1pxcWwR

## Connexions principales

| Depuis | Action | Vers | Animation suggérée |
|--------|--------|------|-------------------|
| Login | Se connecter | Home `/` | Dissolve 200ms |
| Home | Carte Acquisition | `/acquisition` | Smart animate |
| Home | Carte Content | `/content` | Smart animate |
| Content | Générer post | (même frame, état loading) | Instant |
| Content | Approuver | (badge approved) | Dissolve |
| Content | Publier | (toast succès) | Slide up |
| Content | Lien calendrier | `/content/calendar` | Dissolve |
| Nav | Analytics | `/analytics` | Dissolve |
| Nav | Campagnes | `/campaigns` | Dissolve |
| Nav | Billing | `/billing` | Dissolve |
| Nav | Paramètres | `/settings` | Dissolve |
| Settings | Connecter LinkedIn | OAuth (externe) | — |
| Settings | Nouvelle clé API | Modal reveal | Scale |
| Settings | Liens admin | `/admin/*` | Dissolve |
| Home / Nav | Ops | `/ops/overview` | Dissolve |
| Ops sidebar | Chaque onglet | `/ops/*` | Instant |
| Acquisition | Ops Console | `/ops/leads` | Dissolve |

## Frames suggérés (nommage)

| Frame | Route |
|-------|-------|
| `Screen/Login` | `/login` |
| `Screen/Home` | `/` |
| `Screen/Acquisition` | `/acquisition` |
| `Screen/Content` | `/content` |
| `Screen/Calendar` | `/content/calendar` |
| `Screen/Analytics` | `/analytics` |
| `Screen/Campaigns` | `/campaigns` |
| `Screen/Accounts` | `/accounts` |
| `Screen/Billing` | `/billing` |
| `Screen/Settings` | `/settings` |
| `Ops/Overview` … `Ops/Settings` | `/ops/*` |
| `Admin/Audit` … | `/admin/*` |

## États à prototyper (variantes)

- Login : default, loading, error
- Content : empty, liste brouillons, publishing
- Settings : OAuth connecté / non connecté, modal clé API
- Billing : plan Starter / Pro

## Animations CSS (référence code)

Voir `apps/web/app/globals.css` : `fadeIn`, `slideUp`, `transition-card`.
