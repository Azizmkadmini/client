# Documentation — plateforme outreach (`c:\client`)

## Technique

| Fichier | Contenu |
|---------|---------|
| [ARCHITECTURE-AI-ACQUISITION-OS.md](./ARCHITECTURE-AI-ACQUISITION-OS.md) | Acquisition + Content OS + Analytics |
| [ARCHITECTURE-CIBLE-MIGRATION.md](./ARCHITECTURE-CIBLE-MIGRATION.md) | Migration technique acquisition |
| [PHASE-1-2-APPLIQUE.md](./PHASE-1-2-APPLIQUE.md) | Phase 1–2 acquisition |
| [PHASE-CONTENT-COMPLETE.md](./PHASE-CONTENT-COMPLETE.md) | Content OS C0–C5 (livré) |
| [ROADMAP-COMPLETE.md](./ROADMAP-COMPLETE.md) | JWT, Postgres, queues, R2, n8n, monitoring |
| [PHASE-3-5-COMPLETE.md](./PHASE-3-5-COMPLETE.md) | Postgres SSOT, rate limits, billing, Next.js |
| [ARCHITECTURE-ENTERPRISE-AUDIT.md](./ARCHITECTURE-ENTERPRISE-AUDIT.md) | **Audit CTO + blueprint Enterprise / Scale** |
| [PHASE-E0-E5-COMPLETE.md](./PHASE-E0-E5-COMPLETE.md) | **Phases E0–E5 implémentées** |
| [PRODUCTION-HARDENING-AUDIT.md](./PRODUCTION-HARDENING-AUDIT.md) | **Audit prod + limites + coûts + runbooks** |
| [PROJET-STATUT.md](./PROJET-STATUT.md) | État du projet (fait / à faire) |
| [ENVOI-PRET.md](./ENVOI-PRET.md) | Checklist mise en route (sessions, scrape, Redis) |
| [LINKEDIN-AUTOMATION.md](./LINKEDIN-AUTOMATION.md) | LinkedIn stable, limites, sessions |
| [SOCIAL-WEB-SCRAPING.md](./SOCIAL-WEB-SCRAPING.md) | Web Bing → sites → contacts |
| [GUIDE_UTILISATEUR.md](./GUIDE_UTILISATEUR.md) | Guide utilisateur |

## Déploiement gratuit (0 €)

| Fichier | Contenu |
|---------|---------|
| [DEPLOY-GRATUIT.md](./DEPLOY-GRATUIT.md) | Vercel + Render + Neon — URL publique sans payer |

## Design (Figma — documentation)

| Fichier | Contenu |
|---------|---------|
| [FIGMA-COMPLETE-SPEC.md](./FIGMA-COMPLETE-SPEC.md) | Spec écrans et composants |
| [FIGMA-FILE.md](./FIGMA-FILE.md) | Lien fichier Figma + mapping routes |
| [FIGMA-PROTOTYPE-FLOWS.md](./FIGMA-PROTOTYPE-FLOWS.md) | Prototypes et animations |
| [CURSOR-FIGMA-SETUP.md](./CURSOR-FIGMA-SETUP.md) | MCP Cursor ↔ Figma |
| [design-tokens.json](./design-tokens.json) | Tokens (Tokens Studio) |

## Documents clients (hors Git)

Placez audits, contrats et packs d’envoi par client dans [`docs/clients/`](./clients/) — ce dossier n’est pas versionné (voir `docs/clients/README.md`).

## Commandes utiles

```powershell
python -m scraper.cli web-run --query "votre requête" --limit 10 --replace
python -m workers.runner
streamlit run dashboard/app.py
uvicorn api.main:app --reload
```
