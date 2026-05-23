# Dossier clients (hors dépôt)

Ce répertoire sert à stocker **localement** les documents commerciaux par client (audits, contrats, briefs, emails d’envoi).

- Tout fichier placé ici est **ignoré par Git** (sauf ce README).
- Le code et la doc technique du projet restent dans `docs/` à la racine (`ARCHITECTURE-CIBLE-MIGRATION.md`, etc.).

## Organisation suggérée

```
docs/clients/
  nom-client/
    audit.md
    contrat.md
    brief.md
```

Ne pas renommer ce dossier en `docs/dcb/` ou autre nom lié à un client dans le dépôt principal.
