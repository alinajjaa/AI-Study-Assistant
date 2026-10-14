---
title: AI Study Assistant
emoji: 📚
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: Assistant d'étude RAG sur tes cours PDF (tuteur, examens, flashcards)
---

# AI Study Assistant

Assistant d'étude qui travaille **uniquement à partir de tes cours** (PDF) : tuteur qui cite ses pages,
examens notés sur 20, flashcards, résumés et un agent qui choisit le bon outil.

Cette démonstration utilise le LLM **qwen/qwen3.8-27b** via l'API de **Groq**, les embeddings
**intfloat/multilingual-e5-small** et **Qdrant** en mode intégré.

## Utilisation

1. Crée un compte (email et mot de passe de démonstration : n'utilise pas un mot de passe réel).
2. Dans l'Assistant, importe un PDF de cours (avec du texte, pas une image scannée).
3. Pose une question, demande un résumé, un quiz ou des flashcards.

## Limites de cette démonstration

- **Données effacées au redémarrage du Space** (comptes, cours, conversations, examens) : le stockage du
  Space n'est pas persistant.
- **Offre gratuite de Groq** : limites de requêtes et de jetons par minute et par jour. Un examen complet
  peut prendre plusieurs minutes ; au-delà de la limite quotidienne, un message demande de réessayer plus tard.
- **MLflow désactivé** (aucun suivi des générations).
- Ne dépose pas de documents contenant des données personnelles.

Code source et documentation : voir le dépôt du projet (`docs/deploiement.md`).
