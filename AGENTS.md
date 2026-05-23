# AGENTS.md — AI Acquisition OS

Guide pour les agents Cursor travaillant sur ce dépôt.

## Démarrage rapide

```powershell
pip install -r requirements.txt
cd apps/web && npm install
# API
uvicorn api.main:app --reload
# Web
cd apps/web && npm run dev
```

## Documentation design (Figma)

Référence uniquement — pas de routes Figma dans `apps/web/`.

| Ressource | Chemin |
|-----------|--------|
| Spec écrans | `docs/FIGMA-COMPLETE-SPEC.md` |
| Fichier Figma | `docs/FIGMA-FILE.md` |
| Tokens | `docs/design-tokens.json` |
| Setup MCP | `docs/CURSOR-FIGMA-SETUP.md` |

## Zones du code

| Zone | Rôle |
|------|------|
| `api/` | REST FastAPI, auth JWT, content, billing |
| `workers/` | Queue Redis BRPOPLPUSH, runners |
| `apps/web/` | Portail SaaS Next.js |
| `dashboard/` | Ops Console Streamlit (interne) |
| `content/` | Content OS métier |
| `services/` | Risk, crypto, events, AI |

## Tests

```powershell
pytest tests/ -q
```

## Principes

- Stabilité production > nouvelles features SaaS
- Patches ciblés, conventions du fichier modifié
- Français pour l'UI utilisateur
