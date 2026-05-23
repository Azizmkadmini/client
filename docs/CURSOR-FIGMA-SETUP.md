# Cursor ↔ Figma — configuration (projet `c:\client`)

> **Note :** la configuration MCP reste disponible pour le design. Le **code** Next.js ne contient plus de script de capture ni de routes « showcase » Figma.

## Fichier Figma

**https://www.figma.com/design/dILiXDcsASKX05l1pxcWwR** — voir [`FIGMA-FILE.md`](./FIGMA-FILE.md)

## Fichiers du repo

| Chemin | Rôle |
|--------|------|
| `.cursor/mcp.json` | Serveur MCP Figma (`https://mcp.figma.com/mcp`) |
| `docs/FIGMA-COMPLETE-SPEC.md` | Spec écrans |
| `docs/design-tokens.json` | Design tokens |
| `docs/FIGMA-PROTOTYPE-FLOWS.md` | Navigation prototype |
| `apps/web/` | Implémentation UI (source de vérité runtime) |

## Connexion MCP (une fois)

1. Cursor **Settings → MCP** → activer **Figma**
2. Authentification navigateur (compte Figma)
3. Redémarrer Cursor si les outils n’apparaissent pas

## Workflows

### Frame Figma → code

```
@docs/FIGMA-COMPLETE-SPEC.md
Implémente ce frame : [URL Figma]
```

### Spec → code (sans URL)

```
Implémente l'écran Content §4.3 dans apps/web/app/content/page.tsx
```

### Code → Figma (capture)

Utiliser l’outil MCP `generate_figma_design` avec `outputMode: existingFile` et `fileKey: dILiXDcsASKX05l1pxcWwR`. Ouvrir l’URL locale dans le navigateur et valider la toolbar Figma.

## Tokens dans Figma

1. Plugin **Tokens Studio**
2. Import `docs/design-tokens.json`
3. Générer les variables Figma

## Dépannage

| Problème | Action |
|----------|--------|
| MCP gris | Reconnecter le compte Figma |
| Capture bloquée en `pending` | Confirmer dans la toolbar navigateur |
| Quota Starter | Limiter `use_figma` ; privilégier captures HTML |
