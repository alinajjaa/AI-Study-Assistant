# Usage de Claude Code sur le projet

Ce document mesure l'usage de **Claude Code** (assistant de développement d'Anthropic, extension VS Code)
pour construire AI Study Assistant : sessions, demandes, jetons consommés, durée, code produit, tests et
bugs corrigés. Les prompts eux-mêmes, module par module, sont dans [prompts-claude-code.md](prompts-claude-code.md).

Instantané du **20/10/2026 à 16 h 33** (chiffres finaux, identiques à ceux du rapport `rapport/rapport.tex`). La
session `fccd8465` (rédaction des livrables) était en cours : ses chiffres sont partiels, et ses compteurs internes
(lignes ajoutées, coût) ne sont mis à jour par Claude Code qu'à certains moments de la session.

## 1. Méthode

### 1.1 Source et script

Claude Code enregistre chaque session dans un fichier JSONL local
(`C:\Users\<utilisateur>\.claude\projects\c--Users-<utilisateur>-study-companion\<session>.jsonl`). Le script
[`backend/scripts/claude_usage.py`](../backend/scripts/claude_usage.py) les relit et produit les tableaux de ce
document :

```powershell
cd backend
.venv\Scripts\python.exe scripts/claude_usage.py `
  --csv ../docs/mesures/claude_code_sessions.csv `
  --csv-prompts ../docs/mesures/claude_code_demandes.csv `
  --md ../docs/mesures/claude_code_sessions.md `
  --modules ../docs/mesures/modules_demandes.json --csv-modules ../docs/mesures/claude_code_modules.csv
```

| Fichier produit | Contenu |
|---|---|
| `docs/mesures/claude_code_sessions.csv` | une ligne par session |
| `docs/mesures/claude_code_demandes.csv` | une ligne par demande de l'utilisateur |
| `docs/mesures/claude_code_modules.csv` | totaux par module du rapport |
| `docs/mesures/modules_demandes.json` | rattachement de chaque demande à un module (fait à la main, relu) |

### 1.2 Règles de comptage

- **Demande (tour)** : un message écrit par l'utilisateur. Les résultats d'outils, les notifications de tâches
  de fond, les commandes `/compact`, les interruptions et les résumés de reprise ne comptent pas.
- **Appel à l'API** : un message de l'assistant. Claude Code écrit un même message sur plusieurs lignes (une
  par bloc de contenu) avec le même identifiant et le même usage : il n'est **compté qu'une fois**. Contrôle :
  pour la session `20d36a24`, la somme obtenue (421 281 jetons de sortie, 156 140 268 jetons lus en cache)
  est identique au compteur interne de Claude Code (ligne `cost-state`).
- **Jetons** : `input_tokens` (entrée hors cache), `cache_creation_input_tokens` (contexte écrit dans le cache
  de prompt), `cache_read_input_tokens` (contexte relu depuis le cache), `output_tokens` (sortie).
- **Durée active** : somme des écarts entre événements consécutifs, en ignorant les pauses de plus de 15 min.
  **Durée API** : temps de réponse du modèle, compteur interne de Claude Code.
- **Lignes ajoutées / supprimées** : compteur interne de Claude Code (`totalLinesAdded`,
  `totalLinesRemoved`) sur les fichiers modifiés par ses outils. **Lignes écrites** : lignes des contenus
  envoyés aux outils `Write` et `Edit` (mesure plus large : une réécriture compte deux fois).
- **Tests et builds** : commandes lancées par Claude Code contenant `pytest`, `ng test`, `ng build` ou
  `vitest`. **En échec** : sortie qui contient un échec (`N failed`, `FAILED`, `error TS…`, code de sortie non
  nul…) ; le drapeau d'erreur des résultats d'outils n'est presque jamais posé, d'où la lecture de la sortie.
- **Équivalent au tarif public de l'API** : montant calculé par Claude Code comme si les jetons avaient été payés
  au tarif public de l'API. Il est **non facturé** : l'équipe utilise Claude Code via un abonnement. Il donne un
  ordre de grandeur du volume consommé, pas une dépense.
- **Confidentialité** : le script ne recopie aucun texte complet ; une demande est résumée en 140 caractères
  après masquage des emails, clés d'API, jetons et variables `*SECRET*`, `*TOKEN*`, `*API_KEY*`, `*PASSWORD*`.
  Les fichiers produits ont été contrôlés (aucun email ni secret).

### 1.3 Périmètre

- **9 sessions** utiles du 11/10 au 20/10/2026 (une dixième, `a9ca2d68`, ne contient qu'une demande sans
  réponse, reprise aussitôt dans `2ab3ba04` : elle est ignorée).
- La première demande enregistrée (11/10) indique « backend/ : FastAPI (déjà terminé, NE PAS le modifier) ».
  Le cœur du backend (client LLM, ingestion PDF, embeddings, Qdrant, tuteur RAG), le **backend** du générateur
  d'examens et celui des flashcards ont été développés **avant, avec Claude en mode conversation (claude.ai)**
  (§7) : leur coût en jetons **n'est pas mesurable**. Les sessions Claude Code couvrent le frontend, les
  phases 4 bis à 9 du backend, l'évaluation, le déploiement et la documentation.

## 2. Outils d'IA générative utilisés

| Outil | Usage | Mesure |
|---|---|---|
| **Claude Code**, modèle **claude-opus-5-5** | tous les messages de l'assistant (génération de code, tests, documentation) | 1 226 appels |
| **claude-haiku-5-5** | tâches annexes de Claude Code (titres, résumés courts), d'après le compteur `modelUsage` | présent dans les 9 sessions ; jetons non comptés dans les tableaux ci-dessous |
| Outils de Claude Code | lecture et recherche de fichiers, `Edit` / `Write` (612 appels), commandes `Bash` / `PowerShell` (1 137), sous-agents (aucun dans ces sessions) | `claude_code_sessions.csv` |

Les LLM **de l'application** (qwen2.5 via Ollama, qwen3.8-27b via Groq, Qwen2.5-1.5B + LoRA) sont décrits dans
[prompts.md](prompts.md) ; ils ne sont pas comptés ici.

## 3. Sessions

| Session | Début | Demande (résumé) | Tours | Appels API | Entrée | Cache (écriture / lecture) | Sortie | Durée active | Lignes ajoutées |
|---|---|---|---|---|---|---|---|---|---|
| `5d902768` | 11/10 13:23 | Frontend du tuteur RAG, puis génération d'examen PDF et flashcards côté Angular | 11 | 106 | 212 | 774 263 / 20 381 507 | 207 805 | 58,0 min | 5 842 |
| `2ab3ba04` | 13/10 23:44 | Phase « AI Personal Tutor » (comptes, SQLite, cours privés, conversations, profil), MLflow, résumés | 5 | 185 | 370 | 894 844 / 52 457 402 | 300 718 | 90,6 min | 6 820 |
| `01cad59c` | 14/10 11:18 | Phase « AI Study Companion » : agent LangGraph et page unique | 1 | 94 | 188 | 335 915 / 21 994 422 | 174 341 | 39,9 min | 4 300 |
| `c528cea3` | 14/10 12:08 | Fusion du tuteur dans la page « Assistant », 4 bugs vus en test réel | 1 | 70 | 140 | 193 969 / 11 081 576 | 69 653 | 16,9 min | 267 |
| `224dfdba` | 14/10 12:42 | Fine-tuning LoRA : jeu de données, notebook Colab, évaluation | 1 | 28 | 56 | 106 644 / 2 754 899 | 54 476 | 13,4 min | 1 629 |
| `20d36a24` | 14/10 13:03 | Documentation, résultats du fine-tuning, Docker et Groq, optimisation des performances, refonte du design | 6 | 330 | 660 | 2 134 288 / 156 140 268 | 421 281 | 157,4 min | 7 747 |
| `755606e7` | 19/10 15:29 | Barre latérale de la page Assistant (interrompue) | 1 | 34 | 68 | 122 619 / 3 574 377 | 57 585 | 10,4 min | 1 584 |
| `b49e2763` | 19/10 15:40 | Barre latérale : refonte, repli, version minimaliste | 4 | 134 | 270 | 402 329 / 32 332 573 | 218 226 | 57,7 min | 3 720 |
| `fccd8465` | 19/10 22:09 | Livrables de la grille d'évaluation et rapport (en cours) | 11 | 245 | 490 | 940 501 / 77 240 427 | 396 328 | 116,4 min | 3 514 |
| **Total** | | **9 sessions** | **41** | **1 226** | **2 454** | **5 905 372 / 377 957 451** | **1 900 413** | **560,7 min** | **35 423** |

Compléments (compteurs internes de Claude Code ; partiels pour `fccd8465`) : **2 779 lignes supprimées** ;
**275,4 min** de temps de réponse du modèle ; équivalent au tarif public de l'API de **151,82 USD** au total
(non facturé : utilisation via un abonnement), de 2,49 USD (`224dfdba`) à 56,74 USD (`20d36a24`).

### 3.1 Lecture des jetons

- **Le cache de prompt porte presque tout le contexte** : 378 millions de jetons relus en cache contre
  2 454 jetons d'entrée hors cache. À chaque appel, Claude Code renvoie le contexte de la session (consignes,
  fichiers lus, échanges) ; le cache évite de le refacturer au plein tarif. C'est ce qui rend économiquement
  possibles les longues sessions comme `20d36a24` (330 appels).
- **La sortie représente 1,9 million de jetons** pour 35 423 lignes ajoutées, soit environ 54 jetons par ligne
  ajoutée. Ce ratio inclut les explications, les rapports et les commandes, pas seulement le code.
- **Une session longue coûte plus par appel** : le contexte grandit à chaque tour. `20d36a24` (6 demandes sur
  5 jours, une compaction le 18/10) relit en moyenne 473 000 jetons de cache par appel, contre 98 000 pour
  `224dfdba` (une seule demande). Ouvrir une nouvelle session par fonctionnalité, comme pour les phases 6 à 9,
  limite ce coût.

## 4. Par module

Rattachement de chaque demande dans `docs/mesures/modules_demandes.json`.

| Module | Demandes | Appels API | Cache lu | Sortie | Durée active | Lignes écrites | Tests / builds (en échec) |
|---|---|---|---|---|---|---|---|
| M1 — Architecture, tuteur RAG, intégration (frontend, comptes, cours privés, page Assistant, Docker, design) | 13 | 579 | 176 298 659 | 822 281 | 221,9 min | 19 972 | 108 (11) |
| M1 + M5 — Study Companion et agent LangGraph (une seule demande) | 1 | 94 | 21 994 422 | 174 341 | 39,9 min | 4 295 | 15 (2) |
| M1 — Optimisation des performances (travaux expérimentaux, non livrés) | 1 | 91 | 45 998 849 | 133 335 | 52,1 min | 1 532 | 14 (6) |
| M2 — Fine-tuning LoRA/QLoRA | 2 | 47 | 7 275 467 | 72 923 | 17,1 min | 1 889 | 5 (1) |
| M3 — Générateur d'examens (frontend ; backend en phase conversationnelle, §7) | 6 | 49 | 10 134 242 | 86 582 | 16,9 min | 1 807 | 7 (2) |
| M4 — Flashcards (frontend ; backend en phase conversationnelle, §7) et résumés (backend et frontend) | 3 | 49 | 19 208 993 | 98 054 | 30,4 min | 3 404 | 15 (3) |
| M5 — MLflow, benchmark, métriques | 3 | 36 | 14 164 851 | 61 497 | 21,8 min | 854 | 9 (1) |
| Transverse — qualité, documentation et rapport | 12 | 281 | 82 881 968 | 451 400 | 186,1 min | 13 479 | 72 (7) |

La part de M1 reflète la répartition réelle du travail fait avec Claude Code dans ces sessions : M1 a porté
l'intégration de bout en bout (frontend, comptes, page Assistant, déploiement, design). Les modules dont le
backend a été écrit en phase conversationnelle avant le 11/10 (M3, M4 pour les flashcards) ont donc moins de
jetons enregistrés : ce travail n'est pas absent, il n'est pas mesurable (§7).

## 5. Gain de productivité

### 5.1 Code produit

| Mesure | Valeur | Source |
|---|---|---|
| Lignes ajoutées par les outils de Claude Code | 35 423 (9 sessions ; partiel pour `fccd8465`) | compteur `totalLinesAdded` |
| Lignes supprimées | 2 779 | compteur `totalLinesRemoved` |
| Lignes écrites par `Write` / `Edit` | 47 232 | `claude_code_sessions.csv` |
| Taille actuelle du projet (répertoire de travail) | backend : 6 984 lignes Python (`app/`) et 3 186 de tests ; frontend : 6 307 lignes TypeScript, 3 222 de tests, 6 702 de HTML et CSS | `wc -l`, 20/10/2026 |
| Durée active cumulée des sessions | 560,7 min (9 h 21) | §3 |
| Statistiques Git (commits, lignes par auteur, `git log --stat`) | **[statistiques Git fournies par l'équipe]** | à compléter par l'équipe |

| Mesure Git | Valeur |
|---|---|
| Nombre de commits | [statistiques Git fournies par l'équipe] |
| Commits par membre (`git shortlog -sn`) | [statistiques Git fournies par l'équipe] |
| Lignes ajoutées / supprimées (`git log --stat`) | [statistiques Git fournies par l'équipe] |
| Branches de fonctionnalité | [statistiques Git fournies par l'équipe] |

### 5.2 Tests

Nombre de tests à la fin de chaque demande (date de la demande), d'après les rapports finaux de Claude Code
(tous au vert), puis mesuré le 19/10 :

| Demande du | Étape | Backend (pytest) | Frontend (vitest) |
|---|---|---|---|
| 11/10 22:46 | Génération d'examen PDF (frontend) | — | 21 |
| 12/10 00:06 | Examen complet / QCM rapide | — | 34 |
| 13/10 12:53 | Flashcards (frontend) | — | 65 |
| 13/10 23:44 | Comptes, cours privés, conversations, profil | 45 | 106 |
| 14/10 01:05 | MLflow et benchmark | 64 | 106 |
| 14/10 10:43 | Résumés | 83 | 129 |
| 14/10 11:18 | Study Companion (agent) | 113 | 149 |
| 14/10 12:08 | Page Assistant et 4 bugs | 126 | 152 |
| 14/10 12:42 | Fine-tuning | 147 | 152 |
| 14/10 16:19 | Docker, Groq, Hugging Face Spaces | 171 | 152 |
| 19/10/2026, mesuré | refonte du design | 171 passés (54 s) | 186 passés, 30 fichiers (5 s) |
| **20/10/2026, mesuré** | fin de la phase qualité et sécurité (`docs/qualite-ia.md`) | **212 passés** | **195 passés**, 31 fichiers |

Claude Code a lancé **245 exécutions de tests ou de builds** ; **33** ont échoué puis ont été corrigées dans la
même demande avant le rapport final. Chaque fonctionnalité a été livrée avec ses tests : les demandes
l'exigeaient (« tous les tests doivent passer », « ajoute des tests pour… »), et Claude Code relançait la suite
complète avant de rendre la main.

### 5.3 Bugs détectés ou corrigés avec l'aide de l'IA

Relevés dans les rapports finaux des sessions. « Détecté par » indique qui a vu le problème en premier.

| # | Date | Bug | Détecté par | Correctif | Test ajouté |
|---|---|---|---|---|---|
| 1 | 11/10 | Avec `responseType: 'blob'`, l'intercepteur ne lisait pas `detail` dans le corps d'erreur (message générique au lieu du message du backend) | Claude, en lisant le code avant d'implémenter | lecture asynchrone du Blob (`from` + `switchMap`), repli si le JSON est invalide | oui |
| 2 | 13/10 | Durée réelle de 10 flashcards : 317 s alors que l'interface annonçait 2 min | Claude, en test réel | durées mesurées dans `FLASHCARD_MINUTES` (demande suivante) | oui |
| 3 | 13/10 | Fragments de chunks trop courts enregistrés seuls (« ingle one. ») | utilisateur | dernier morceau de page de moins de `MIN_CHUNK_CHARS` rattaché au précédent (`ingest.py`) | oui |
| 4 | 14/10 | MLflow 3 refuse le stockage `file:./mlruns` (mode maintenance) | Claude, en test réel | URI par défaut `sqlite:///mlruns/mlflow.db` | oui |
| 5 | 14/10 | `reponse_trouvee` faussée par les questions hors cours du benchmark | Claude, signalé dans son rapport | métrique limitée aux questions du cours | oui |
| 6 | 14/10 | Puce de résumé terminée par un `}` parasite | Claude, en test réel | caractère retiré à la validation | oui |
| 7 | 14/10 | Plusieurs sections de résumé avec le même titre | Claude, en test réel | titres déjà utilisés passés au prompt | oui |
| 8 | 14/10 | Prénom tapé par l'étudiant répété dans les traces MLflow de l'agent | Claude, en test réel | réponses masquées dans les traces | oui |
| 9 | 14/10 | Classification de repli qui inventait un cours au lieu de demander lequel | Claude, en test réel | cours retenu seulement s'il existe et si l'étudiant l'a nommé | oui |
| 10 | 14/10 | Agent qui recopiait les questions du quiz dans sa réponse finale | Claude, en test réel | `short_reply` (coupé avant la liste, 3 phrases) | oui |
| 11 | 14/10 | Le cours choisi par le LLM remplaçait le cours sélectionné dans la page | utilisateur | le cours sélectionné prime toujours (`chosen_course`) | oui |
| 12 | 14/10 | « Résume les idées principales de ce cours » routé vers `ask_course` | utilisateur | formulations ajoutées aux prompts + garde-fou `COURSE_SUMMARY` ; 6 cas ajoutés à l'évaluation | oui |
| 13 | 14/10 | Réponse hors cours complétée par du texte du modèle et des sources | utilisateur | seule la phrase de refus est gardée | oui |
| 14 | 14/10 | Boutons rapides qui recouvraient les derniers messages | utilisateur | boutons intégrés au bloc de saisie | oui |
| 15 | 14/10 | Juge du fine-tuning qui notait presque tout 1 ou 2 : il recopiait l'exemple de format `{"niveau": 1, …}` | Claude, en test réel | exemple retiré, justification demandée avant les notes | oui |
| 16 | 14/10 | Notebook Colab : erreur « Attempting to unscale FP16 gradients » (poids LoRA en float16 sur T4) ; second envoi des données renommé `train (1).jsonl` | utilisateur (erreur sur Colab) | `bf16=False`, poids LoRA en float32, chemins `data/` fixes | contrôle de syntaxe des cellules |
| 17 | 14/10 | Build Docker en échec : `requirements.txt` en retard sur le venv (`websockets`, `orjson`, `uuid_utils`) ; URL de l'API absolue dans le build de production | Claude, pendant le build | `requirements.txt` aligné sur `pip freeze` ; `/api` relatif en production | test de bout en bout dans Docker |

Les 10 bugs corrigés pendant la phase conversationnelle (claude.ai), avant Claude Code, sont listés au §7.3.

S'y ajoute, dans les travaux expérimentaux du 18/10 (non livrés, voir le rapport, « Perspectives ») : sous
Windows, `localhost` passe d'abord par IPv6, où Ollama n'écoute pas, ce qui coûtait environ 2,1 s par nouvelle
connexion (détecté par Claude en mesurant le streaming).

**Bilan : 17 bugs** tracés dans les sessions Claude Code, dont **11 détectés par Claude Code** lui-même (lecture du code, essais
avec le vrai modèle, build) et 6 signalés par l'utilisateur puis corrigés par Claude Code ; 15 sur 17 sont
couverts par un test automatisé (les bugs 16 et 17 ont été vérifiés sur Colab et par un essai de bout en bout dans Docker).

### 5.4 Ce que l'on peut en conclure

- **Volume** : 35 423 lignes ajoutées en 9 h 21 de sessions actives. Ce chiffre mesure ce que Claude Code a
  écrit, pas un gain par rapport à un développement sans IA : l'équipe n'a pas de mesure de référence sans
  outil, et les estimations de temps « à la main » ne sont pas mesurées.
- **Qualité maintenue** : chaque livraison passe par les tests (212 + 195 aujourd'hui) et, pour les
  fonctionnalités LLM, par un essai réel (Ollama, Qdrant, base et MLflow temporaires).
- **Le gain vient surtout de trois choses** : l'écriture rapide du code répétitif (composants Angular, routes,
  schémas, tests), la vérification systématique (245 exécutions de tests ou builds) et la détection de bugs en
  conditions réelles (11 bugs sur 17).
- **Le temps humain se déplace vers la spécification et la relecture** : les demandes font en moyenne
  3 983 caractères pour les 22 demandes longues (voir [prompts-claude-code.md](prompts-claude-code.md)) ; les
  tests visuels dans un navigateur restent à la charge de l'équipe (Claude le signale dans plusieurs rapports).

## 6. Limites et écarts observés

- **Consigne « aucune commande git » non respectée deux fois** : `git status` (session `c528cea3`) et
  `git diff --stat` (`224dfdba`), en lecture seule. Claude Code l'a signalé lui-même dans son rapport. Aucune
  modification du dépôt.
- **Fonctionnalité testée puis abandonnée** : la « plage de pages » de l'examen (13/10 11:06) a été implémentée et
  testée (51 tests frontend), puis **retirée volontairement par l'équipe** : sur des diapositives, une plage de
  quelques pages contient trop peu de passages utiles, et l'examen complet sortait incomplet (barème sur 15 au
  lieu de 20). À la demande suivante, Claude a constaté le retrait et ne l'a pas réintroduit ; les 13 tests
  correspondants ont été retirés avec la fonctionnalité (51 → 38 tests frontend).
- **Vérifications visuelles non faites** : Claude précise dans plusieurs rapports qu'il n'a pas testé la
  modale, les animations ou la mise en page dans un navigateur ; ces points restent à vérifier à la main.
- **Coût d'une requête de test interrompue** : en vérifiant les erreurs de la plage de pages, une requête réelle
  d'examen complet a été coupée au bout de 3 s, mais le backend a continué à générer environ 2 minutes.
- **Contexte des longues sessions** : `20d36a24` a nécessité une compaction (`/compact`) le 18/10 ; le
  contexte relu en cache a dépassé 156 millions de jetons sur la session.
- **Mesures** : l'usage de `claude-haiku-5-5` n'est pas détaillé par demande ; la durée active est une
  approximation (seuil de 15 min) ; le rattachement des demandes aux modules est un choix de l'équipe.

## 7. Phase conversationnelle (claude.ai), avant Claude Code

### 7.1 Ce qui a été fait

Le cœur du backend a été développé **avec Claude en mode conversation (claude.ai)**, avant l'adoption de
Claude Code : client LLM, ingestion des PDF et tuteur RAG, générateur d'examens, schémas Pydantic avec leurs
expressions régulières de validation, générateur de flashcards. C'est pourquoi la première session Claude Code
(11/10) qualifie le backend de « déjà terminé ».

### 7.2 Méthode et type d'interactions

- **L'assistant fournissait le code** : des fichiers complets, ou des modifications au format « ancien bloc /
  nouveau bloc » à remplacer dans un fichier existant.
- **L'étudiant intégrait** le code à la main dans le dépôt, lançait le programme ou les tests, puis **renvoyait
  les erreurs et les sorties** (traceback, sortie de pytest, réponse brute du LLM) dans la conversation.
- **L'assistant diagnostiquait** à partir de ces sorties et proposait le correctif suivant.

Différences avec Claude Code : l'assistant ne lisait pas le dépôt et n'exécutait rien ; chaque cycle passait par
un copier-coller. Deux bugs de la liste ci-dessous (C2, C3) viennent directement de ce mode de travail : un
collage partiel ou un bloc collé sans retirer l'ancien. Claude Code supprime ce risque en modifiant les fichiers
lui-même et en relançant les tests.

### 7.3 Bugs corrigés pendant cette phase

| # | Bug | Symptôme | Correctif (dans le code actuel) |
|---|---|---|---|
| C1 | Caractères de contrôle dans le JSON | un chemin comme `C:\flutter\bin` cité dans une question arrivait avec un saut de page (`\f`) ou un retour arrière (`\b`) : l'antislash mal échappé par le modèle était interprété par le décodeur JSON | `CONTROL_CHARS` et `capitalize_first` (`app/phase4_exam/schemas.py`) restaurent `\f`, `\b`, `\t`, `\r`, `\v` |
| C2 | `NameError` après un collage partiel | après le collage d'une partie seulement de `schemas.py`, un nom utilisé dans le fichier n'était plus défini (`NameError` à l'import) | fichier `schemas.py` renvoyé en entier, puis tests relancés |
| C3 | Lignes dupliquées dans `generator.py` | lignes dupliquées après l'intégration d'une modification « ancien bloc / nouveau bloc » | bloc dédupliqué ; consigne de fournir des blocs « ancien / nouveau » uniques et assez longs pour être repérés |
| C4 | Questions ouvertes rejetées à tort | `DOUBLE_QUESTION` (« … et comment… ») refusait les questions de réflexion qui enchaînent légitimement deux consignes | `OpenQuestion.clean_question` n'applique plus `DOUBLE_QUESTION` : seul un second « ? » est refusé |
| C5 | Attribut `page` supprimé dans `Flashcard` | une modification du modèle avait supprimé l'attribut `page` : les cartes perdaient leur numéro de page | `page: int = Field(ge=1)` rétabli, page la plus proche si le modèle se trompe (`make_card`) |
| C6 | Caractères cyrilliques générés | lettres cyrilliques glissées dans un mot français (« effектer ») | `NON_LATIN` dans `check_french` : rejet des caractères cyrilliques, arabes ou chinois |
| C7 | Réponses tronquées par `maxLength` | le schéma JSON envoyé au serveur porte `maxLength` (verso de carte : 250 caractères) ; des réponses arrivaient coupées en pleine phrase | consigne « moins de 250 caractères » dans le prompt et validateur « réponse coupée » (le verso doit finir par une ponctuation) |
| C8 | Doublons de cartes | deux cartes posant la même question avec d'autres mots | similarité cosinus des embeddings e5 : carte écartée au-delà de `CARD_SIMILARITY` = 0,92 ; concepts fusionnés au-delà de 0,97 |
| C9 | Juge trop strict | la vérification d'une carte rejetait des cartes correctes | question posée à l'envers (« contient-elle une ERREUR ? ») avec « Réponds true seulement si tu es sûr » (`verify_card`) |
| C10 | Fragments de chunks trop courts | des bouts de découpage (« ingle one. ») ou des titres faisaient inventer des cartes | passages de moins de `MIN_PASSAGE_CHARS` = 60 caractères exclus des flashcards et des résumés (et de 250 pour les examens) ; côté ingestion, rattachement du dernier morceau court (bug 3 de la phase Claude Code) |

### 7.4 Mesures

**Jetons non mesurables** : les conversations claude.ai ne laissent pas de fichier de session local, et aucun
export n'est conservé dans le projet. Le nombre de conversations, de messages et de jetons de cette phase n'est
donc pas connu. Seuls ses résultats sont mesurables : le code actuel du backend et les tests qui le couvrent
(212 tests pytest au 20/10/2026).
