# Évaluation

Résultats relevés le **14 octobre 2026** dans les fichiers CSV de `backend/app/phase5_evaluation/results/` et
dans la base MLflow `backend/mlruns/mlflow.db`. Modèle : **qwen2.5:7b** (Ollama), embeddings
**multilingual-e5-small**, GPU RTX 4050 6 Go.

## 1. Méthode

### 1.1 Mesure intégrée à l'application (MLflow)

Chaque génération (examen, flashcards, question au tuteur, résumé, message à l'agent) enregistre **un run
MLflow** dans l'expérience correspondante (`exam`, `flashcards`, `tutor`, `summary`, `agent`). Un
collecteur (`GenerationStats`) compte pendant la génération : appels au LLM, rejets par cause (validation
Pydantic, auto-vérification, doublon de sens), éléments demandés et obtenus, durée.

- **Aucune donnée personnelle** dans les runs : seulement des nombres, des réglages, le nom du cours, le
  niveau et le tag `source` (`app`, `agent`, `benchmark`, `evaluation`). Jamais d'email, de nom ni de texte
  de question.
- Enregistrement dans un thread séparé : la réponse à l'étudiant n'attend pas MLflow ; une panne de MLflow
  ne casse pas la génération.
- `GET /api/stats` renvoie les moyennes de tous les runs.

### 1.2 Benchmark hors ligne

```
python -m app.phase5_evaluation.benchmark <email> <cours> [--n 3]
```

Sur un cours du compte `<email>` : N examens complets (difficulté moyenne), N paquets de 10 flashcards, le
jeu de questions du tuteur et un résumé du cours entier (sans cache). Résultat : runs MLflow (tag
`source=benchmark`) et CSV récapitulatif (moyenne, écart-type, N par métrique).

Cours de test : **Chapter1_Part_1** (cours d'architecture logicielle, en anglais ; 26 passages utiles,
21 passages de 250 caractères ou plus pour les examens).

### 1.3 Évaluation du choix d'outil de l'agent

```
python -m app.phase5_evaluation.agent_eval <email>
```

Pour chaque demande du jeu `datasets/agent_requests.json` (message + outil attendu ; `null` = réponse
directe sans outil), l'agent choisit son outil (tool calling, puis repli par classification si besoin) et
s'arrête là (`dry_run` : les outils longs ne sont pas exécutés). Résultat : taux de bon outil global et par
outil, taux de repli, CSV et expérience MLflow `agent_eval`.

### 1.4 Définition des métriques

| Métrique | Définition |
|---|---|
| `taux_reussite` | éléments obtenus / éléments tentés (pour un examen, le complément Vrai/Faux compte dans les tentatives) |
| `total_points` | points de l'examen généré (objectif : 20) |
| `rendement_appels` | éléments obtenus / appels au LLM (vérifications comprises) |
| `taux_rejet_validation` / `_verification` / `_doublon` | rejets de chaque cause / appels de génération |
| `hit_3` | la page attendue fait partie des sources renvoyées par le tuteur |
| `hit_3_recherche` | la page attendue fait partie des 3 passages renvoyés par Qdrant (sans le LLM) |
| `reponse_trouvee` | le tuteur a répondu (pas la phrase de refus), sur les questions du cours |
| `refus_correct` | le tuteur a répondu « Cette information n'est pas présente dans le cours. » à une question hors cours |
| `taux_puces_page_valide` | puces proposées dont toutes les pages `[p.X]` font partie des passages fournis |
| `taux_bon_outil` | demandes pour lesquelles l'agent choisit l'outil attendu |
| `taux_repli` | demandes passées par la classification de repli |

## 2. Résultats

### 2.1 Examens complets (3 runs du benchmark)

Format complet, difficulté moyenne : 8 QCM, 4 Vrai/Faux, 2 questions courtes, 1 question de réflexion
(15 questions, 20 points).

| Métrique | Run 1 | Run 2 | Run 3 | Moyenne (écart-type) |
|---|---|---|---|---|
| Points | 20/20 | 20/20 | 20/20 | **20/20** |
| Questions obtenues | 15/15 | 18 (question de réflexion ratée, remplacée par 4 V/F) | 15/15 | — |
| `taux_reussite` | 1.000 | 0.947 | 1.000 | **0.982** (0.031) |
| Appels au LLM | 40 | 57 | 49 | 48.7 (8.5) |
| Durée | 150 s | 176 s | 149 s | **158 s** (15) |
| `rendement_appels` | 0.375 | 0.316 | 0.306 | 0.332 (0.037) |
| Rejets de validation | 26 % | 16 % | 12 % | 17.9 % (7.5) |
| Rejets par vérification | 0 % | 16 % | 0 % | 5.4 % (9.3) |
| Rejets pour doublon | 9 % | 10 % | 31 % | 16.4 % (12.5) |

Quiz QCM lancé par l'agent (5 questions) : 5/5 en 61 s, 13 appels au LLM.

### 2.2 Flashcards (3 runs du benchmark, 10 cartes)

| Métrique | Run 1 | Run 2 | Run 3 | Moyenne (écart-type) |
|---|---|---|---|---|
| Cartes obtenues | 10/10 | 10/10 | 10/10 | **10/10** |
| Concepts trouvés / retenus | 27 / 24 | 27 / 22 | 27 / 23 | 27 / 23 |
| Appels au LLM | 39 | 42 | 54 | 45 (7.9) |
| Durée | 115 s | 116 s | 155 s | **129 s** (23) |
| `rendement_appels` | 0.256 | 0.238 | 0.185 | 0.226 (0.037) |
| Rejets de validation | 24 % | 26 % | 39 % | 29.7 % (8.4) |
| Rejets par vérification | 6 % | 11 % | 21 % | 12.6 % (8.0) |
| Rejets pour doublon | 12 % | 11 % | 4 % | 8.6 % (4.4) |

Paquet de 20 cartes lancé par l'agent : **14/20** (70 %) en 159 s. Les concepts ont manqué avant la fin
(rejets de validation 27 %, doublons 19 %).

### 2.3 Résumés

| Run | Mode | Sections | Puces gardées | Puces avec page valide (proposées) | Appels | Durée |
|---|---|---|---|---|---|---|
| Benchmark, Chapter1_Part_1 | cours entier | 5 | 22 | **100 %** (22/22) | 6 | 42 s |
| Application, Chapter1_Part_1 | cours entier | 5 | 22 | 100 % (22/22) | 6 | 55 s |
| Application, Chapter1_Part_1 | thème, niveau avancé | 2 | 6 | 100 % (6/6) | 1 | 32 s |
| Agent, CNN_intro (43 passages) | cours entier | 7 | 30 | 67 % (30/45) | 11 | 79 s |

Sur CNN_intro, 3 sorties sur 11 ont été rejetées (pages citées hors des passages fournis) puis regénérées :
**toutes les puces affichées** ont une page valide, puisque la validation refuse les autres.

### 2.4 Tuteur RAG

Jeu `datasets/Chapter1_Part_1.json` : 12 questions du cours (page attendue connue, dont 2 formulées
familièrement : « c'est quoi la différence… ») et 2 questions hors cours.

| Run | Questions | `hit_3` | `hit_3_recherche` | Réponse trouvée | Refus hors cours | Durée moyenne |
|---|---|---|---|---|---|---|
| 1 | 10 du cours | 100 % | 100 % | 100 % | — | 6.5 s |
| 2 | 12 du cours | 100 % | 100 % | 100 % | — | 5.9 s |
| 3 (jeu complet) | 12 du cours + 2 hors cours | **100 %** (12/12) | 100 % | **100 %** | **100 %** (2/2) | 6.1 s (σ 5.2) |

Run 3 : meilleur score de similarité moyen 0.83 ; 2.6 passages gardés en moyenne après la marge de 0.03.

### 2.5 Agent : choix de l'outil

| Run | Demandes | `taux_bon_outil` | `taux_repli` | Durée moyenne du choix |
|---|---|---|---|---|
| 1 | 20 | **100 %** | 20 % (4/20) | 2.0 s |
| 2 | 26 (6 formulations de résumé ajoutées) | **100 %** (26/26) | 15 % (4/26) | 1.8 s |

Détail du run 2 : `aucun` 4/4, `ask_course` 4/4, `summarize` 9/9, `generate_quiz` 3/3,
`generate_flashcards` 3/3, `get_progress` 3/3. Les 4 replis sont les 4 salutations ou questions sur
l'application : le modèle répond sans outil, la classification confirme « aucun ».

Le run 2 a été fait après l'ajout du garde-fou « résumé du cours entier » : avant, des demandes comme
« Résume les idées principales de ce cours » partaient vers `ask_course`.

Messages réels traités par l'agent dans l'application : 8 runs, 8 succès, aucun repli (outils
`summarize`, `get_progress`, `generate_quiz`, `generate_flashcards`, `ask_course`).

### 2.6 Fine-tuning LoRA du style du tuteur (phase 4 bis)

Sources : `backend/app/phase4_finetuning/results/finetuning_2026-10-14_1704.csv` (+ `_details.jsonl`), runs
MLflow `base` et `affine` de l'expérience `finetuning`, fichiers `data/progress.json`, `train.jsonl`,
`test.jsonl`. Méthode détaillée : `backend/app/phase4_finetuning/README.md`.

Modèle publié : **[Alinajjaa/study-tutor-qwen2.5-1.5b-lora](https://huggingface.co/Alinajjaa/study-tutor-qwen2.5-1.5b-lora)**
(adaptateur LoRA pour Qwen/Qwen2.5-1.5B-Instruct).

#### Jeu de données

Questions et réponses « idéales » générées par qwen2.5:7b (modèle enseignant) à partir des passages des
cours, pour les 3 niveaux, puis filtrées automatiquement.

| Élément | Valeur |
|---|---|
| Questions générées | 124 (5 inutilisables) |
| Réponses produites (question × niveau) | 372 |
| Réponses gardées | **300 (81 %)** |
| Découpage par question | **train 269** (103 questions) / **test 31** (11 questions jamais vues à l'entraînement) |
| Train par niveau | débutant 89, intermédiaire 85, avancé 95 |
| Test par niveau | débutant 10, intermédiaire 11, avancé 10 |
| Train par type | pourquoi 63, définition 61, rôle 60, comparaison 50, exemple 35 |

Réponses rejetées (72) :

| Cause | Rejets | Signification |
|---|---|---|
| `incertitude` | 33 | « probablement », « peut-être »… : réponse devinée |
| `hors_cours` | 14 | l'enseignant répond « pas présente dans le cours » |
| `longueur` | 14 | hors des bornes du niveau (débutant 60 à 260 mots, intermédiaire 35 à 200, avancé 20 à 170) |
| `reference` | 9 | aucune référence `[p.X]` ou mauvaise page |
| `anglais` | 2 | texte resté en anglais |

#### Entraînement (Google Colab, GPU T4)

| Hyperparamètre | Valeur |
|---|---|
| Méthode | QLoRA : modèle de base en 4 bits nf4 (double quantification), calcul en float16, poids LoRA en float32 |
| LoRA | `r=16`, `alpha=32`, `dropout=0.05`, sur `q/k/v/o_proj` et `gate/up/down_proj` |
| Époques | 3 (51 étapes) |
| Lot effectif | 16 (4 × 4 accumulations) |
| Taux d'apprentissage | 2e-4, décroissance cosinus, 5 % de préchauffage |
| Longueur maximale | 1 024 jetons |
| Optimiseur | `paged_adamw_8bit`, `gradient_checkpointing` |
| Perte | calculée sur la réponse du tuteur seulement (format prompt / completion) |

**Perte finale** : entraînement **0,710**, test **0,827**.

![Courbe de perte du fine-tuning](images/loss_curve.png)

Lecture de la courbe : la perte d'entraînement passe de 0,96 à environ 0,57 (dernier point) ; 0,710 est la
**moyenne sur tout l'entraînement** (`training_loss` du Trainer). La perte de test baisse de 0,839 à 0,827
puis se stabilise à la 3e époque : pas de surapprentissage marqué, mais une 4e époque n'apporterait
probablement rien.

#### Comparaison base / affiné

Même modèle 4 bits, adaptateur désactivé pour la base ; mêmes 31 prompts de test, température 0.3, même
graine. Juge : qwen2.5:7b (température 0), qui ne sait pas quel modèle a écrit la réponse ; 0 échec du juge.

| Métrique | Base | Affiné | Écart |
|---|---|---|---|
| **Citations `[p.X]` valides** | **3 %** (1/31) | **97 %** (30/31) | **+94 pts** |
| Réponses en français | 100 % | 100 % | 0 |
| Longueur adaptée au niveau | 84 % | 90 % | +6 pts |
| Mots — débutant | 98 | 126 | +28 |
| Mots — intermédiaire | 110 | 94 | −16 |
| Mots — avancé | 107 | 84 | −23 |
| Juge : respect du niveau | 3,52 | 3,74 | +0,23 |
| — débutant | 3,40 | 3,90 | +0,50 |
| — intermédiaire | 3,73 | 3,91 | +0,18 |
| — avancé | 3,40 | 3,40 | **0** |
| Juge : fidélité au cours | 4,26 | 4,29 | +0,03 |
| Juge : clarté | 4,19 | 4,35 | +0,16 |
| Juge : moyenne | 3,99 | 4,13 | +0,14 |

À retenir :

- **Le format est appris** : le modèle de base ne cite presque jamais la page (3 %), le modèle affiné le
  fait presque toujours (97 %).
- **La longueur suit enfin le niveau** : la base écrit environ 100 mots quel que soit le niveau ; l'affiné
  écrit plus pour un débutant (126) et moins pour un avancé (84), comme les réponses de l'enseignant.
- **Notes du juge** : gain net au niveau débutant (+0,5), faible ailleurs, **aucun gain au niveau avancé**.
  Réponse par réponse, l'affiné a une meilleure moyenne dans 14 cas sur 31, une moins bonne dans 10, égale
  dans 7.
- **Fidélité au niveau débutant en baisse** (4,7 → 4,0) : en ajoutant analogies et exemples, l'affiné
  s'éloigne parfois du passage. La fidélité moyenne reste stable (4,26 → 4,29) grâce aux niveaux
  intermédiaire (4,27 → 4,73) et avancé (3,8 → 4,1).

### 2.7 Tests automatisés

- Backend : 128 tests `pytest` (LLM simulé, Qdrant en mémoire, base SQLite et MLflow temporaires).
- Frontend : 26 fichiers de tests (vitest).

Ils vérifient le comportement du code (validateurs, routes, droits d'accès, confidentialité des traces),
pas la qualité des réponses du modèle.

## 3. Limites

- **Jeux de test petits** : 14 questions pour le tuteur, 26 demandes pour l'agent, 3 examens et 3 paquets,
  sur **un seul cours** (Chapter1_Part_1) pour le benchmark. Un score de 100 % sur 12 questions ne prouve
  pas que le tuteur trouve toujours la bonne page ; les écarts-types sont calculés sur 3 runs seulement.
- **Jeux de test en partie écrits automatiquement** : une partie des questions et des demandes a été
  rédigée avec l'aide d'un LLM. Elles peuvent être plus proches du vocabulaire du cours que de vraies
  questions d'étudiants.
- **Questions hors cours très éloignées** (Docker, Coupe du monde) : le refus est facile. Une question
  proche du domaine mais absente du cours serait un test plus dur.
- **Pas de relecture humaine systématique** : la justesse des questions d'examen et des cartes est
  contrôlée par le même modèle (auto-vérification), qui peut se tromper de la même façon deux fois. Les
  métriques mesurent le respect des formats et des pages, pas la qualité pédagogique.
- **`hit_3` mesure la page, pas la réponse** : une réponse peut citer la bonne page et mal la résumer.
- **Agent évalué en `dry_run`** : seul le choix de l'outil est mesuré, pas la qualité du résultat ni la
  réponse finale.
- **Durées propres à ce matériel** (GPU 6 Go, un seul utilisateur) ; elles changeraient avec Groq ou un
  autre GPU.
- **Historique mélangé** : les runs `app` et `agent` viennent d'essais manuels ; seuls les runs `benchmark`
  et `evaluation` suivent un protocole fixe.

Limites propres au fine-tuning :

- **Petit jeu de test** : 31 réponses sur 11 questions seulement (10 ou 11 par niveau). Un écart de moins
  de 0,3 point sur une note du juge n'est pas significatif : seuls la citation (+94 pts) et, dans une moindre
  mesure, le niveau débutant (+0,5) montrent un effet net. Les types de questions du test sont déséquilibrés
  (12 « exemple », 2 « définition »).
- **Juge = modèle enseignant** : qwen2.5:7b a écrit les réponses d'entraînement et note les réponses. Il peut
  préférer son propre style (biais d'auto-préférence), donc favoriser le modèle affiné qui l'imite.
- **Pas de gain au niveau avancé** (3,40 → 3,40) : le modèle raccourcit bien ses réponses, mais le juge ne
  les trouve pas plus techniques. Un modèle de 1,5 milliard de paramètres relie moins bien les notions.
- **Données entièrement synthétiques** : filtrées automatiquement, sans relecture humaine, issues des cours
  d'un seul compte ; le modèle affiné imite aussi les défauts de l'enseignant.
- **Style, pas connaissances** : le modèle affiné est comparé à son propre modèle de base, pas à
  qwen2.5:7b, qui reste le LLM de l'application.
