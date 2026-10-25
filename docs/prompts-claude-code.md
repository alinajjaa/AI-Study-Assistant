# Prompts utilisés avec Claude Code

Ce document présente les **prompts envoyés à Claude Code** pour générer le code du projet, module par module :
le prompt principal (extrait des sessions enregistrées), la technique de prompting, les itérations et
corrections, et les jetons consommés. Les mesures d'usage globales sont dans
[claude-code-usage.md](claude-code-usage.md) ; les prompts **de l'application** (envoyés à qwen2.5 ou Groq)
sont dans [prompts.md](prompts.md).

Sources : sessions JSONL de Claude Code (11/10 au 20/10/2026), lues par `backend/scripts/claude_usage.py` ;
jetons par demande dans `docs/mesures/claude_code_demandes.csv` (instantané final du 20/10/2026, 16 h 33). Les
demandes analysées ci-dessous sont les 32 demandes enregistrées au 19/10 ; les suivantes portent sur les livrables
(module transverse, [claude-code-usage.md](claude-code-usage.md) §4). Les
extraits sont recopiés des sessions ; `[…]` marque une coupe. Les adresses email des commandes sont remplacées
par `etudiant@example.com`.

---

## 1. Technique de prompting commune

### 1.1 Structure des demandes

Les 32 demandes de l'équipe se répartissent en **22 demandes longues** (plus de 1 500 caractères, 3 983 en
moyenne, jusqu'à 9 444), qui lancent une fonctionnalité, et **10 demandes courtes** de suivi (validation,
précision, correction). Éléments présents dans les 22 demandes longues (recherche par expressions régulières
sur le texte des demandes) :

| Élément | Demandes longues | Rôle |
|---|---|---|
| Étapes numérotées (`1.`, `ÉTAPE 1`) | 21 / 22 | découpe le travail ; Claude Code les suit dans l'ordre et en rend compte une par une |
| Interdictions (« Ne modifie pas… », « Ne casse… », « Hors périmètre ») | 18 / 22 | protège le code existant et le contrat de l'API |
| Rapport final demandé (fichiers, commandes, checklist, « choix faits sans moi ») | 18 / 22 | rend le travail relisable ; fait remonter les décisions implicites |
| Critères d'acceptation par les tests (`pytest`, `ng test`, `ng build`, « tous les tests ») | 17 / 22 | condition de fin vérifiable par l'outil lui-même |
| Contexte (« Contexte : projet … ») | 16 / 22 | état du projet et fonctionnalités à ne pas casser |
| Interdiction explicite des commandes git | 16 / 22 | l'équipe garde la main sur l'historique Git |
| Objectif (« Objectif : … ») | 15 / 22 | une phrase qui dit ce qui doit exister à la fin |
| Règles techniques (standalone, signals, TypeScript strict, Pydantic, `json_schema`, `mask_pii`) | 15 / 22 | impose les conventions du projet |
| Contrat d'API (routes, corps JSON, codes d'erreur) | 9 / 22 | le frontend est écrit contre un contrat exact, sans deviner |
| Confidentialité (données personnelles, `mask_pii`, aucun secret) | 9 / 22 | exigence du cahier des charges rappelée à chaque phase |
| Analyse avant de coder (« Avant de coder », « propose-moi… et attends ma validation ») | 6 / 22 | relecture du plan avant toute modification |
| Mesures chiffrées (durées, débits, taux) | 6 / 22 | ancre la demande sur des faits mesurés |
| Rôle (« Tu es ingénieur logiciel senior… ») | 1 / 22 | utilisé seulement pour la rédaction des livrables |

### 1.2 Gabarit retenu

Le gabarit suivant résume la forme des demandes longues ; il s'est stabilisé dès la deuxième phase.

```text
Contexte : projet AI Study Assistant (FastAPI + Angular). Fonctionnalités terminées qui doivent continuer à
marcher : <liste>.
Règles :
- N'exécute AUCUNE commande git.
- Ne modifie pas <ce qui doit rester stable> ; seulement <ce qui peut changer>.
- Exigence du projet : aucune donnée personnelle envoyée au LLM (mask_pii).
- Messages et interface en français ; respecte l'architecture existante.

Objectif : <une phrase>.

1. <étape> — <fichiers, signatures, valeurs par défaut>
2. <étape> — <comportement attendu, cas d'erreur>
…
N. Tests : <tests à ajouter>, puis tous les tests existants (pytest, ng build, ng test).

Rapport final en français : fichiers créés et modifiés, commandes, checklist manuelle, choix faits sans moi.
```

### 1.3 Ce qui a le mieux marché

- **Les critères vérifiables** (« `npx ng build` sans warning », « les 65 tests doivent passer ») : Claude Code
  relance les tests jusqu'au vert. 33 exécutions en échec sur 245 (instantané du 20/10) ont été corrigées avant
  le rapport final.
- **L'essai réel demandé ou laissé libre** : Claude Code a vérifié les fonctionnalités LLM avec le vrai Ollama
  et le vrai Qdrant, sur une base et un MLflow temporaires. 11 des 17 bugs relevés ont été trouvés ainsi.
- **« Choix faits sans moi »** : fait apparaître les écarts (URI MLflow changée, métrique redéfinie, fichier
  modifié sans demande) au lieu de les cacher.
- **Les contrats exacts** : avec les routes, les corps JSON et les codes d'erreur dans le prompt, le frontend
  a été écrit sans aller-retour sur l'API.
- **La validation en deux temps** (« propose-moi d'abord… attends ma validation ») pour les choix visuels et les
  changements d'API : 6 demandes, suivies d'une demande courte de validation avec des précisions.

### 1.4 Limites constatées

- Les interdictions ne sont **pas absolues** : deux commandes git en lecture seule ont été lancées malgré la
  règle, et signalées par Claude Code lui-même.
- Une demande doit tenir compte de l'état réel du dépôt : après le retrait volontaire de la plage de pages
  (§4.3), Claude Code l'a constaté et a demandé avant de la réintroduire, au lieu de supposer qu'elle existait.
- Les vérifications visuelles (navigateur, animations, focus) ne sont pas faites par l'outil : elles restent
  dans la checklist manuelle.

---

## 2. Module 1 — Architecture, tuteur RAG, intégration, déploiement (Najjaa Ali)

### 2.1 Demandes

| Date | Session | Demande | Appels API | Sortie (jetons) | Cache lu (jetons) | Durée active |
|---|---|---|---|---|---|---|
| 11/10 13:23 | `5d902768` | Frontend « AI Course Tutor » (upload PDF, choix du cours, questions-réponses avec pages) | 12 | 32 226 | 668 178 | 5,5 min |
| 11/10 13:55 / 14:03 | `5d902768` | Design du tuteur (proposition, puis validation avec 3 précisions) | 22 | 47 333 | 2 483 829 | 7,7 min |
| 13/10 23:44 | `2ab3ba04` | Phase « AI Personal Tutor » : comptes JWT, SQLite, cours privés, conversations avec mémoire, profil et niveau | 123 | 182 831 | 26 178 816 | 50,3 min |
| 14/10 12:08 | `c528cea3` | Fusion du tuteur dans la page unique « Assistant » + 4 bugs | 70 | 69 653 | 11 081 576 | 16,9 min |
| 14/10 16:19 | `20d36a24` | Déploiement : profils Ollama / Groq, Docker Compose, Hugging Face Spaces, benchmark Groq | 84 | 89 742 | 28 270 356 | 53,7 min |
| 18/10 17:48, 19/10 15:22 | `20d36a24` | Refonte du design (système de design, mode sombre, pages) | 100 | 124 685 | 71 708 954 | 27,3 min |
| 19/10 15:29 → 16:10 | `755606e7`, `b49e2763` | Barre latérale de la page Assistant (3 versions successives) | 168 | 275 811 | 35 906 950 | 60,5 min |
| 18/10 16:32 | `20d36a24` | Optimisation des performances (**travaux expérimentaux, non livrés**) | 91 | 133 335 | 45 998 849 | 52,1 min |

### 2.2 Prompt principal : phase « AI Personal Tutor » (13/10, 9 444 caractères)

```text
Contexte : projet « AI Study Assistant » (backend FastAPI dans backend/, frontend Angular dans frontend/).
Fonctionnalités déjà terminées qui doivent continuer à marcher :
- Tuteur RAG (app/phase3_rag) : questions sur les cours, réponses avec sources [p.X], masquage des données
  personnelles (app/core/privacy.py).
- Import de cours PDF (app/phase2_embeddings : ingest.py, vectorstore.py, embeddings.py), Qdrant collection
  "courses" (payload course/page/text).
- Examen PDF (app/phase4_exam) et flashcards (app/phase7_flashcards).
- LLM via Ollama (app/phase1_llm/llm.py), erreurs LLMError → 503.

Règles importantes :
- N'exécute AUCUNE commande git (pas de commit, push, branch, checkout…). Je gère Git moi-même.
- Ne modifie pas la logique interne des générateurs d'examen et de flashcards : seulement leurs points d'entrée
  (lecture des cours, routes).
- Exigence du projet : aucune donnée personnelle brute (email, nom) n'est envoyée au LLM. Seuls le niveau et les
  noms de concepts peuvent l'être.
- Le fichier .env ne doit jamais contenir de secret dans le code, ni être ajouté au dépôt.
- Respecte l'architecture existante : un dossier par phase côté backend, core/features/shared côté Angular
  (standalone, signals, même design et même thème sombre).
- Travaille dans l'ordre des étapes. À la fin de CHAQUE étape, lance les tests (pytest côté backend, ng build +
  ng test côté frontend) et vérifie que le tuteur, l'examen et les flashcards fonctionnent toujours. Si quelque
  chose casse, corrige avant de passer à l'étape suivante.

Objectif : phase « AI Personal Tutor » — comptes étudiants, base de données SQLite, cours privés, conversations
sauvegardées, historique des examens et des flashcards, profil et explications adaptées au niveau.

ÉTAPE 1 — Base de données […]
ÉTAPE 2 — Inscription et connexion
- Backend : POST /api/auth/register (email, mot de passe 8 à 72 caractères, niveau), POST /api/auth/login
  (renvoie {access_token, user}), GET /api/me, PATCH /api/me (changer de niveau). Dépendance get_current_user :
  401 si le jeton est absent, invalide ou expiré. Email déjà utilisé → 409. […]
ÉTAPE 3 — Cours privés
- Import : ajoute user_id dans le payload de chaque point Qdrant et une ligne dans la table Course.
- Toutes les lectures filtrent par user_id : get_course_chunks(course, user_id), recherche du tuteur, liste des
  cours (depuis la table Course), suppression (Qdrant + table Course). Crée un index de payload Qdrant sur user_id.
- Protège toutes les routes existantes […] Un étudiant ne peut ni voir, ni interroger, ni supprimer le cours d'un
  autre (404). […]
- Correction du découpage dans ingest.py : un dernier morceau de page trop court (moins de MIN_CHUNK_CHARS) est
  rattaché au morceau précédent au lieu d'être enregistré seul (bug actuel : des passages comme « ingle one. »).
ÉTAPE 4 — Conversations du tuteur […]
- Mémoire : les 3 derniers échanges de la conversation sont ajoutés au prompt pour comprendre les questions de
  suivi (« et pour les CNN ? »). Ils passent aussi par mask_pii. La recherche Qdrant se fait sur la question
  reformulée avec ce contexte, ou sur la question seule si elle est complète. […]
```

**Technique** : contexte de non-régression (liste de ce qui doit continuer à marcher), règles de sécurité
(PII, secrets), étapes ordonnées avec **tests à la fin de chaque étape**, contrat d'API complet (routes,
codes 401 / 404 / 409), bug connu intégré à l'étape concernée.

**Itérations et corrections** : une seule demande pour les 7 étapes ; 46 exécutions de tests ou builds, dont
9 en échec corrigées en cours de route ; essai réel à chaque étape avec un utilisateur jetable et une base
temporaire ; résultat : 45 tests backend et 106 tests frontend.

### 2.3 Autres prompts du module

**Fusion « Assistant » (14/10)** — demande de correction de bugs vus en test réel, chacun avec le comportement
attendu :

```text
2. Bugs vus en test réel :
   a. Le cours sélectionné dans la page doit être celui envoyé à l'agent et affiché dans le message
      (« Toi · <cours> ») ; un cours choisi par le LLM ne remplace jamais le cours sélectionné.
   b. « Résume les idées principales de ce cours » (et les formulations proches) doit être routé vers
      summarize, pas vers ask_course : ajoute ces cas au jeu agent_requests.json et vérifie le routage.
   c. Une réponse NOT_FOUND (« Hors du cours ») ne doit afficher aucun contenu supplémentaire ni sources.
   d. Les boutons rapides ne doivent jamais recouvrir les messages […]
3. Tests : mets à jour les specs […], ajoute des tests pour les bugs a, c et d, relance agent_eval avec le vrai
   modèle (taux de bon outil), puis tous les tests et le build.
```

Résultat : 4 bugs corrigés et testés, `taux_bon_outil` 100 % sur 26 demandes. Pour le bug b, Claude Code n'a
pas pu le reproduire et a ajouté un garde-fou (`COURSE_SUMMARY`) plutôt que de déclarer le problème inexistant.

**Déploiement (14/10)** — demande avec une part de recherche :

```text
1. Profils LLM sans toucher au code métier : […] Vérifie dans la documentation actuelle de Groq quels modèles
   sont disponibles, lesquels gèrent le tool calling (pour l'agent) et les sorties JSON structurées
   (json_schema) ; choisis un modèle par défaut adapté (bon en français). Si json_schema n'est pas pris en
   charge par le modèle choisi, ajoute un repli automatique sur response_format json_object + validation
   Pydantic […]. Gère les limites de débit de l'offre gratuite (erreur 429 → attente et nouvel essai, avec un
   message clair si la limite persiste).
2. Docker en local : […] Vérifie que « docker compose up --build » démarre tout et que l'application
   fonctionne sur http://localhost:8080 avec Groq.
3. Benchmark Groq : relance le benchmark […] sans écraser les runs qwen […]
```

Itérations : choix du modèle par appels réels (gpt-oss rejetés : `json_validate_failed` ; Llama : 404 avec la
clé), deux correctifs pendant le build (`requirements.txt`, URL relative de l'API), test de bout en bout dans
Docker.

**Barre latérale (19/10)** — trois demandes successives : refonte, puis repli « comme claude.ai », puis, après
« ok mais maintenant elle est très chargée », une version minimaliste avec une contrainte de non-régression
explicite (« NE MODIFIE PAS le mécanisme d'ouverture/fermeture »). Exemple d'itération guidée par le retour
visuel de l'utilisateur.

**Optimisation des performances (18/10)** — prompt qui donne d'abord les mesures (examen 102 s, 54 appels,
rejets par cause) et impose une analyse avant toute modification (« donne-moi la liste des appels LLM
séquentiels avec leur coût, AVANT de modifier quoi que ce soit »). Ce travail (vérification groupée, cache des
concepts, streaming SSE, correctif IPv6) n'est **pas dans le code livré** : il est présenté dans le rapport comme
travaux expérimentaux (« Perspectives »).

### 2.4 Jetons du module

M1 seul : 13 demandes, 579 appels, 822 281 jetons de sortie, 176 298 659 jetons lus en cache, 221,9 min
actives, 19 972 lignes écrites ; plus la demande partagée avec M5 (§6) et les travaux expérimentaux (91 appels,
133 335 jetons de sortie).

---

## 3. Module 2 — Fine-tuning LoRA/QLoRA

### 3.1 Demandes

| Date | Session | Demande | Appels API | Sortie | Cache lu | Durée active |
|---|---|---|---|---|---|---|
| 14/10 12:42 | `224dfdba` | Jeu de données, notebook Colab, évaluation base / affiné, fournisseur `hf-local` | 28 | 54 476 | 2 754 899 | 13,4 min |
| 14/10 16:09 | `20d36a24` | Résultats dans la documentation + corrections du notebook | 19 | 18 447 | 4 520 568 | 3,7 min |

### 3.2 Prompt principal (14/10, 4 037 caractères)

```text
Contexte : projet AI Study Assistant (FastAPI + Angular). Tout le projet est terminé et testé.
N'exécute aucune commande git. Ne modifie pas la logique de l'application.

Objectif : expérience de fine-tuning LoRA d'un modèle Hugging Face pour le style de tuteur adapté au
niveau de l'étudiant (cahier des charges : « fine-tuning a Hugging Face model to produce your desired
tutoring style »), dans backend/app/phase4_finetuning (le dossier peut déjà exister : réutilise-le).

Contraintes matérielles : GPU local NVIDIA RTX 4050 6 Go (insuffisant pour entraîner) → l'entraînement
se fait sur Google Colab (GPU T4 gratuit, 15 Go). Le jeu de données et l'évaluation se font en local.

1. dataset.py — python -m app.phase4_finetuning.dataset <email> [--n 300]
   - À partir des cours de l'utilisateur dans Qdrant (passages de 200 caractères ou plus), génère des
     questions variées (définition, rôle, comparaison, exemple, « pourquoi ») avec le LLM configuré.
   - Pour chaque question, les 3 niveaux (débutant, intermédiaire, avancé) : la « réponse idéale » est produite
     par le LLM configuré (modèle enseignant) avec la consigne de niveau du tuteur et le passage, puis filtrée
     (français, longueur adaptée au niveau, référence [p.X] valide, pas de « probablement », pas d'anglais).
   - Aucune donnée d'étudiant, mask_pii sur tout.
   - Export JSONL au format chat (system / user avec le niveau + le passage + la question / assistant),
     découpé en train (90 %) et test (10 %) […]
2. notebooks/finetune_lora.ipynb pour Google Colab, cellule par cellule avec des explications en français :
   […] Qwen/Qwen2.5-1.5B-Instruct en 4 bits (QLoRA), LoRA r=16, alpha=32, dropout 0.05 sur les couches
   d'attention et MLP, SFTTrainer, 2-3 époques, hyperparamètres adaptés à 15 Go de VRAM ;
   - courbe de perte, sauvegarde de l'adaptateur ;
   - génération des réponses du modèle de BASE et du modèle AFFINÉ sur tout le jeu de test (mêmes prompts,
     même température) […]
   - publication de l'adaptateur sur le Hugging Face Hub (<HF_USERNAME>/study-tutor-qwen2.5-1.5b-lora) avec
     une model card en français (objectif, données, hyperparamètres, limites).
3. evaluate.py — […] Juge LLM (le LLM configuré, qwen2.5:7b) avec une grille de 1 à 5 : respect du niveau
   demandé, fidélité au passage du cours, clarté ; plus des mesures automatiques : longueur, présence de [p.X],
   français. […]
4. Optionnel et désactivé par défaut : fournisseur LLM_PROVIDER=hf-local […]
6. Tests pytest (filtres du jeu de données, format JSONL, calcul des scores avec un juge simulé), puis tous
   les tests existants. Rapport en français avec les commandes exactes.
```

**Technique** : contrainte matérielle explicite (6 Go en local, T4 sur Colab) qui fixe le partage du travail ;
hyperparamètres LoRA imposés ; protocole de comparaison équitable (mêmes prompts, même température) ; option
désactivée par défaut pour ne pas changer l'application.

### 3.3 Itérations et corrections

- **Juge LLM** : pendant l'essai réel, le premier juge notait presque tout 1 ou 2 parce qu'il recopiait
  l'exemple de format `{"niveau": 1, …}`. Claude Code a retiré l'exemple et demandé une justification avant
  les notes (bug 15 de [claude-code-usage.md](claude-code-usage.md)).
- **Découpage train / test** : choix de Claude Code, signalé dans son rapport, de découper **par question**
  (les 3 niveaux d'une question dans le même fichier), pour qu'aucune question de test ne soit vue à
  l'entraînement.
- **Notebook (2e demande)** : « Corrige aussi le notebook (bfloat16 → float16 sur T4, poids LoRA en float32,
  dossier data/, REPO_ID lu depuis les secrets Colab) ». Claude Code a constaté que float16 était déjà utilisé,
  ajouté `bf16=False` et la conversion des poids LoRA en float32 (erreur « Attempting to unscale FP16
  gradients »), et corrigé l'envoi des données qui créait `train (1).jsonl`.
- **Lecture des résultats** : Claude Code a précisé que la perte de 0,710 est une moyenne sur l'entraînement
  (le dernier point de la courbe est vers 0,57), et relevé la baisse de fidélité au niveau débutant
  (4,7 → 4,0).
- Écart : un `git diff --stat` lancé malgré la consigne, signalé dans le rapport.

### 3.4 Jetons du module

2 demandes, 47 appels, 72 923 jetons de sortie, 7 275 467 jetons lus en cache, 17,1 min actives, 1 889 lignes
écrites ; 5 exécutions de tests, 1 en échec corrigée. L'entraînement (Colab) et la génération du jeu de données
(qwen2.5:7b local) ne consomment pas de jetons Claude.

---

## 4. Module 3 — Générateur d'examens

Le **backend** du générateur (prompts, schémas Pydantic et leurs expressions régulières, vérification, PDF) a
été développé avant Claude Code, **avec Claude en mode conversation** (§8 ; jetons non mesurables). Les
demandes Claude Code ci-dessous portent sur le frontend et l'intégration. Bugs du backend corrigés pendant la
phase conversationnelle : caractères de contrôle JSON (C1), `NameError` après un collage partiel de
`schemas.py` (C2), lignes dupliquées dans `generator.py` (C3), questions ouvertes rejetées à tort par
`DOUBLE_QUESTION` (C4), caractères cyrilliques (C6). Les prompts du générateur lui-même sont dans
[prompts.md](prompts.md) §7.

### 4.1 Demandes

| Date | Session | Demande | Appels API | Sortie | Cache lu | Durée active |
|---|---|---|---|---|---|---|
| 11/10 22:41 / 22:46 | `5d902768` | Génération d'examen PDF depuis « Mes cours », en arrière-plan (proposition, puis validation) | 14 | 37 625 | 2 205 570 | 6,6 min |
| 12/10 00:03 / 00:06 | `5d902768` | Formats « Examen complet » / « QCM rapide », barème sur 20 | 15 | 18 780 | 2 962 558 | 3,9 min |
| 13/10 11:06 | `5d902768` | Plage de pages (testée, puis retirée volontairement) | 13 | 23 917 | 3 040 858 | 3,8 min |
| 13/10 11:54 | `5d902768` | Durées estimées mesurées, une seule fonction | 7 | 6 260 | 1 925 256 | 2,6 min |

### 4.2 Prompt principal (11/10, 5 246 caractères)

```text
Contexte
--------
Projet "AI Study Assistant" : backend FastAPI (backend/) et frontend Angular 22 (frontend/),
avec une architecture core/ features/ shared/, des signals, en mode zoneless.
Le backend expose déjà une nouvelle route, à NE PAS modifier :

POST /api/courses/{course}/exam
  body JSON : {"num_questions": 5 | 10 | 15 | 20, "difficulty": "facile" | "moyen" | "difficile",
               "include_answers": boolean}
  → 200 : fichier PDF (application/pdf)
          en-têtes exposés : Content-Disposition (nom du fichier), X-Questions-Generated (nombre)
  → 404 {"detail": "..."}  cours introuvable
  → 422 {"detail": "..."}  le modèle n'a produit aucune question valide
  → 503 {"detail": "..."}  LLM indisponible, timeout…
La génération prend de 30 s à 3 min (environ 10 s par question).

Objectif : ajouter la génération d'examen PDF depuis la liste "Mes cours", sans bloquer l'application.

Avant de coder
--------------
1. Lis core/services/tutor-api.service.ts, core/models, core/interceptors/error.interceptor.ts, […]
2. Lis backend/app/phase4_exam/routes.py et schemas.py pour confirmer le contrat de l'API.
3. Propose-moi en quelques lignes les fichiers que tu vas créer ou modifier, puis attends ma validation.

Scénario utilisateur à implémenter […]
5. Échec : notification d'erreur avec le message "detail" du backend.
   Attention : avec responseType 'blob', le corps d'erreur arrive lui aussi sous forme de Blob ;
   il faut le lire (blob.text() puis JSON.parse) pour récupérer "detail".
   Vérifie aussi que l'interceptor d'erreur gère ce cas sans casser le tuteur. […]
Validation
----------
1. `npx ng build` sans erreur ni warning ; `npx ng test --watch=false` passe.
2. Ajoute des tests unitaires pour : la lecture du nom de fichier depuis Content-Disposition,
   la lecture du "detail" dans un Blob d'erreur, et le calcul de la durée estimée.
3. Donne-moi la liste des fichiers modifiés et une checklist de test manuel : […]
```

**Technique** : contrat d'API complet avec codes d'erreur et durées ; **analyse puis validation avant le code** ;
piège technique signalé à l'avance (Blob d'erreur) ; tests unitaires nommés ; checklist manuelle demandée.

### 4.3 Itérations et corrections

- **Validation avec précisions (11/10 22:46)** : fermeture de la modale seulement si le clic commence ET finit
  sur le fond ; lecture asynchrone du Blob avec `from()` et `switchMap`, repli si le JSON est invalide ; mention
  « Le corrigé est généré par IA : relis-le avant de distribuer l'examen ».
- **Durées** : estimation corrigée deux fois à partir de mesures réelles (12/10, puis 13/10 11:54 avec les
  valeurs mesurées sur qwen2.5:7b).
- **Plage de pages (13/10 11:06)** : implémentée et testée (51 tests frontend), puis **retirée volontairement**
  par l'équipe. Sur des diapositives, une plage de quelques pages contient trop peu de passages utiles : l'examen
  complet sortait incomplet (barème sur 15 au lieu de 20). À la demande suivante, Claude Code a constaté le
  retrait (« le code de la plage n'existe plus nulle part ») et ne l'a pas réintroduite sans accord. Elle n'est
  pas dans le code livré.
- 7 exécutions de tests ou builds, 2 en échec corrigées.

### 4.4 Jetons du module

6 demandes, 49 appels, 86 582 jetons de sortie, 10 134 242 jetons lus en cache, 16,9 min actives, 1 807 lignes
écrites.

---

## 5. Module 4 — Flashcards et résumés

Le **backend** des flashcards (extraction de concepts, retrieve, carte, vérification, doublons) a été développé
avant Claude Code, **avec Claude en mode conversation** (§8 ; jetons non mesurables). Bugs corrigés pendant cette
phase : attribut `page` supprimé dans `Flashcard` (C5), réponses tronquées par `maxLength` (C7), doublons de
cartes (C8), juge trop strict (C9), fragments de chunks trop courts → `MIN_PASSAGE_CHARS` (C10). Le backend des
**résumés** (map-reduce, explication d'un thème, cache) a été généré par Claude Code dans la session `2ab3ba04`.

### 5.1 Demandes

| Date | Session | Demande | Appels API | Sortie | Cache lu | Durée active |
|---|---|---|---|---|---|---|
| 13/10 12:53 | `5d902768` | Fonctionnalité Flashcards (frontend : génération, révision, score) | 19 | 38 997 | 5 763 555 | 11,8 min |
| 13/10 13:07 | `5d902768` | Durées mesurées des flashcards | 4 | 2 667 | 1 331 703 | 0,7 min |
| 14/10 10:43 | `2ab3ba04` | Résumés de cours : map-reduce, thème, cache, page Résumés, benchmark | 26 | 56 390 | 12 113 735 | 17,9 min |

### 5.2 Prompt principal : résumés (14/10, 3 222 caractères)

```text
Contexte : projet AI Study Assistant (FastAPI + Angular). Comptes, cours privés (user_id dans Qdrant),
tuteur avec niveau de l'étudiant, examens, flashcards et MLflow sont terminés et testés. Ne casse rien,
n'exécute aucune commande git.

Objectif : résumés de cours (dossier backend/app/phase9_summaries), demandés par le cahier des charges
(« Explain chapter 3 »). Le tuteur RAG ne lit que 3 passages et ne peut pas résumer un cours entier :
le résumé doit lire TOUT le cours.

1. Deux modes :
   - Cours entier (map-reduce) : regroupe les passages du cours (get_course_chunks avec user_id, en ignorant
     ceux de moins de 60 caractères) en sections d'environ 6 passages consécutifs ; résume chaque section
     (un titre court + 3 à 5 puces, chaque puce avec sa référence [p.X]) ; puis rédige une vue d'ensemble
     de 4 à 6 phrases. Sortie structurée (Pydantic + json_schema) : {overview, sections:[{title, pages, bullets}]}.
   - Thème (« Explique-moi les CNN », « la partie sur les connecteurs ») : recherche sémantique (6 meilleurs
     passages du cours), puis une explication structurée avec références [p.X], adaptée au niveau de
     l'étudiant (même consigne de niveau que le tuteur). Si le thème n'est pas dans le cours, le dire
     clairement au lieu d'inventer.
   Toujours en français, uniquement à partir du cours, mask_pii sur tous les prompts. Validation : refus
   des puces vides, en anglais, sans référence de page ou avec une page absente des passages fournis
   (réessaie une fois en cas de rejet). LLMError → 503.
2. Cache : table Summary (user_id, course, mode, topic, content JSON, created_at). Le résumé du cours
   entier est réutilisé s'il existe ; option regenerate=true pour le refaire. […]
5. Ajoute le résumé au benchmark (--skip-summary) : 1 résumé du cours entier, avec la durée, le nombre
   de sections et le taux de puces avec une page valide.
6. Tests pytest (LLM simulé) et frontend, puis tous les tests existants. […]
```

**Technique** : justification par le cahier des charges et par une limite du RAG (3 passages) ; algorithme
imposé (map-reduce, tailles de section, nombre de puces) ; **règles de validation des sorties LLM** écrites dans
le prompt (page citée parmi les passages fournis, français, une nouvelle tentative) ; mesure intégrée au
benchmark dès la conception.

### 5.3 Prompt : flashcards (13/10, 2 482 caractères, extrait)

```text
Ajoute une fonctionnalité « Flashcards » au frontend Angular (même architecture core/features/shared,
standalone, signals, même design et thème sombre que le tuteur et l'examen).

API backend (déjà prête) :
POST /api/courses/{course}/flashcards  body {"count": 10 | 20 | 30}
→ 200 {"course": "...", "cards": [{"concept": "...", "front": "question ?", "back": "réponse", "page": 12}]}
Erreurs : 404 (cours introuvable), 422 {"detail": "..."}, 503 (LLM indisponible) → gérées par l'intercepteur
existant (toast). […] Le nombre de cartes reçues peut être inférieur au nombre demandé (petit cours) : afficher
le nombre réel. […]
4. Écran de révision, une carte à la fois : […] clic ou Espace : la carte se retourne (animation 3D en CSS,
   désactivée si prefers-reduced-motion) ; […] boutons « À revoir » (touche 1) et « Je savais » (touche 2) […]
7. Tests unitaires (service API, logique de révision : retournement, score, filtre « à revoir »,
   persistance localStorage), puis lance le build et les tests.
```

### 5.4 Itérations et corrections

- **Résumés, essai réel** (cours entier en 60 s, thème en 14 s, thème hors cours refusé en 1 s, deuxième
  demande servie par le cache en 0 s) : deux défauts trouvés et corrigés par Claude Code, une puce terminée par
  un `}` parasite et des titres de section répétés (les titres déjà utilisés sont maintenant passés au prompt).
- **Flashcards** : génération réelle de 10 cartes mesurée à 317 s alors que l'interface annonçait 2 min ;
  signalé par Claude Code, puis durées corrigées par la demande du 13/10 13:07.
- 15 exécutions de tests ou builds, 3 en échec corrigées.

### 5.5 Jetons du module

3 demandes, 49 appels, 98 054 jetons de sortie, 19 208 993 jetons lus en cache, 30,4 min actives, 3 404 lignes
écrites.

---

## 6. Module 5 — Agent LangGraph, MLflow, tests et CI/CD

### 6.1 Demandes

| Date | Session | Demande | Appels API | Sortie | Cache lu | Durée active |
|---|---|---|---|---|---|---|
| 14/10 01:05 | `2ab3ba04` | Évaluation avec MLflow : collecteur, expériences, benchmark hors ligne, `/api/stats` | 30 | 55 869 | 11 577 330 | 20,0 min |
| 14/10 01:54 / 01:56 | `2ab3ba04` | Métrique `refus_correct`, `reponse_trouvee` limitée aux questions du cours | 6 | 5 628 | 2 587 521 | 1,8 min |
| 14/10 11:18 | `01cad59c` | Phase « AI Study Companion » : agent LangGraph + page (partagée avec M1) | 94 | 174 341 | 21 994 422 | 39,9 min |

Le workflow d'intégration continue (`.github/workflows/ci.yml`) est produit dans la session de rédaction des
livrables (`fccd8465`), phase « qualité et sécurité » ; voir `docs/qualite-ia.md`.

### 6.2 Prompt principal : agent LangGraph (14/10, 4 791 caractères)

```text
Contexte : projet AI Study Assistant (FastAPI + Angular). Fonctions existantes à réutiliser SANS les
réécrire : tuteur RAG avec conversations (phase3_rag), résumés (phase9_summaries), générateur d'examen
(phase4_exam, format qcm), flashcards (phase7_flashcards), profil et points faibles (phase8_personal),
MLflow (phase5_evaluation). N'exécute aucune commande git. Ne casse aucune page existante.

Objectif : phase « AI Study Companion » du cahier des charges — un agent LangGraph et une page unique
(dossier backend/app/phase6_agent).

1. Agent LangGraph (langgraph + langchain-openai ; LLM via LLM_BASE_URL / LLM_MODEL / LLM_API_KEY,
   compatible OpenAI : Ollama qwen2.5:7b aujourd'hui, Groq plus tard sans changer le code).
   Outils (chacun appelle la fonction existante avec le user_id de l'étudiant connecté) :
   - ask_course(question, course?) : réponse RAG avec sources [p.X] ;
   - summarize(course, topic?) : résumé du cours entier (avec le cache existant) ou explication d'un thème ;
   - generate_quiz(course, count=5|10, difficulty) : QCM renvoyé en JSON (pas de PDF) […] ;
   - generate_flashcards(course, count=10) : paquet enregistré, renvoie deck_id ;
   - get_progress() : niveau, statistiques, points faibles.
   Graphe : choix de l'outil par tool calling → exécution → réponse finale courte en français, adaptée au
   niveau. Si le modèle n'appelle aucun outil ou appelle un outil invalide : repli sur une classification
   d'intention en sortie structurée (json_schema), puis exécution de l'outil choisi. Maximum 3 appels d'outil
   par message. Pour une simple salutation ou une question sur l'application, réponse directe sans outil.
   Aucune donnée personnelle envoyée au LLM (mask_pii, jamais d'email ni de nom). […]
4. […] Les outils longs (quiz, flashcards, résumé) peuvent prendre 1 à 3 minutes : gère-les en tâche de fond
   avec un état consultable (GET /api/companion/jobs/{id}) pour éviter les timeouts HTTP.
5. MLflow :
   - expérience "agent" : outil choisi, repli utilisé ou non, durée, nombre d'appels d'outil, succès ;
   - tracing MLflow de l'agent LangGraph […]. Aucune donnée personnelle dans les traces […]
   - évaluation de l'agent : fichier JSON de 20 demandes variées avec l'outil attendu (ex. « Fais-moi un quiz
     sur les CNN » → generate_quiz, « Bonjour » → aucun outil) et script
     python -m app.phase5_evaluation.agent_eval <email> qui mesure le taux de bon outil choisi (sans exécuter
     les outils longs : arrêt après le choix) et l'enregistre dans MLflow. […]
7. Tests : pytest (agent avec LLM simulé, routage, repli, quiz, tâches de fond) et frontend, puis tous les
   tests existants. Rapport en français : fichiers, commandes, checklist manuelle, choix faits sans moi,
   et le taux de bon outil obtenu avec le vrai modèle.
```

**Technique** : réutilisation imposée des fonctions existantes (pas de réécriture) ; architecture de l'agent
décrite (outils, graphe, repli, limite de 3 outils) ; portabilité du fournisseur (Ollama puis Groq) ;
confidentialité étendue aux traces ; **évaluation demandée avec le vrai modèle** et un jeu de test étiqueté.

### 6.3 Prompt : évaluation avec MLflow (14/10, 5 362 caractères, extrait)

```text
Règles :
- N'exécute AUCUNE commande git.
- Ne change pas le comportement ni la logique des générateurs (examen, flashcards, tuteur) : ajoute seulement
  de la mesure. Les résultats générés doivent rester identiques.
- Aucune donnée personnelle dans MLflow : jamais d'email, de nom, ni de texte de question de l'étudiant.
  Seulement des nombres, des réglages et des noms de cours.
- Si MLflow échoue ou est désactivé, l'application fonctionne normalement (aucune exception remontée). […]
2. Collecteur de statistiques
   - Un petit objet (par exemple GenerationStats) avec des compteurs : appels LLM, rejets par cause
     (validation Pydantic, auto-vérification, doublons), éléments générés/demandés, par type si utile.
   - Il est passé en paramètre optionnel aux générateurs (None par défaut) : quand il est absent, le code
     se comporte exactement comme avant. […]
4. Benchmark hors ligne
   - Commande : python -m app.phase5_evaluation.benchmark <email> <cours> [--n 3] […]
   - Évaluation du tuteur : jeu de questions dans app/phase5_evaluation/datasets/<cours>.json
     (liste de {"question": ..., "expected_page": ...}). […] Mesure le hit rate @3 (la page attendue est parmi
     les 3 sources renvoyées) et le taux de réponses trouvées. […]
6. Tests
   - pytest : le collecteur compte correctement, log_run ne plante pas quand MLflow est désactivé ou
     indisponible, un générateur sans collecteur fonctionne comme avant, /api/stats répond.
```

Exemple de commande du rapport : `python -m app.phase5_evaluation.benchmark etudiant@example.com Chapter1_Part_1 --n 3`.

### 6.4 Itérations et corrections

- **MLflow** : MLflow 3 refuse `file:./mlruns` ; Claude Code a choisi `sqlite:///mlruns/mlflow.db` et l'a
  signalé comme écart. Un test vérifie qu'un examen et un paquet générés avec ou sans collecteur sont identiques.
- **Métriques (2 demandes courtes)** : ajout de `refus_correct` pour les questions hors cours ; Claude Code a
  ensuite signalé que `reponse_trouvee` restait faussée par ces questions, corrigé à la demande suivante.
- **Agent, essai réel** : trois défauts trouvés et corrigés (prénom répété dans les traces, cours inventé par la
  classification, questions du quiz recopiées dans la réponse finale). `taux_bon_outil` 100 % (20/20), repli
  20 % (les 4 salutations).
- 24 exécutions de tests ou builds sur le module (dont l'agent), 3 en échec corrigées.

### 6.5 Jetons du module

M5 seul : 3 demandes, 36 appels, 61 497 jetons de sortie, 14 164 851 jetons lus en cache, 21,8 min, 854 lignes
écrites. Demande partagée M1 + M5 (agent et page Study Companion) : 94 appels, 174 341 jetons de sortie,
21 994 422 jetons lus en cache, 39,9 min, 4 295 lignes écrites.

---

## 7. Demandes courtes de suivi

Les 10 demandes courtes montrent comment l'équipe corrige le tir sans réécrire la demande :

| Type | Exemple (extrait) | Effet |
|---|---|---|
| Validation avec précisions | « Oui, c'est validé, garde l'accent vert. Implémente tout. Trois précisions : […] appelle preventDefault() […] Utilise marked en mode synchrone […] » | le plan proposé est accepté, avec des détails techniques ajoutés |
| Décision sur une question de Claude | « Oui, limite reponse_trouvee aux seules questions du cours (comme hit_3), mets à jour les tests » | répond à une alerte du rapport précédent |
| Mise à jour par des mesures | « mets à jour FLASHCARD_MINUTES avec les durées mesurées (Ollama qwen2.5:7b) : 10 cartes → environ 3 min […] » | remplace une estimation par une mesure |
| Retour visuel | « ok mais maintenant elle est tres charger le side barre » | suivi d'une nouvelle demande longue avec une contrainte de non-régression |

---

## 8. Phase conversationnelle (claude.ai)

Le cœur du backend (ingestion et RAG, générateur d'examens, schémas Pydantic et leurs expressions régulières,
flashcards) a été écrit avec Claude en mode conversation, avant Claude Code. Aucune transcription n'est
conservée dans le projet : les prompts exacts ne peuvent pas être recopiés ici, et les **jetons de cette phase ne
sont pas mesurables**. La méthode est décrite dans [claude-code-usage.md](claude-code-usage.md) §7.

### 8.1 Type d'interactions

| Interaction | Contenu envoyé par l'étudiant | Réponse de l'assistant |
|---|---|---|
| Demande de fonctionnalité | objectif, contraintes (français, sortie JSON, pages citées), extrait du code existant | fichier complet à créer |
| Modification | le fichier ou la fonction concernée | bloc « ancien » à remplacer et bloc « nouveau » |
| Débogage | traceback, sortie de pytest ou réponse brute du LLM | diagnostic et correctif |
| Réglage des validateurs | exemples de sorties du LLM acceptées ou rejetées à tort | nouvelle expression régulière ou nouvelle règle Pydantic, avec un test |

### 8.2 Ce que cette phase a appris pour la suite

- **Fichiers complets plutôt que fragments** quand un module change beaucoup : les collages partiels ont causé
  un `NameError` (C2) et des lignes dupliquées (C3).
- **Renvoyer la sortie exacte** (traceback, JSON brut) : c'est elle qui a permis de diagnostiquer les caractères
  de contrôle (C1), les caractères cyrilliques (C6) et les réponses tronquées par `maxLength` (C7).
- **Écrire chaque règle de validation avec son contre-exemple** : `DOUBLE_QUESTION` rejetait à tort les
  questions ouvertes (C4) ; le juge des cartes était trop strict (C9).

Ces leçons se retrouvent dans le gabarit des demandes Claude Code (§1.2) : critères de tests, contrats exacts,
interdictions de modifier les validateurs sans test.

Liste des bugs C1 à C10 : [claude-code-usage.md](claude-code-usage.md) §7.3.
