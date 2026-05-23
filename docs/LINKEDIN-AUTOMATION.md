# LinkedIn — mode stable (automatisation)

## Démarrage (obligatoire)

```powershell
cd c:\client
python outreach.py login linkedin
```

Alternative (Chrome déjà connecté) :

```powershell
# Fermer Chrome complètement, puis :
python outreach.py login linkedin --from-browser chrome
```

Vérifier avant chaque collecte :

```powershell
python scripts/check_linkedin_session.py
```

## Variables `.env` (mode stable — défaut)

| Variable | Valeur recommandée | Rôle |
|----------|-------------------|------|
| `SCRAPER_STABLE_LINKEDIN_MODE` | `true` | Pauses longues, limites basses |
| `SCRAPER_FAST_MODE` | `false` | Ne pas accélérer globalement |
| `SCRAPER_INTER_PROFILE_PAUSE_SECONDS` | `3`–`5` | Pause entre profils |
| `SCRAPER_LINKEDIN_MAX_PROFILES_TO_TRY` | `25` | Max profils testés / recherche |
| `SCRAPER_LINKEDIN_MAX_SEARCH_SCROLL_ROUNDS` | `5` | Scroll résultats |
| `SCRAPER_LINKEDIN_MAX_SEARCH_TERMS` | `4` | Max mots-clés par run |
| `SCRAPER_HEADLESS` | `false` | Fenêtre visible = moins de blocages |
| `LINKEDIN_DAILY_MAX` | `15`–`20` | Quota bot outreach LinkedIn |

## Lancer une collecte

```powershell
python -m scraper.cli run `
  --query "directeur marketing,fondateur" `
  --mode keyword `
  --app linkedin `
  --linkedin-scope people `
  --include-location "France,Tunisie" `
  --limit 10
```

## Si checkpoint / déconnexion

1. Arrêter tout scrape.
2. Se connecter dans **Chrome normal**, finir la vérification.
3. Attendre **24–48 h** si blocage fort.
4. `python outreach.py login linkedin`
5. Reprendre avec `--limit 5` puis monter.

## Mode rapide (non recommandé pour LinkedIn)

```env
SCRAPER_STABLE_LINKEDIN_MODE=false
SCRAPER_FAST_MODE=true
SCRAPER_INTER_PROFILE_PAUSE_SECONDS=0.7
```

Risque élevé de vérification LinkedIn.

## CDP (session Chrome réelle)

```powershell
chrome.exe --remote-debugging-port=9222
```

```env
BROWSER_CONNECTION_MODE=cdp
BROWSER_CDP_URL=http://127.0.0.1:9222
```

Puis scraper — réutilise la session du navigateur ouvert.
