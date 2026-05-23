# Guide utilisateur — Outreach Platform

Ce guide décrit le parcours complet pour installer, configurer, piloter et automatiser la plateforme.

## 1. Vue d'ensemble

La plateforme enchaîne six étapes dans un seul orchestrateur :

1. **Scraper** : produit `leads/scraper_output.csv` ou s'exécute via `SCRAPER_COMMAND`.
2. **Connecteur** : nettoie, déduplique, tague et met en file.
3. **File** : stocke les leads prêts dans `bot/leads_queue.json`.
4. **Ingest** : copie la file vers le store outreach `data/outreach_leads.csv`.
5. **IA + bots** : génère un message unique par lead et envoie sur le canal adapté.
6. **Logs + relances** : journalise les envois et planifie les suivis.

## 2. Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

Variables essentielles dans `.env` :

- `SCRAPER_OUTPUT_CSV` et `CONNECTOR_SOURCE_CSV` : entrée scraper.
- `LEADS_CSV` : store outreach.
- `AI_PROVIDER`, `OLLAMA_*` ou `OPENAI_*` : génération IA.
- `SMTP_*` : canal email.
- `DASHBOARD_PASSWORD` : protection du dashboard.
- `API_KEY` : protection API.

## 3. Démarrage du dashboard pro

```bash
streamlit run dashboard.py
```

Onglets :

- **Vue d'ensemble** : KPIs, statuts, envois par canal.
- **Pipeline** : exécution complète, connecteur seul, ingest, envoi par canal.
- **Leads** : filtres, import CSV scraper, marquage des réponses.
- **File** : contenu de la file bot.
- **Logs** : envoyés, échecs, réponses.
- **Conformité** : opt-out.
- **Guide** : rappel opérationnel.
- **Paramètres** : config active, quotas journaliers, sessions.

## 4. Ligne de commande

```bash
python run.py run --source csv
python run.py schedule --hours 6 --limit 5
python run.py status
python outreach.py login linkedin
python outreach.py reply <lead_id>
uvicorn api.main:app --host 127.0.0.1 --port 8000
```

## 5. Parcours type

### Première campagne

1. Remplir `leads/scraper_output.csv`.
2. Lancer `python run.py run --source csv --limit 3`.
3. Vérifier le dashboard : file, leads `queued`, logs.
4. Pour les réseaux sociaux, faire `python outreach.py login <canal>` avant l'envoi automatique.

### Automatisation continue

1. Définir `SCRAPER_COMMAND` si le scraper est externe.
2. Lancer `python run.py schedule --hours 6 --limit 5`.
3. Surveiller les logs et le registre opt-out.

### Réponse reçue

1. Ouvrir l'onglet **Leads** du dashboard.
2. Copier l'`id` du lead.
3. Marquer comme répondu pour stopper les relances.

## 6. API externe

Endpoint principal :

```http
POST /orchestrator/run
X-API-Key: <API_KEY>
Content-Type: application/json

{
  "source": "csv",
  "retry_failed": false,
  "per_channel_limit": 5,
  "run_scraper_step": true,
  "run_outreach": true
}
```

## 7. Bonnes pratiques

- Ne mélangez pas l'ancien import direct et le pipeline orchestré.
- Gardez le scraper et le store outreach séparés.
- Respectez les limites journalières par canal.
- Utilisez le registre opt-out avant toute nouvelle campagne sur une base existante.
