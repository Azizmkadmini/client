# Déploiement gratuit (0 €) — AI Acquisition OS

> Objectif : avoir une **URL publique** (app + API) sans payer.  
> Limites : veille automatique, quotas, pas de workers Playwright fiables en cloud gratuit.

---

## Architecture gratuite recommandée

| Composant | Service gratuit | URL exemple |
|-----------|-----------------|-------------|
| **Front Next.js** | [Vercel](https://vercel.com) | `https://ton-app.vercel.app` |
| **API FastAPI** | [Render](https://render.com) | `https://ton-api.onrender.com` |
| **Postgres** | [Neon](https://neon.tech) | connexion dans `DATABASE_URL` |
| **Redis** (optionnel) | [Upstash](https://upstash.com) | `rediss://...` |
| **Workers / scraper** | **Ton PC** (local) | pointent vers API cloud |

Les workers avec navigateur (LinkedIn) ne tournent **pas bien** sur Render/Vercel gratuits → garde-les en local au début.

---

## Étape 1 — Postgres gratuit (Neon)

1. Crée un compte sur https://neon.tech  
2. Nouveau projet → copie `DATABASE_URL`  
3. Dans `.env` (et plus tard variables Render) :

```env
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

4. En local, applique les schémas :

```powershell
cd c:\client
python scripts\bootstrap_saas.py --email admin@tonemail.com --password <secret> --postgres
```

---

## Étape 2 — API sur Render (gratuit)

1. Pousse le code sur **GitHub** (repo privé ou public)  
2. https://render.com → **New → Web Service**  
3. Connecte le repo, racine `c:\client` (racine du monorepo)  
4. Paramètres :

| Champ | Valeur |
|-------|--------|
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| Plan | **Free** |

5. Variables d’environnement (Environment) — minimum :

```env
APP_ENV=production
STORAGE_BACKEND=postgres
DATABASE_URL=<neon>
JWT_SECRET=<génère 64 caractères aléatoires>
SECRETS_ENCRYPTION_KEY=<32+ caractères>
WEB_APP_URL=https://ton-app.vercel.app
CORS_ORIGINS=https://ton-app.vercel.app
AI_PROVIDER=template
# ou GROQ_API_KEY si tu as quota gratuit
```

6. Deploy → note l’URL : `https://ton-api.onrender.com`  
7. Test : `https://ton-api.onrender.com/docs`

**Note :** le plan gratuit **s’endort** après ~15 min sans trafic → premier appel lent (30–60 s).

---

## Étape 3 — Front Next.js sur Vercel (gratuit)

1. https://vercel.com → importe le repo GitHub  
2. **Root Directory** : `apps/web`  
3. Framework : Next.js (auto)  
4. Variables :

```env
NEXT_PUBLIC_API_URL=https://ton-api.onrender.com
```

5. Deploy → URL : `https://ton-app.vercel.app`

6. Retourne sur **Render** → mets à jour `CORS_ORIGINS` et `WEB_APP_URL` avec l’URL Vercel exacte → redeploy API.

---

## Étape 4 — Redis gratuit (optionnel)

1. https://upstash.com → base Redis gratuite  
2. Copie `UPSTASH_REDIS_REST_URL` ou URL Redis classique  
3. Sur Render :

```env
REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379
```

Sans Redis : l’API fonctionne en mode sync (OK pour début).

---

## Étape 5 — Admin & login

En local (une fois), avec `DATABASE_URL` Neon :

```powershell
python scripts\bootstrap_saas.py --email admin@tonemail.com --password <mot-de-passe-fort>
```

Puis sur le site déployé : **https://ton-app.vercel.app/login**

---

## Étape 6 — Workers / LinkedIn (local → cloud)

Sur **ton PC**, `.env` pointe vers le cloud :

```env
DATABASE_URL=<même Neon>
REDIS_URL=<Upstash si utilisé>
NEXT_PUBLIC_API_URL=https://ton-api.onrender.com
```

```powershell
python -m workers.run_all
python outreach.py login linkedin-scrape
```

Les sessions restent dans `sessions/` sur ton PC — c’est normal en mode gratuit.

---

## Ce qui ne sera PAS déployé gratuitement (honnête)

| Élément | Raison |
|---------|--------|
| Workers 24/7 Playwright | RAM, navigateur, anti-bot |
| Streamlit public | Pas nécessaire ; garde en local |
| Stripe live | Pas besoin au début |
| Domaine custom | Payant (~10 €/an) — URLs Vercel/Render suffisent |

---

## Checklist « c’est déployé »

- [ ] `https://ton-api.onrender.com/docs` répond  
- [ ] `https://ton-app.vercel.app` affiche le design sombre  
- [ ] Login fonctionne  
- [ ] CORS : pas d’erreur réseau dans la console navigateur (F12)  
- [ ] Neon : données visibles après actions dans l’app  

---

## Dépannage

| Problème | Solution |
|----------|----------|
| API lente au 1er clic | Render free — attendre le réveil |
| CORS error | `CORS_ORIGINS` = URL Vercel exacte, sans `/` final |
| 401 login | Re-run `bootstrap_saas.py` avec le même `DATABASE_URL` |
| Build Vercel fail | Root = `apps/web`, pas la racine repo |

---

## Alternative : tout sur 1 VPS gratuit

**Oracle Cloud Always Free** (VM Ubuntu) : Docker compose complet, mais setup plus long.  
Utile quand tu voudras workers 24/7 sans payer Render/Vercel.

```bash
docker compose -f docker-compose.yml -f docker-compose.saas.yml up -d
```

---

## Résumé 3 actions

1. **Neon** → `DATABASE_URL`  
2. **Render** → API  
3. **Vercel** → `apps/web` + `NEXT_PUBLIC_API_URL`

Coût : **0 €** avec les limites des plans gratuits.
