# Google → sites web → contacts

**`web-run`** = recherche **Google**, crawl des **sites d’entreprises**, extraction **e-mail / WhatsApp**.

**Pas de LinkedIn. Pas de Instagram.** Pas de session à enregistrer.

## Commande

```powershell
cd c:\client

python -m scraper.cli web-run `
  --query "agence événementiel Tunis contact email" `
  --limit 10
```

Résultat : `leads/scraper_web_google.csv` (ou `SCRAPER_WEB_OUTPUT_CSV` dans `.env`).

## Important : API Google CSE (nouveaux comptes)

Google indique que **Custom Search JSON API n’est plus disponible pour les nouveaux clients** (fin du service prévue en 2027).  
Si vous avez **403** malgré API activée + clé + CX corrects → c’est **normal** pour un compte récent.

**À utiliser à la place :**

```env
SCRAPER_WEB_SEARCH_PROVIDER=bing
```

ou `google_playwright` (Chrome sur google.com, `SCRAPER_HEADLESS=false`).

Les champs `SCRAPER_WEB_GOOGLE_API_KEY` / `CX` ne servent que si Google vous a déjà accordé l’accès (ancien client).

## Moteur de recherche (`.env`)

```env
SCRAPER_WEB_SEARCH_PROVIDER=bing
SCRAPER_WEB_GOOGLE_USE_PLAYWRIGHT=true
SCRAPER_HEADLESS=false
```

Forcer le navigateur sur google.com :

```powershell
python -m scraper.cli web-run `
  --query "wedding planner Sousse" `
  --search-provider google_playwright
```

## Ce qui se passe

1. Google avec ta requête (LinkedIn/Instagram **exclus** de la recherche)
2. Pour chaque site trouvé : pages contact / mentions légales / accueil
3. CSV avec `site_web`, `email`, `whatsapp`, `domaine`

## Plusieurs niches

```powershell
python -m scraper.cli web-run `
  --query "agence événementiel Tunis, wedding planner Sfax, traiteur corporate" `
  --limit 15
```

## Erreur « Aucun site web trouvé »

Vérifiez l’API :

```powershell
python scripts/check_google_cse.py
```

**403 / access denied** → activer l’API sur le **même projet** que la clé :

1. https://console.cloud.google.com/apis/library/customsearch.googleapis.com  
2. **Activer** → attendre 1–2 min → relancer le script.

En attendant, dans `.env` :

```env
SCRAPER_WEB_SEARCH_PROVIDER=bing
```

Puis relancer `web-run` ou le dashboard (moteur **bing**).

## Si peu de résultats

- Ajoutez **contact**, **email**, un **ville/pays** dans la requête
- `SCRAPER_HEADLESS=false` pour voir Google (CAPTCHA)
- API Google CSE si CAPTCHA bloque

## LinkedIn ?

Utilisez l’autre commande (recherche **dans** LinkedIn) :

```powershell
python -m scraper.cli run --app linkedin --query "directeur marketing" --limit 10
```

Ce n’est **pas** `web-run`.
