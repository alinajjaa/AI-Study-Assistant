# Frontend — AI Study Assistant

Interface Angular 22 (composants autonomes, signals, sans zone.js) de l'assistant d'étude : connexion et
inscription, Assistant (questions sur les cours, quiz, examens, flashcards, résumés), révision des flashcards,
résumés, historique des examens, cours importés et profil.

Le frontend appelle l'API FastAPI sur `http://localhost:8000/api` avec `ng serve`
(`src/environments/environment.development.ts`) et sur `/api` (même origine) dans le build de production
(`src/environments/environment.ts`). Le backend doit donc tourner pour utiliser l'application.

## Commandes

À lancer dans le dossier `frontend/` :

```bash
npm ci                     # installe les dépendances exactes de package-lock.json
npx ng serve               # serveur de développement sur http://localhost:4200
npx ng test --watch=false  # tests unitaires (vitest + jsdom, sans navigateur)
npx ng build               # build de production dans dist/frontend/browser
```

Couverture des tests : `npx ng test --watch=false --coverage`.

## Pour aller plus loin

Architecture, configuration du backend, lancement complet et déploiement Docker : voir le
[README racine](../README.md).
