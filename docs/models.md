# Modèles et paramètres

## 1. Vue d'ensemble

| Rôle | Modèle / outil | Où il tourne | Configuration |
|---|---|---|---|
| LLM (génération, tuteur, agent) | **qwen2.5:7b** (Qwen 2.5, 7 milliards de paramètres, quantifié Q4 par Ollama) | **Ollama**, en local (`http://localhost:11434/v1`) | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT` |
| Embeddings | **intfloat/multilingual-e5-small** (Hugging Face, 384 dimensions) | en local, `sentence-transformers` | `EMBED_MODEL` |
| Base vectorielle | **Qdrant** (collection `courses`, distance cosinus) | Docker, en local (`http://localhost:6333`) | `QDRANT_URL` |
| Modèle affiné (optionnel) | **Qwen/Qwen2.5-1.5B-Instruct** + adaptateur LoRA [Alinajjaa/study-tutor-qwen2.5-1.5b-lora](https://huggingface.co/Alinajjaa/study-tutor-qwen2.5-1.5b-lora) | entraînement sur Google Colab, démonstration en local (4 bits) | `LLM_PROVIDER=hf-local`, `HF_BASE_MODEL`, `HF_ADAPTER` |

En développement, l'application utilise **`qwen2.5-7b-gpu`** : les mêmes poids que qwen2.5:7b, chargés
entièrement sur le GPU par le [`Modelfile`](../Modelfile) de la racine (`num_gpu 99`, `num_ctx 4096`), avec
la *flash attention*, un cache KV en 8 bits et `keep_alive` illimité côté serveur Ollama. Benchmark MLflow
du 18/10/2026 (`app/phase5_evaluation/results/Chapter1_Part_1_2026-10-18_1729.csv`, un run par génération),
comparé à qwen2.5:7b (moyenne de 3 runs, 14/10) : examen complet 158 → 102 s, 10 flashcards 129 → 62 s,
résumé 42 → 28 s, tuteur 6,1 → 4,0 s par question, avec la même qualité (20/20, 10/10 cartes, 100 % de
pages valides, `hit_3` et refus hors cours à 100 %). Détails : [prompts.md §12.3](prompts.md#123-optimisation-gpu-dollama-configuration-du-serveur).

## 2. LLM : qwen2.5:7b via Ollama

### Pourquoi ce choix

- **Matériel** : le poste de développement a un GPU **RTX 4050 avec 6 Go de VRAM**. qwen2.5:7b quantifié
  (≈ 4,7 Go) tient dans cette mémoire. Un modèle de 14 milliards de paramètres ou plus ne tient pas.
- **API Hugging Face abandonnée** : les premiers essais utilisaient l'API d'inférence de Hugging Face. Elle
  renvoyait des **erreurs 402 (Payment Required)** une fois le quota gratuit épuisé, ce qui bloquait le
  développement. Un modèle local n'a ni quota ni coût par appel.
- **Français et JSON** : Qwen 2.5 écrit correctement en français, suit bien les consignes et prend en charge
  le **tool calling** (agent) et les **sorties structurées** (`json_schema`) dans Ollama.
- **Confidentialité** : les cours et les questions ne quittent pas la machine.

### Compatibilité OpenAI / Groq

Le code n'utilise que l'**API compatible OpenAI** (`openai` pour `chat()`, `langchain-openai` pour l'agent).
Changer de fournisseur ne demande que le fichier `.env` :

| Fournisseur | `LLM_BASE_URL` | `LLM_API_KEY` | `LLM_MODEL` |
|---|---|---|---|
| Ollama (par défaut) | `http://localhost:11434/v1` | `ollama` (valeur quelconque non vide) | `qwen2.5:7b` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` (`gsk_…`), prioritaire sur `LLM_API_KEY` | `qwen/qwen3.8-27b` |
| OpenAI | `https://api.openai.com/v1` | clé OpenAI | ex. `gpt-4o-mini` |

Modèle Groq retenu : **qwen/qwen3.8-27b** (tool calling et `json_schema` pris en charge, bon en français ;
modèle « preview » chez Groq). Les modèles gpt-oss échouent sur les schémas du projet et les modèles Llama ne
sont pas accessibles avec la clé du projet. Le client replie automatiquement `json_schema` sur `json_object`
si un modèle le refuse, et gère les erreurs 429 de l'offre gratuite (attente puis nouvel essai, message clair
si la limite persiste). Détails, mesures et comparaison avec qwen2.5:7b : [deploiement.md](deploiement.md) et
[evaluation.md](evaluation.md#28-qwen257b-en-local-contre-qwenqwen38-27b-sur-groq).

### Paramètres d'appel

| Paramètre | Valeur | Fichier |
|---|---|---|
| `LLM_TIMEOUT` | 120 s par appel | `app/core/config.py` |
| `max_retries` (client OpenAI) | 1 | `app/phase1_llm/llm.py`, `app/phase6_agent/graph.py` |
| `temperature` par défaut | 0.3 | `chat()` |
| `max_tokens` par défaut | 1024 | `chat()` |

Températures et `max_tokens` par usage :

| Usage | Température | `max_tokens` | Sortie |
|---|---|---|---|
| Tuteur RAG | 0.3 | 1024 | texte (markdown) |
| Examen : génération QCM / V-F / courte / ouverte | 0.5 | 500 / 300 / 300 / 600 | `json_schema` |
| Examen : vérification QCM / V-F / rédigée | 0 | 100 / 60 / 20 | `json_schema` |
| Flashcards : concepts | 0.2 | 200 | `json_schema` |
| Flashcards : carte (1re / 2e tentative) | 0.4 / 0.7 | 250 | `json_schema` |
| Flashcards : vérification | 0 | 20 | `json_schema` |
| Résumé : section / vue d'ensemble / thème | 0.3 puis 0.5 | 600 / 500 / 900 | `json_schema` |
| Agent : choix de l'outil et réponse finale | 0 | défaut du serveur | tool calling |
| Agent : classification de repli | 0 | 150 | `json_schema` |
| Agent : notions d'un quiz | 0 | 300 | `json_schema` |

## 3. Embeddings : intfloat/multilingual-e5-small

### Pourquoi ce choix

- **Multilingue** : les cours sont en français ou en anglais, les questions en français. e5 multilingue
  rapproche une question française d'un passage anglais.
- **Petit** (≈ 118 millions de paramètres, 384 dimensions) : calcul rapide sur CPU, mémoire GPU laissée au LLM.
- **Local** : téléchargé une fois depuis le Hub Hugging Face, puis utilisé hors ligne (pas d'API, donc pas
  d'erreur 402).

### Utilisation

- Préfixes exigés par e5 : `passage: ` pour les morceaux du cours, `query: ` pour la question.
- Vecteurs **normalisés** : le produit scalaire est la similarité cosinus.
- Modèle chargé une seule fois (`lru_cache`).
- Les embeddings servent aussi à détecter les **doublons de sens** (questions d'examen, concepts, cartes)
  et à retrouver les passages d'un concept (flashcards).

## 4. Qdrant

- Collection `courses`, taille des vecteurs = dimension du modèle (384), distance **cosinus**.
- Chaque point contient : `course`, `page`, `text`, `user_id`.
- Index de payload sur `user_id` (entier) : **chaque lecture filtre par `user_id`**, un étudiant ne voit
  jamais les cours d'un autre.
- Réimporter un cours supprime d'abord ses anciens points (pas de doublons).

## 5. Tous les paramètres

### Découpage et recherche (RAG)

| Paramètre | Valeur | Rôle | Fichier |
|---|---|---|---|
| `CHUNK_SIZE` | 800 caractères | taille d'un morceau | `app/core/config.py` |
| `CHUNK_OVERLAP` | 150 caractères | chevauchement entre deux morceaux | `app/core/config.py` |
| `MIN_CHUNK_CHARS` | 120 caractères | morceau plus court ignoré (titre, schéma) ; un dernier morceau trop court est rattaché au précédent | `app/phase2_embeddings/ingest.py` |
| `TOP_K` | 3 | passages retrouvés pour le tuteur | `app/core/config.py` |
| `SCORE_MARGIN` | 0.03 | un passage est gardé s'il est à moins de 0.03 du meilleur score | `app/phase3_rag/rag.py` |
| `HISTORY_TURNS` | 3 échanges | mémoire de la conversation | `app/phase3_rag/rag.py` |
| `HISTORY_ANSWER_CHARS` | 600 | troncature d'une réponse précédente dans le prompt | `app/phase3_rag/rag.py` |
| `SHORT_QUESTION_WORDS` | 4 mots | une question plus courte est une question de suivi (recherche reformulée avec la question précédente) | `app/phase3_rag/rag.py` |

Le découpage se fait **page par page** : chaque morceau garde son numéro de page, ce qui permet les
citations `[p.X]`.

### Examens

| Paramètre | Valeur | Rôle |
|---|---|---|
| `CALLS_PER_QUESTION` | 5 | budget d'appels de génération par question demandée (échecs et rejets compris) |
| `SIMILARITY_THRESHOLD` | 0.96 | au-delà, deux questions sont des doublons de sens |
| `CATCH_UP_SIMILARITY` | 0.985 | seuil assoupli dans le dernier tiers du budget |
| `EXAM_MIN_CHUNK_CHARS` | 250 | passages plus courts exclus des examens |
| Barème « complet » | 8 QCM × 1 pt, 4 V/F × 1 pt, 2 courtes × 2 pts, 1 ouverte × 4 pts | toujours 20 points ; points manquants complétés par des V/F |
| Barème « qcm » | 5, 10 ou 20 questions | 4, 2 ou 1 point par question |

### Flashcards

| Paramètre | Valeur | Rôle |
|---|---|---|
| `CONCEPT_WINDOW` | 3 passages | lus ensemble pour extraire les concepts |
| `CANDIDATE_MARGIN` | 2.5 | concepts préparés par carte demandée (certaines cartes sont rejetées) |
| `CONCEPT_SIMILARITY` | 0.97 | deux concepts identiques au-delà |
| `CARD_SIMILARITY` | 0.92 | deux cartes en double au-delà |
| `CONTEXT_PASSAGES` | 2 | passages retrouvés pour rédiger une carte |
| `MIN_PASSAGE_CHARS` | 60 | passages plus courts exclus |
| Tentatives par concept | 2 | seconde chance à température plus haute |
| Nombre de cartes | 10, 20 ou 30 | |

### Résumés

| Paramètre | Valeur | Rôle |
|---|---|---|
| `SECTION_SIZE` | 6 passages | taille d'une section (étape « map ») |
| `TOPIC_PASSAGES` | 6 | passages retrouvés pour un thème (on en cherche 12, puis on écarte les trop courts) |
| `MIN_PASSAGE_CHARS` | 60 | passages plus courts exclus |
| `ATTEMPTS` | 2 | tentatives par appel structuré |
| Cache | 1 résumé « cours entier » par cours et par étudiant | invalidé quand le cours est réimporté |

### Agent et tâches de fond

| Paramètre | Valeur | Rôle | Fichier |
|---|---|---|---|
| `MAX_TOOL_CALLS` | 3 | outils exécutés au plus par message | `app/phase6_agent/graph.py` |
| `RECURSION_LIMIT` | 15 | garde-fou LangGraph | `app/phase6_agent/graph.py` |
| `HISTORY_MESSAGES` / `HISTORY_CHARS` | 6 messages / 300 caractères | historique donné à l'agent | `app/phase6_agent/graph.py` |
| `FINAL_SENTENCES` / `FINAL_CHARS` | 3 phrases / 350 caractères | longueur de la réponse finale | `app/phase6_agent/graph.py` |
| `SYNC_WAIT_S` | 20 s | au-delà, la route répond 202 et le frontend consulte la tâche | `app/phase6_agent/routes.py` |
| `WORKERS` | 2 threads | tâches de fond simultanées | `app/phase6_agent/jobs.py` |
| `JOB_TTL_S` | 3600 s | une tâche terminée est oubliée après une heure | `app/phase6_agent/jobs.py` |
| `MESSAGE_MAX` | 2000 caractères | longueur maximale d'un message | `app/phase6_agent/schemas.py` |

### Profil et points faibles

| Paramètre | Valeur | Rôle |
|---|---|---|
| `WEAK_MIN_REVIEWS` | 2 | révisions ou réponses de quiz minimales pour qu'un concept soit un point faible |
| `WEAK_MAX` | 5 | points faibles affichés au plus |
| `SUGGESTION_MIN_REVIEWS` | 20 | révisions nécessaires avant une suggestion de niveau |
| `SUGGEST_UP_ABOVE` / `SUGGEST_DOWN_BELOW` | 85 % / 40 % | seuils de suggestion (jamais de changement automatique) |

## 6. Fine-tuning (phase 4 bis)

Détails complets : `backend/app/phase4_finetuning/README.md`.

- **Modèle** : Qwen/Qwen2.5-1.5B-Instruct (assez petit pour un entraînement QLoRA sur un GPU T4 de Colab et
  une démonstration en 4 bits sur 6 Go de VRAM).
- **Objectif** : apprendre le **style** du tuteur (citations `[p.X]`, adaptation au niveau), pas de
  nouvelles connaissances.
- **Modèle publié** : [Alinajjaa/study-tutor-qwen2.5-1.5b-lora](https://huggingface.co/Alinajjaa/study-tutor-qwen2.5-1.5b-lora)
  (adaptateur seul, quelques dizaines de Mo ; le modèle de base est téléchargé depuis le Hub).
- **Données** : 300 exemples gardés sur 372 générés par qwen2.5:7b (81 %), découpés par question :
  train 269 / test 31. Rejets : incertitude 33, hors cours 14, longueur 14, référence 9, anglais 2.

| Hyperparamètre | Valeur |
|---|---|
| Quantification | 4 bits nf4, double quantification (QLoRA) |
| Précision | calcul en float16 (le T4 ne gère pas bfloat16), poids LoRA en float32 |
| LoRA | `r=16`, `alpha=32`, `dropout=0.05` |
| Modules ciblés | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| Époques / étapes | 3 / 51 |
| Lot effectif | 16 (4 × 4 accumulations) |
| Taux d'apprentissage | 2e-4, cosinus, 5 % de préchauffage |
| Longueur maximale | 1 024 jetons |
| Optimiseur | `paged_adamw_8bit`, `gradient_checkpointing` |
| Génération (évaluation) | température 0.3, `top_p` 0.9, `repetition_penalty` 1.05, 512 jetons au plus |
| Matériel | Google Colab, GPU T4 (15 Go) |

- **Perte finale** : entraînement 0,710 (moyenne sur l'entraînement), test 0,827. Courbe :
  [images/loss_curve.png](images/loss_curve.png).
- **Résultats** (31 réponses de test, juge qwen2.5:7b) : citations `[p.X]` valides **3 % → 97 %** ;
  longueur adaptée au niveau (débutant 98 → 126 mots, avancé 107 → 84) ; note moyenne du juge 3,99 → 4,13 ;
  respect du niveau +0,5 en débutant, **aucun gain en avancé**. Détails : [evaluation.md](evaluation.md#26-fine-tuning-lora-du-style-du-tuteur-phase-4-bis).
- **Démonstration** : `LLM_PROVIDER=hf-local` et `HF_ADAPTER=Alinajjaa/study-tutor-qwen2.5-1.5b-lora`
  (désactivé par défaut, ≈ 1,5 Go de VRAM en 4 bits). Seules les réponses en texte libre passent par le
  modèle affiné ; les demandes JSON restent sur Ollama. L'application garde qwen2.5:7b par défaut : le
  modèle affiné écrit mieux dans le style attendu, mais un modèle de 1,5 milliard de paramètres raisonne
  moins bien, et il ne sait pas produire les sorties JSON des autres fonctionnalités.

## 7. Limites constatées

Constatées pendant le développement avec qwen2.5:7b ; chacune a reçu une protection dans le code.

| Limite | Effet | Protection |
|---|---|---|
| Lenteur d'un LLM local | qwen2.5:7b : examen complet ≈ 2 min 40, 10 flashcards ≈ 2 min 10, résumé ≈ 42 s ; qwen2.5-7b-gpu : ≈ 1 min 40, ≈ 1 min, ≈ 28 s | variante 100 % GPU, tâches de fond (202 + consultation), budgets d'appels |
| Sorties invalides (12 à 39 % de rejets de validation selon les runs) | JSON valide mais contenu hors consignes : négations, « combien », choix « Tous les… », texte resté en anglais | validateurs Pydantic, nouvelles tentatives, budget d'appels |
| Réponses fausses | corrigé d'examen ou verso de carte qui contredit le cours | auto-vérification à température 0 |
| Mauvais numéros de page | page citée absente des passages | page remplacée par la plus proche (examens, cartes) ; puce rejetée (résumés) |
| Mots ou lettres étrangers | caractères cyrilliques glissés dans un mot (« effектer ») | `check_french` |
| Antislashs mal échappés dans le JSON | `C:\flutter\bin` devient des caractères de contrôle | `capitalize_first` restaure les antislashs |
| Refus complété | le modèle ajoute du texte après « Cette information n'est pas présente dans le cours. » | seule la phrase de refus est gardée |
| Mauvais outil | une demande de résumé du cours entier routée vers `ask_course` ; appel d'outil écrit en texte | garde-fou `reroute_course_summary`, repli par classification, texte JSON ignoré |
| Réponse finale trop longue | l'agent recopie ou invente les questions du quiz | `short_reply` (coupé avant la liste, 3 phrases) |
| Prénom répété | le modèle reprend un prénom tapé par l'étudiant (« Bonjour Ali ! ») | réponses masquées dans les traces MLflow |
| Partie incomplète | la question ouverte échoue parfois (1 run d'examen sur 3) ; 14 cartes sur 20 demandées dans un essai | complément par des V/F pour garder 20 points ; nombre réel de cartes affiché |
| PDF scannés | aucun texte extrait (pas d'OCR) | erreur 422 claire à l'import |
| Modèle affiné (1,5 B) : pas de gain au niveau avancé, fidélité en baisse au niveau débutant (4,7 → 4,0) | réponses plus « pédagogiques » mais parfois moins fidèles au passage | désactivé par défaut ; qwen2.5:7b reste le LLM de l'application |
| Fine-tuning sur T4 | bfloat16 non pris en charge ; poids LoRA en float16 → erreur « Attempting to unscale FP16 gradients » | notebook : float16 pour le calcul, `bf16=False`, poids LoRA convertis en float32 |
| Petit modèle d'embeddings | moins précis qu'un grand modèle sur des questions très vagues | reformulation des questions de suivi, marge de score |
