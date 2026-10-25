# Prompts et paramètres des appels au LLM

Ce document recense **tous les appels au LLM** faits par `backend/app`. Pour chacun : module, rôle, prompt
système, gabarit du message utilisateur, modèle, `temperature`, `top_p`, `max_tokens`, format de sortie,
nouvelles tentatives, mémoire, masquage des données personnelles et justification des valeurs. Il se termine
par la comparaison des modèles utilisés, avec les mesures disponibles.

Chemins relatifs à `backend/`. Les prompts sont recopiés depuis le code. Les gabarits ne contiennent aucune
donnée personnelle : les `{variables}` sont remplies à l'exécution, puis passées par `mask_pii`.

Sources des mesures :

| Mesure | Source |
|---|---|
| Jetons d'entrée et de sortie, durée et débit par appel | `docs/mesures/jetons_par_appel_qwen2.5-7b-gpu.csv` et `docs/mesures/jetons_par_appel_qwen2.5-7b.csv`, produits le 19/10/2026 par `backend/scripts/measure_prompts.py` (section 4) |
| Examens, flashcards, résumés, tuteur, agent ; comparaison avec Groq | `docs/evaluation.md` (benchmark MLflow, CSV de `app/phase5_evaluation/results/`) |
| Fine-tuning | `docs/evaluation.md` §2.6, `app/phase4_finetuning/results/finetuning_2026-10-14_1704.csv` |
| Benchmark de la variante GPU | `app/phase5_evaluation/results/Chapter1_Part_1_2026-10-18_1729.csv` (MLflow, 18/10/2026) |
| Débit et répartition CPU / GPU d'Ollama | mesures de l'équipe (section 12.3), recoupées par les deux CSV de `docs/mesures/` |

---

## 1. Chaîne d'appel commune

Tous les appels passent par **`chat(system, user, max_tokens, temperature, json_mode, json_schema)`**
(`app/phase1_llm/llm.py`) : un message `system`, un message `user`, l'API compatible OpenAI (bibliothèque
`openai`). La seule exception est l'**agent**, qui appelle le même serveur et le même modèle par `ChatOpenAI`
(LangChain) pour le *tool calling*.

| Élément | Valeur | Où |
|---|---|---|
| Modèle | `LLM_MODEL`, le même pour tous les appels. En développement : `qwen2.5-7b-gpu` (Ollama, section 12) ; avec Docker et Groq : `qwen/qwen3.8-27b`. Si `LLM_MODEL` n'est pas défini, le code prend `DEFAULT_LLM_MODEL` = `qwen2.5:7b` (corrigé : c'était `qwen2.5:3b`, voir `docs/qualite-ia.md`) | `app/core/config.py`, `backend/.env.example` |
| Serveur | `LLM_BASE_URL` (Ollama `http://localhost:11434/v1` par défaut, ou Groq) | `app/core/config.py` |
| Timeout | `LLM_TIMEOUT` = 120 s par appel | `app/core/config.py` |
| `temperature` | fixée par chaque appelant (0 à 0.7) ; 0.3 par défaut dans `chat()` | section 2 |
| `top_p` | **jamais envoyé** par le code : c'est la valeur par défaut du fournisseur qui s'applique, **0.9 pour Ollama** (documentation des paramètres du Modelfile ; `qwen2.5:7b` ne la redéfinit pas, `ollama show` n'affiche aucun `PARAMETER`) et **1 pour Groq** (valeur par défaut de l'API compatible OpenAI). Seul le modèle affiné local fixe `top_p = 0.9` (`app/phase4_finetuning/hf_local.py`) | — |
| `max_tokens` | fixé par chaque appelant ; 1024 par défaut dans `chat()` ; non fixé pour l'agent (limite du serveur) | section 2 |
| Autres paramètres d'échantillonnage | non envoyés : valeurs d'Ollama (`top_k` 40, `repeat_penalty` 1.1) | — |
| Sorties JSON | `response_format = json_schema` avec le schéma Pydantic de l'appelant ; repli sur `json_object` si le modèle refuse le schéma (mémorisé par modèle) ou n'arrive pas à le respecter (Groq `json_validate_failed`) ; `LLM_JSON_MODE=json_object` force le repli | `_response_format`, `chat()` |
| Nouvelles tentatives (couche transport) | client OpenAI `max_retries = 1` (erreurs de connexion, 408, 409, 429, 5xx) | `client = OpenAI(...)` |
| Nouvelles tentatives (limite de débit) | erreur 429 : attente du délai indiqué (`retry-after`, « try again in … »), sinon 2, 4, 8, 16 s ; `LLM_RATE_LIMIT_RETRIES` = 4 essais, attente maximale `LLM_RATE_LIMIT_MAX_WAIT` = 60 s ; limite quotidienne : arrêt immédiat | `_create()` |
| Erreurs | timeout, serveur injoignable, clé absente ou invalide, quota, réponse vide → `LLMError` avec un message en français → HTTP 503 | `chat()` |
| Mesure | chaque appel incrémente `appels_llm` (MLflow) ; replis et attentes sont comptés (`replis_json_object`, `attentes_limite_debit`) | `app/phase5_evaluation/stats.py` |

### 1.1 Protections communes

| Protection | Où | Effet |
|---|---|---|
| `mask_pii(text)` | `app/core/privacy.py` | Remplace les emails par `[EMAIL]` et les numéros de 8 à 14 chiffres (téléphone, CIN), avec indicatif et séparateurs facultatifs, par `[NUMÉRO]`. Appliqué à **chaque message utilisateur envoyé au LLM**, à chaque ligne d'historique et aux noms de cours ou de concepts injectés dans les prompts système. |
| Prompt système sans identité | tous les appels | Le prompt système ne contient jamais l'email ni le nom de l'étudiant : seulement son **niveau**, les **noms de ses cours** et des **noms de concepts** issus du cours. |
| Journalisation masquée | `rag.py`, traces MLflow de l'agent | La question est journalisée après `mask_pii` ; les traces de l'agent sont masquées. |
| Sorties structurées | `chat(..., json_schema=...)` | Le serveur contraint la réponse au schéma JSON du modèle Pydantic. |
| Validateurs Pydantic | `schemas.py` de chaque phase | Chaque élément est relu (longueurs, formats, français, pages citées, règles métier). Un élément invalide est rejeté et compté (`reject("validation")`), jamais affiché. |
| Auto-vérification | examens, flashcards | Un second appel à température 0 relit la sortie avec le cours ; une sortie jugée fausse est écartée. |
| Doublons de sens | examens, concepts, flashcards | Similarité cosinus entre embeddings e5 ; au-delà d'un seuil, la sortie est écartée. |

---

## 2. Tableau récapitulatif des appels

Tous les appels utilisent le modèle `LLM_MODEL` et le `top_p` par défaut du fournisseur (0.9 avec Ollama,
1 avec Groq). « Tentatives » désigne les nouvelles tentatives **de l'application**, en plus de celles de
`chat()` (section 1).

| # | Module | Appel (fonction) | Rôle | `temperature` | `max_tokens` | Sortie | Tentatives et repli | Mémoire |
|---|---|---|---|---|---|---|---|---|
| 1 | Tuteur RAG | `rag._answer` → `chat` | réponse citée [p.X] à partir de 3 passages | 0.3 | 1024 | texte (markdown) | aucune ; refus détecté | 3 derniers échanges, niveau, points faibles |
| 2 | Examens | `generate_section` (qcm) | 1 QCM par passage | 0.5 | 500 | `json_schema` `MCQBatch` | budget de 5 appels par question demandée | 10 dernières questions posées |
| 3 | Examens | `generate_section` (vrai_faux) | 1 affirmation vraie ou fausse | 0.5 | 300 | `TrueFalseBatch` | idem | idem |
| 4 | Examens | `generate_section` (courte) | 1 question à réponse courte | 0.5 | 300 | `ShortAnswerBatch` | idem | idem |
| 5 | Examens | `generate_section` (ouverte) | 1 question de réflexion, 3 passages | 0.5 | 600 | `OpenBatch` | idem ; points manquants complétés par des V/F | idem |
| 6 | Examens | `verify_mcq` | retrouver la lettre sans le corrigé | 0 | 100 | `LetterAnswers` | aucune ; échec → question gardée sans contrôle | — |
| 7 | Examens | `verify_true_false` | juger l'affirmation | 0 | 60 | `BoolAnswers` | idem | — |
| 8 | Examens | `verify_written` | juger la réponse attendue (courte, ouverte) | 0 | 20 | `BoolAnswers` | idem | — |
| 9 | Flashcards | `extract_concepts` | 3 notions clés par bloc de 3 passages | 0.2 | 200 | `ConceptBatch` | aucune ; bloc ignoré si erreur | — |
| 10 | Flashcards | `make_card` | 1 carte sur un concept imposé | 0.4 puis 0.7 | 250 | `FlashcardBatch` | 2 tentatives par concept | — |
| 11 | Flashcards | `verify_card` | détecter une erreur dans la carte | 0 | 20 | `BoolAnswers` | aucune ; échec → carte gardée | — |
| 12 | Résumés | `summarize_section` (map) | titre + 3 à 5 puces pour 6 passages | 0.3 puis 0.5 | 600 | `SectionDraft` | 2 tentatives, puis section ignorée | titres déjà utilisés |
| 13 | Résumés | `write_overview` (reduce) | vue d'ensemble de 4 à 6 phrases | 0.3 puis 0.5 | 500 | `OverviewDraft` | 2 tentatives, puis repli sans invention | — |
| 14 | Résumés | `explain_topic` | explication structurée d'un thème | 0.3 puis 0.5 | 900 | `TopicDraft` | 2 tentatives | niveau ; **cache** des résumés de cours |
| 15 | Agent | nœud `agent` (`ChatOpenAI`) | choisir un outil, puis réponse finale | 0 | limite du serveur | *tool calling* | client : `max_retries = 4` ; outil invalide → appel 16 | 6 derniers messages (300 caractères), cours, niveau |
| 16 | Agent | `classify_intent` | classification d'intention de repli | 0 | 150 | `IntentDecision` | aucune ; sortie invalide → « aucun » | demande précédente |
| 17 | Agent | `label_concepts` | notion testée par chaque question d'un quiz | 0 | 300 | `CONCEPTS_SCHEMA` | aucune ; repli : début de la question | — |
| 18 | Fine-tuning (hors application) | `dataset.py` : question | question d'étudiant par passage | 0.7 | 120 | schéma `{"question"}` | — | — |
| 19 | Fine-tuning (hors application) | `dataset.py` : réponse | réponse « idéale » de l'enseignant | 0.3 | 700 | texte | filtres de rejet | — |
| 20 | Fine-tuning (hors application) | `evaluate.py` : juge | note de 1 à 5 (niveau, fidélité, clarté) | 0 | 250 | schéma (entiers 1 à 5) | réponse inutilisable → ignorée | — |

---

## 3. Justification des valeurs

### 3.1 Température

| Valeur | Appels | Raison |
|---|---|---|
| **0** | vérifications (6, 7, 8, 11), agent (15), classification (16), étiquetage (17), juge (20) | Ce sont des **décisions** (lettre, vrai/faux, outil, note) : une même entrée doit donner la même sortie, et le hasard n'apporte rien. L'agent à 0 choisit toujours le même outil pour la même demande, ce qui rend l'évaluation `taux_bon_outil` reproductible. |
| **0.2** | concepts (9) | Extraction : on veut les notions du passage, pas des variantes ; une légère variété évite de renvoyer toujours la même notion générique. |
| **0.3** | tuteur (1), première tentative des résumés (12 à 14), réponses du jeu de fine-tuning (19) | Texte pédagogique **fidèle** au cours : une température basse limite les inventions, sans le style figé de 0. Le jeu de fine-tuning reprend la même valeur pour imiter le tuteur de l'application. |
| **0.4** | flashcards (10, 1re tentative) | Un peu plus de variété entre les cartes d'un même paquet (moins de doublons de sens). |
| **0.5** | génération d'examens (2 à 5), seconde tentative des résumés | Les questions doivent **varier** d'un examen à l'autre et éviter les doublons (rejets pour doublon : 16,4 % en moyenne, `docs/evaluation.md` §2.1), tout en restant ancrées sur un passage imposé. La justesse est contrôlée ensuite par la vérification à 0. |
| **0.7** | flashcards (10, 2e tentative), questions du jeu de fine-tuning (18) | Une carte rejetée est redemandée avec **un autre tirage** : à 0.4, le modèle redonnerait souvent la même carte invalide. Les questions du jeu de fine-tuning doivent être variées. |

### 3.2 `top_p`

Le code n'envoie jamais `top_p` : la valeur par défaut du fournisseur s'applique (0.9 pour Ollama, 1 pour
Groq). Ce choix est volontaire : la **température** est le seul réglage de diversité, ce qui garde un seul
paramètre à expliquer et à comparer entre appels. À température 0, `top_p` n'a pas d'effet (décodage
glouton). Pour le modèle affiné local (`transformers`), il faut le fixer explicitement : `top_p = 0.9`, la
même valeur qu'Ollama, pour comparer les deux dans les mêmes conditions.

### 3.3 `max_tokens`

Chaque `max_tokens` est un **plafond de sécurité** (boucle du modèle, sortie qui ne s'arrête pas), pas une
longueur visée : la longueur est fixée par le prompt (« 1 ou 2 phrases », « 3 à 5 puces », « 4 éléments »).
Les mesures (section 4) montrent qu'aucune sortie ne l'atteint (colonne `tronque` toujours fausse) :

| Appel | `max_tokens` | Sortie la plus longue mesurée | Marge |
|---|---|---|---|
| Tuteur | 1024 | 193 jetons | × 5,3 |
| Examen QCM | 500 | 125 | × 4 |
| Examen V/F | 300 | 94 | × 3,2 |
| Examen courte | 300 | 73 | × 4,1 |
| Examen ouverte | 600 | 186 | × 3,2 |
| Vérifications | 20 à 100 | 7 | × 3 à 14 |
| Concepts | 200 | 42 | × 4,8 |
| Carte | 250 | 87 | × 2,9 |
| Section de résumé | 600 | 148 | × 4,1 |
| Vue d'ensemble | 500 | 111 | × 4,5 |
| Classification | 150 | 27 | × 5,6 |

Les petits plafonds des vérifications (20 jetons pour `{"answers":[true]}`, 6 jetons mesurés) coupent court à
un modèle qui se mettrait à expliquer sa réponse. Revers constaté avec Groq : les modèles « à raisonnement »
(gpt-oss) consomment ces petits budgets pour réfléchir et échouent, d'où le choix de qwen3.8-27b
(`docs/deploiement.md`). Une carte est limitée à 250 jetons et son verso à 250 **caractères** par le
validateur : une carte coupée par `max_tokens` (verso sans ponctuation finale) est rejetée par le validateur
au lieu d'être affichée tronquée.

### 3.4 Format de sortie

- **Texte libre** pour le tuteur : la réponse est affichée telle quelle (markdown converti par `marked`, puis
  nettoyé par la sanitization d'Angular).
- **`json_schema`** pour tout ce que le code doit relire : la forme est garantie par le serveur, le contenu
  par Pydantic. Le prompt garde un **exemple de format** (`Format attendu : …`), utile au modèle même avec un
  schéma, et indispensable en repli `json_object`.
- **Tool calling** pour l'agent : les outils sont décrits par leurs modèles Pydantic (`openai_tools()`).

### 3.5 Nouvelles tentatives

- Les **erreurs transitoires** (réseau, 5xx, 429) sont gérées une seule fois, dans `chat()` : les modules
  n'ont pas à les connaître.
- Les **sorties invalides** sont gérées par chaque module, car le bon repli dépend du contexte : budget
  d'appels (examens, puisqu'on peut passer au passage suivant), seconde tentative à température plus haute
  (cartes, résumés), repli déterministe (vue d'ensemble, classification, étiquetage).
- Une **vérification impossible** garde la sortie (`verifications_impossibles`) : une panne du vérificateur
  ne doit pas vider un examen. C'est un compromis entre disponibilité et justesse, compté dans MLflow.

---

## 4. Jetons et durée mesurés par appel

Script : `backend/scripts/measure_prompts.py`. Il remplace `chat` dans chaque module par un appel à l'API
native d'Ollama (`/api/chat`), qui renvoie les jetons comptés par le modèle, puis appelle **les vraies
fonctions du code** (`build_prompt`, `verify`, `extract_concepts`, `make_card`, `summarize_section`,
`classify_intent`…) avec les mêmes `temperature`, `max_tokens` et schémas JSON. Passages : 10 passages réels
du cours *CNN_intro* (article public, sans donnée personnelle), relus dans
`app/phase4_finetuning/data/results_base.jsonl`. Une seule exécution par modèle, le 19/10/2026, sur la
RTX 4050 (6 Go).

| Appel | Entrée (jetons) | Sortie, 7b-gpu | Sortie, 7b | Durée, 7b-gpu | Durée, 7b |
|---|---|---|---|---|---|
| Tuteur (premier appel, chargement du modèle compris) | 737 | 157 | 180 | 13,9 s | 16,1 s |
| Tuteur, question de suivi avec historique | 814 | 124 | 193 | 4,5 s | 9,7 s |
| Tuteur, question hors cours (refus) | 662 | 11 | 11 | 0,9 s | 1,1 s |
| Examen : génération QCM | 735 | 109 | 125 | 4,1 s | 6,6 s |
| Examen : vérification QCM | 334 | 6 | — (QCM rejeté par la validation) | 0,7 s | — |
| Examen : génération V/F | 590 | 83 | 94 | 2,9 s | 4,9 s |
| Examen : vérification V/F | 291 à 300 | 7 | 7 | 0,5 s | 0,9 s |
| Examen : génération courte | 565 | 73 | 69 | 2,5 s | 3,7 s |
| Examen : vérification courte | 319 à 323 | 6 | 6 | 0,5 s | 0,7 s |
| Examen : génération ouverte (3 passages) | 903 | 165 | 186 | 6,2 s | 9,6 s |
| Examen : vérification ouverte | 673 à 692 | 6 | 6 | 0,8 s | 1,1 s |
| Flashcards : concepts (3 passages) | 629 | 42 | 38 | 1,7 s | 2,6 s |
| Flashcards : carte (2 passages) | 548 à 550 | 82 | 87 | 2,6 s | 4,4 s |
| Flashcards : vérification | 417 | — (carte rejetée par la validation) | 6 | — | 0,9 s |
| Résumé : section (6 passages), 1re tentative | 1 233 | 142 | 132 | 5,4 s | 7,4 s |
| Résumé : section, 2e tentative | 1 233 | 120 | 148 | 3,9 s | 7,3 s |
| Résumé : vue d'ensemble | 286 | — (section rejetée deux fois) | 111 | — | 5,5 s |
| Agent : classification de repli | 289 | 27 | 27 | 1,1 s | 1,7 s |
| Agent : choix d'outil (*tool calling*, 5 outils décrits) | 994 | 27 | 27 | 1,6 s | 2,3 s |
| **Débit moyen de sortie** (hors premier appel) | | **35,6 tok/s** (16 appels) | **23,0 tok/s** (17 appels) | | |

Lecture :

- **L'entrée domine** : 290 à 1 230 jetons en entrée pour 6 à 190 jetons en sortie. Le coût d'un appel tient
  surtout aux passages du cours injectés ; c'est pourquoi le tuteur garde 3 passages (`TOP_K`) et les élague
  avec une marge de score, et pourquoi une réponse précédente est tronquée à 600 caractères dans l'historique.
- **Les vérifications sont peu coûteuses** (6 ou 7 jetons de sortie, moins d'une seconde) : elles relisent le
  passage mais ne produisent presque rien. Un examen complet en fait une par question gardée.
- **Le plus long prompt** (section de résumé, 1 233 jetons) tient dans le contexte de 4 096 jetons de
  `qwen2.5-7b-gpu`, avec la place pour 600 jetons de sortie.
- **Le choix d'outil coûte 994 jetons d'entrée** pour un message de 9 mots : la description des 5 outils et le
  prompt système de l'agent pèsent plus que la demande.
- **Le refus hors cours est court** (11 jetons) : la phrase exacte imposée par le prompt.
- Cette exécution a aussi montré trois comportements gérés par le code : un V/F vérifié a reçu deux réponses
  pour une affirmation (`[true,false]`, réponse en trop ignorée par `_keep_matching`) ; une carte et une
  section ont été rejetées par la validation (d'où les tentatives) ; un concept trop vague (« Artificielle »)
  a été accepté par le validateur `Concept`.

Le coût en argent est nul en local (Ollama). Avec Groq, l'offre gratuite limite à 8 000 jetons par minute
(`docs/deploiement.md`) : un examen complet (≈ 49 appels de 300 à 900 jetons) dépasse cette limite et impose
des attentes.

---

## 5. Mémoire et cache

| Mémoire | Où | Contenu envoyé au LLM | Limites |
|---|---|---|---|
| Historique du tuteur | `rag.py` (`HISTORY_TURNS`, `HISTORY_ANSWER_CHARS`), `conversation_routes.py` | 3 derniers échanges « Étudiant : … / Tuteur : … », masqués ; une réponse précédente est tronquée à 600 caractères | La route `/ask` (sans conversation) n'envoie pas d'historique. La règle `HISTORY_RULE` interdit de répondre à partir de l'historique. |
| Reformulation des questions de suivi | `rag.search_query` | rien de plus au LLM : la **recherche** Qdrant utilise la question précédente + la question actuelle si celle-ci est une question de suivi (mot de liaison, pronom, 4 mots ou moins) | — |
| Profil : niveau | `users.level`, `LEVEL_INSTRUCTIONS` | une consigne de niveau (débutant, intermédiaire, avancé) dans le prompt système du tuteur, de l'explication de thème et de l'agent | Le niveau est choisi par l'étudiant ; le code ne fait que suggérer un changement (20 révisions minimum). |
| Profil : points faibles | `profile.weak_points`, `WEAK_POINT_RULE` | les noms des points faibles **touchés par la question**, masqués | 5 points faibles au plus, 2 révisions ou réponses minimum. |
| Historique de l'agent | `graph.initial_messages` | 6 derniers messages de 300 caractères au plus, masqués | — |
| Questions déjà posées (examens) | `build_prompt` | 10 dernières questions de l'examen en cours | Limite la longueur du prompt ; les doublons plus anciens sont filtrés par embeddings. |
| Titres déjà utilisés (résumés) | `summarize_section` | titres des sections précédentes | — |
| **Cache des résumés** | `phase9_summaries/routes.py` (`cached_course_summary`) | aucun appel : le résumé « cours entier » est relu en base (un par cours et par étudiant) | Invalidé quand le cours est réimporté. Pas de cache pour les explications de thème. |
| Repli JSON mémorisé | `llm._json_object_only` | — | Un modèle qui refuse `json_schema` ne coûte qu'une erreur par processus. |
| Modèles chargés une fois | `lru_cache` (embeddings e5), `hf_local.load()` | — | — |

Il n'y a **pas de cache des réponses du LLM** (le même prompt est recalculé) en dehors du cache des résumés.
Côté serveur, `OLLAMA_KEEP_ALIVE=-1` garde le modèle chargé (section 12.3).

---

## 6. Tuteur RAG (phase 3)

Fichier : `app/phase3_rag/rag.py`. Appel : `chat(system, user_prompt)`, température **0.3**, `max_tokens`
**1024**, texte libre (markdown).

### 6.1 Prompt système de base (`SYSTEM_PROMPT`)

Rôle : répondre uniquement à partir des extraits du cours, citer les pages, refuser hors cours.

```text
Tu es un tuteur qui aide un étudiant à comprendre SON cours.
Règles :
- Réponds UNIQUEMENT à partir des extraits du cours fournis dans le contexte.
- Ignore les informations personnelles ou hors sujet présentes dans la question (nom, email, [EMAIL], [NUMÉRO]…) et réponds uniquement à la partie qui concerne le cours.
- Si la réponse n'est pas dans les extraits, réponds exactement : "Cette information n'est pas présente dans le cours."
- Termine chaque phrase importante par la page d'où vient l'information, sous la forme [p.X]. Exemple : « Le pooling réduit la taille des cartes d'activation [p.8]. »
- Réponds dans la langue de la question, de façon claire et pédagogique.
```

Technique : rôle, règles numérotées, **phrase de refus exacte** (détectable par le code), **exemple de
citation** (few-shot minimal), consigne explicite sur les marqueurs `[EMAIL]` / `[NUMÉRO]`.

### 6.2 Règles ajoutées selon le contexte (`build_system_prompt`)

| Règle | Ajoutée quand | Texte |
|---|---|---|
| `HISTORY_RULE` | la conversation a des échanges précédents | « Les échanges précédents servent uniquement à comprendre la question (ex. « et pour les CNN ? ») : la réponse vient toujours des extraits du cours. » |
| `WEAK_POINT_RULE` | la question touche un point faible de l'étudiant | « La question porte sur {concepts}, une notion que l'étudiant marque souvent « à revoir » dans ses flashcards. Signale-le avec bienveillance en une phrase à la fin de ta réponse et propose-lui de la revoir. » |
| `LEVEL_RULE` + consigne de niveau | le niveau de l'étudiant est connu | « Adapte ton explication au niveau indiqué ci-dessous, sans changer les règles précédentes : les informations viennent toujours des extraits et sont citées [p.X] (une analogie sert seulement à illustrer). » |

Consignes de niveau (`LEVEL_INSTRUCTIONS`, réutilisées par les résumés et l'agent) :

| Niveau | Consigne |
|---|---|
| `debutant` | « Niveau de l'étudiant : débutant. Utilise des mots simples, définis chaque terme technique, donne une analogie de la vie courante et un exemple concret. » |
| `intermediaire` | « Niveau de l'étudiant : intermédiaire. Donne une explication claire avec les termes du cours et un exemple. » |
| `avance` | « Niveau de l'étudiant : avancé. Réponds de façon précise et technique, sans définitions de base, en reliant les notions entre elles. » |

La consigne de niveau est placée **en dernier**, après la règle qui rappelle que les règles précédentes
priment : une analogie pour débutant ne doit pas faire sortir du cours.

### 6.3 Message utilisateur (`build_user_prompt`)

```text
Extraits du cours :
[p.{page}] {texte du passage}
…

Échanges précédents :            ← seulement s'il y a un historique
Étudiant : {question précédente}
Tuteur : {réponse précédente, tronquée à 600 caractères}

Question de l'étudiant : {question}

Rappel : les informations personnelles ont été masquées ([EMAIL], [NUMÉRO]). Ignore-les et réponds à la partie de la question qui concerne le cours.
```

Variables : passages retrouvés dans Qdrant (`TOP_K = 3`, filtrés par `user_id` et éventuellement par cours,
puis seulement ceux à moins de 0.03 du meilleur score), 3 derniers échanges au plus, question.

Protections :
- `mask_pii` sur **tout** le message utilisateur et sur chaque ligne de l'historique ;
- la question est journalisée masquée ;
- détection du refus : si la réponse contient la phrase `NOT_FOUND`, aucune source n'est renvoyée
  (`answered = False`) ; côté agent, seule la phrase de refus est gardée (le modèle la complète parfois) ;
- côté frontend, les `[p.X]` absentes des sources sont signalées.

---

## 7. Générateur d'examens (phase 4)

Fichiers : `app/phase4_exam/generator.py` (prompts) et `app/phase4_exam/schemas.py` (validateurs).
Une question est générée **par appel**, ancrée sur un passage différent du cours, puis vérifiée par un
appel séparé.

### 7.1 Prompt système de génération (`SYSTEM_PROMPT`)

```text
Tu es un enseignant qui rédige des sujets d'examen à partir d'un cours. Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour.
```

### 7.2 Message utilisateur (`build_prompt`)

```text
Cours (chaque passage commence par sa page) :
[page {page}] {texte}

{consignes propres au type de question}
- Questions en français, {indice de difficulté}.
{règles communes}
- Ne pose pas une question déjà posée :
- {10 dernières questions déjà posées}

Format attendu :
{exemple JSON du type}
```

Variables : passage(s) du cours, type de question, difficulté, questions déjà posées, vrai ou faux voulu
(alternance pour équilibrer les Vrai/Faux). Tout le message passe par `mask_pii`.

Indices de difficulté (`DIFFICULTY_HINTS`) :

| Difficulté | Texte |
|---|---|
| facile | niveau facile : définitions et reconnaissance directe d'une notion du cours |
| moyen | niveau moyen : compréhension, en reliant deux notions du cours |
| difficile | niveau difficile : application et analyse, avec des pièges proches de la bonne réponse |

Règles communes (`COMMON_RULES`) :

```text
- Chaque question porte sur une information précise présente dans le cours ci-dessus.
- Utilise uniquement les exemples cités dans le cours : n'en invente aucun.
- "page" est le numéro de la page d'où vient l'information.
- N'utilise jamais les mots « extraits » ou « contenu » : écris « selon le cours » si nécessaire.
- Rédige TOUT en français, y compris les réponses attendues et les corrections : traduis le cours s'il est en anglais.
- Une question ne contient jamais sa propre réponse (elle doit vraiment interroger l'étudiant).
- Jamais de question « combien », jamais de négation (« ne … pas »), jamais deux questions en une seule.
- Écris un JSON compact, sans espaces ni retours à la ligne inutiles.
```

Plusieurs interdictions répondent à des défauts constatés pendant le développement et listés dans
`docs/models.md` §7 (négations, questions « combien », choix « Tous les… », texte resté en anglais) ; elles
sont doublées par les validateurs Pydantic (§7.5), car un modèle de 7 milliards ne les respecte pas toujours.

### 7.3 Consignes par type de question (`TYPE_SPECS`)

| Type | Passages | `max_tokens` | Consignes (résumé fidèle) | Format |
|---|---|---|---|---|
| `qcm` | 1 | 500 | 1 question affirmative (jamais « lequel n'est PAS ») ; une seule bonne réponse, les 3 autres clairement fausses selon le cours ; aucun autre élément d'une liste du cours comme mauvaise réponse ; interdits : « Tous les éléments… », « Toutes les réponses », « Aucune de ces réponses » ; 4 choix courts, comparables, distincts ; mauvaises réponses plausibles et du même domaine ; `answer` = A à D ; `explanation` en une phrase. | `{"items":[{"question","choices":[4],"answer","explanation","page"}]}` |
| `vrai_faux` | 1 | 300 | 1 affirmation tirée du passage, **{truth}** = « VRAIE selon le cours » ou « FAUSSE : elle modifie un seul détail précis du cours » ; une fausse reste plausible ; `correction` en une phrase (version correcte si fausse). | `{"items":[{"statement","answer":bool,"correction","page"}]}` |
| `courte` | 1 | 300 | 1 question sur UNE notion (définition, signification, rôle, exemple) ; réponse en 1 ou 2 phrases, clairement dans le cours ; `expected_answer` rédigée comme un corrigé. | `{"items":[{"question","expected_answer","page"}]}` |
| `ouverte` | 3 | 600 | 1 seule question de réflexion cohérente (ex. comparer deux notions), sans réponse ni explication ; relie plusieurs notions ; `expected_points` = **exactement 4** éléments (1 point chacun), tirés du cours, sans répéter la question. | `{"items":[{"question","expected_points":[4],"page"}]}` |

Appel : `chat(SYSTEM_PROMPT, prompt, max_tokens=…, temperature=0.5, json_schema=<Batch>.model_json_schema())`.
Le prompt Vrai/Faux impose **vrai ou faux** (`want_true` alterne) pour équilibrer la partie, au lieu de
laisser le modèle choisir.

### 7.4 Prompts de vérification (LLM juge)

Prompt système commun (`VERIFY_SYSTEM_PROMPT`) :

```text
Tu es un étudiant rigoureux qui répond uniquement à partir du cours fourni. Tu réponds UNIQUEMENT avec un objet JSON valide.
```

| Fonction | Message utilisateur | Schéma | `max_tokens` | Décision |
|---|---|---|---|---|
| `verify_mcq` | « Cours : … QCM : Q1. … A. … D. … Pour chacune des N questions, dans l'ordre, donne la lettre de la seule bonne réponse selon le cours. Format : {"answers":["A","C"]} » | `LetterAnswers` | 100 | garde la question si la lettre trouvée = corrigé |
| `verify_true_false` | « Cours : … Affirmations : A1. … Pour chacune des N affirmations, dans l'ordre, réponds true si elle est vraie selon le cours, false sinon. Format : {"answers":[true,false]} » | `BoolAnswers` | 60 | garde si vrai/faux trouvé = corrigé |
| `verify_written` (courte, ouverte) | « Cours : … Question : … Réponse attendue : … La réponse attendue est-elle correcte selon le cours ET répond-elle exactement à la question posée ? Format : {"answers":[true]} ou {"answers":[false]} » | `BoolAnswers` | 20 | garde si `true` |

Toutes à température **0**, message passé par `mask_pii`. Technique : pour les QCM et les V/F, le vérificateur joue
l'**étudiant** et répond **sans voir le corrigé** ; le code compare ensuite sa réponse au corrigé. Il ne
peut donc pas se contenter de confirmer le corrigé qu'on lui montre. Les fonctions acceptent une
liste, mais le générateur leur passe **une question à la fois** (`candidates[:1]`). Si la vérification échoue
(erreur LLM, JSON invalide, nombre de réponses différent), la question est **gardée sans contrôle** et
l'événement est compté (`verifications_impossibles`) ; une réponse en trop est ignorée.

### 7.5 Validateurs Pydantic (`schemas.py`)

- **Toutes les questions** : pas de « combien », pas deux questions en une (`et quel…`, deux `?`),
  première lettre en majuscule, antislashs mal échappés restaurés.
- **QCM** : question de 10 à 250 caractères terminée par `?` ou `:`, sans liste ni négation ; 4 choix
  non vides, distincts, sans préfixe « A. », ni simple lettre, ni oui/non, ni « tous les / aucune de » ;
  réponse normalisée (« b. » → « B ») ; explication en français.
- **Vrai/Faux** : affirmation de 15 à 250 caractères, sans liste (`:`/`•`) ni négation ; correction en français.
- **Réponse courte** : réponse attendue en français, jamais « Oui »/« Non ».
- **Ouverte** : 20 à 300 caractères, un seul `?` ; 4 éléments de réponse d'au moins 5 caractères, en
  français ; refus si 2 éléments ou plus répètent à 80 % les mots de la question.
- **Français** (`check_french`) : refus à partir de 2 mots anglais fréquents (`the`, `of`, `and`…) ou d'un
  caractère cyrillique, arabe ou chinois.
- **Page** : si la page citée n'est pas parmi celles du passage, elle est remplacée par la plus proche.
- Les choix des QCM sont **mélangés** après validation (la bonne réponse change de position).

---

## 8. Flashcards (phase 7)

Fichiers : `app/phase7_flashcards/generator.py` et `app/phase7_flashcards/schemas.py`.
Deux étapes : repérer les concepts clés, puis une carte par concept (RAG sur les passages du cours).

Prompt système de génération :

```text
Tu es un enseignant qui prépare des fiches de révision à partir d'un cours. Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour.
```

### 8.1 Extraction des concepts (`extract_concepts`)

```text
Cours (chaque passage commence par sa page) :
{3 passages consécutifs}

Liste au plus 3 notions clés de ce passage qu'un étudiant doit retenir pour l'examen.
- "name" : le nom court de la notion, en français (2 à 6 mots), par exemple « Connecteur » ou « Développement natif ».
- "importance" : 3 = notion centrale (définition, principe), 2 = notion utile, 1 = détail.
- Ignore les titres, plans de cours, logos, noms de personnes et informations administratives.
- Si le passage ne contient aucune notion utile, renvoie une seule notion d'importance 1.

Format attendu :
{"items":[{"name":"...","importance":3}]}
```

Appel : température **0.2**, `max_tokens` **200**, `json_schema=ConceptBatch`. Seuls les blocs utiles sont
lus (environ `ceil(cartes × 2,5 / 3) + 2` blocs, répartis sur le cours) : la durée dépend du nombre de cartes
demandées, pas de la taille du cours. Validateur `Concept` : nom de 2 à 80 caractères, importance 1, 2 ou 3.
Les concepts en double (même nom, ou similarité ≥ 0.97) sont fusionnés, les plus importants sont gardés.

### 8.2 Rédaction d'une carte (`make_card`)

```text
Cours (chaque passage commence par sa page) :
{2 passages les plus proches du concept}

Rédige 1 flashcard de révision sur la notion « {concept} », à partir du cours ci-dessus.
- "front" : une seule question courte et précise sur « {concept} », qui se termine par « ? ».
- "back" explique vraiment la notion (définition, rôle ou exemple) : il ne reformule jamais la question.
- "back" : la réponse en 1 ou 2 phrases courtes (moins de 250 caractères), tirée du cours,
  compréhensible sans relire la question, sans numéro de page.
- "page" : le numéro de la page d'où vient la réponse.
- Rédige TOUT en français : traduis le cours s'il est en anglais.
- Jamais de question oui/non, jamais de question « combien ».
- N'invente rien : utilise uniquement ce que dit le cours.
- Si le passage est illisible ou incomplet, ne devine pas : choisis une autre information claire du cours.

Format attendu :
{"items":[{"concept":"{concept}","front":"...?","back":"...","page":12}]}
```

Appel : température **0.4**, puis **0.7** pour la seconde tentative ; `max_tokens` **250** ;
`json_schema=FlashcardBatch`. Le concept est imposé par le code, pas par le modèle.

Validateur `Flashcard` : recto de 8 à 150 caractères terminé par un seul `?` ; verso de 5 à 250
caractères, sans oui/non, sans numéro de page, sans hésitation (« probablement », « peut-être »,
« le cours ne »…), terminé par une ponctuation (réponse non coupée), en français, et apportant au moins
2 mots absents du recto.

### 8.3 Vérification d'une carte (`verify_card`)

Système :

```text
Tu es un enseignant rigoureux qui vérifie des fiches de révision à partir du cours fourni. Tu réponds UNIQUEMENT avec un objet JSON valide.
```

Utilisateur :

```text
Cours : {passages}
Question : {front}
Réponse : {back}

Cette réponse contient-elle une ERREUR, c'est-à-dire une information qui contredit le cours ou qui ne s'y trouve pas ? Réponds true seulement si tu es sûr qu'il y a une erreur. Format : {"answers":[true]} ou {"answers":[false]}
```

Température **0**, `max_tokens` **20**, `json_schema=BoolAnswers`. Carte écartée si `true`. La question est
posée « à l'envers » (y a-t-il une ERREUR ?) et le rejet exige une certitude (« seulement si tu es sûr ») :
une carte n'est écartée que pour une contradiction ou une information absente du cours, pas pour une
reformulation. Cette formulation répond au « juge trop strict » du journal des bugs (`docs/qualite-ia.md`).
Ensuite, une carte trop
proche d'une carte déjà gardée (similarité ≥ 0.92) est écartée.

---

## 9. Résumés (phase 9)

Fichiers : `app/phase9_summaries/generator.py` et `app/phase9_summaries/schemas.py`.

Prompt système (tous les résumés) :

```text
Tu es un enseignant qui rédige des fiches de révision en français, uniquement à partir du cours fourni. Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour.
```

Règles communes (`COMMON_RULES`) :

```text
- Rédige TOUT en français, même si le cours est en anglais (traduis-le).
- N'utilise que ce que dit le cours ci-dessus : n'invente rien, aucune connaissance extérieure.
- Ignore les noms de personnes, les dates de cours, les logos et les informations administratives.
- Chaque puce est une phrase complète qui se termine par la page d'où vient l'information, sous la forme [p.X],
  avec X parmi : {pages}.
```

La liste des **pages autorisées** est donnée dans le prompt **et** vérifiée par le validateur. Tous les
appels passent par `ask_structured` : `json_schema` du modèle Pydantic, validation avec le contexte des pages
autorisées, seconde tentative si rejet (température **0.3** puis **0.5**).

### 9.1 Étape « map » : résumé d'une section (`summarize_section`)

```text
Cours (chaque passage commence par sa page) :
{6 passages consécutifs}

Résume cette partie du cours pour un étudiant qui révise.
- "title" : un titre court (3 à 8 mots) qui dit de quoi parle cette partie.
- Le titre doit être différent de ceux des parties précédentes : {titres déjà utilisés}.   ← si besoin
- "bullets" : 3 à 5 puces avec les idées essentielles, dans l'ordre du cours.
{COMMON_RULES}

Format attendu :
{"title":"...","bullets":["... [p.{première page}]","...","..."]}
```

`max_tokens` **600**, schéma `SectionDraft` : titre de 3 à 90 caractères en français ; 3 à 5 puces.

### 9.2 Étape « reduce » : vue d'ensemble (`write_overview`)

```text
Résumés des parties d'un cours, dans l'ordre :
{titre de chaque section + ses puces}

Rédige une vue d'ensemble du cours entier en 4 à 6 phrases, en français : le sujet du cours, les grandes
notions et la façon dont elles s'enchaînent. N'utilise que les résumés ci-dessus, n'invente rien.

Format attendu :
{"overview":"..."}
```

`max_tokens` **500**, schéma `OverviewDraft` : 80 à 1500 caractères, 3 à 7 phrases, en français.
Repli **sans invention** après deux rejets : « Ce cours aborde les parties suivantes : {titres}. »
Le map-reduce permet de résumer **tout** le cours sans dépasser le contexte : chaque section tient en
1 233 jetons environ (section 4), la vue d'ensemble ne relit que les puces (286 jetons mesurés pour une
section).

### 9.3 Explication d'un thème (`explain_topic`)

```text
Cours (chaque passage commence par sa page) :
{6 passages retrouvés par recherche sémantique, triés par page}

Thème demandé par l'étudiant : « {topic} »

Si les passages ci-dessus ne parlent PAS de ce thème, réponds exactement {"found":false}.
Sinon, explique ce thème de façon structurée :
- "found" : true.
- "introduction" : 1 à 2 phrases qui présentent le thème.
- "parts" : 1 à 4 parties, chacune avec un titre court et 2 à 5 puces.
- Adapte l'explication au niveau de l'étudiant. {consigne de niveau}     ← si le niveau est connu
{COMMON_RULES}

Format attendu :
{"found":true,"introduction":"...","parts":[{"title":"...","bullets":["... [p.{première page}]","..."]}]}
```

`max_tokens` **900**, schéma `TopicDraft`. Variables : thème (2 à 200 caractères, validé par
`SummaryRequest`), niveau de l'étudiant, pages autorisées. Le champ `found` donne au modèle une sortie
explicite quand le thème est hors cours, au lieu d'inventer.

### 9.4 Validateur des puces (`check_bullet`)

Chaque puce : au moins 10 caractères hors référence, en français, **au moins une référence `[p.X]`**, et
**toutes les pages citées font partie des passages fournis**. Sinon la sortie est rejetée (seconde
tentative, puis section ignorée).

---

## 10. Agent Study Companion (phase 6)

Fichiers : `app/phase6_agent/graph.py` (prompts) et `app/phase6_agent/tools.py` (outils).
Client : `ChatOpenAI` (LangChain), température **0**, même `LLM_BASE_URL` / `LLM_MODEL` / `LLM_TIMEOUT`,
`max_retries = max(1, LLM_RATE_LIMIT_RETRIES)` = 4, `max_tokens` non fixé.

### 10.1 Prompt système de l'agent (`SYSTEM_PROMPT`)

```text
Tu es « Study Companion », l'assistant d'étude d'un étudiant. Tu réponds toujours en français.
Tu disposes d'outils ; choisis celui qui correspond à la demande :
- ask_course : question précise sur le contenu d'un cours (définition, explication, comparaison, exemple).
- summarize : résumé d'un cours entier (sans topic) — aussi « idées principales », « points clés », « l'essentiel »,
  « synthèse » ou « récapitulatif » du cours —, ou explication structurée d'un thème (topic).
- generate_quiz : quiz QCM pour s'entraîner ou se tester (count 5 ou 10, difficulty facile, moyen ou difficile).
- generate_flashcards : paquet de flashcards (cartes de révision).
- get_progress : progrès, statistiques, niveau, points faibles de l'étudiant.
Règles :
- Salutation, remerciement ou question sur l'application elle-même : réponds directement en une ou deux phrases,
  sans outil.
- Toute demande sur le contenu d'un cours passe par un outil : n'invente jamais de contenu de cours.
- Au plus 3 outils par message.
- N'indique un cours (course) que si l'étudiant le nomme ; sinon laisse-le vide.
- Tutoie l'étudiant. N'utilise jamais son nom, son email ou une autre information personnelle.
{courses}
{level}
```

Variables : `courses` = « Cours de l'étudiant : « A », « B ». Cours sélectionné dans la page : « A ». »
(chaque nom passé par `mask_pii`) ; `level` = consigne de niveau du tuteur. Les synonymes de « résumé »
(« idées principales », « points clés »…) visent le défaut constaté à l'évaluation : « Résume les idées
principales de ce cours » partait vers `ask_course` ; le garde-fou `COURSE_SUMMARY` corrige les cas restants
(`docs/evaluation.md` §2.5).

Après l'exécution d'un outil, on ajoute `AFTER_TOOLS_RULE` :

```text
Les outils ont été exécutés et leur résultat est affiché à l'étudiant (quiz, résumé, flashcards, progression).
Écris maintenant ta réponse finale : 1 à 3 phrases courtes et chaleureuses, en tutoyant l'étudiant, adaptées
à son niveau, qui présentent ce qui a été préparé. Ne recopie pas le contenu et n'invente rien. N'appelle un autre
outil que si la demande de l'étudiant n'est pas encore satisfaite.
```

Messages envoyés : les 6 derniers messages de la conversation (300 caractères au plus chacun) puis le
message de l'étudiant, **tous passés par `mask_pii`**.

### 10.2 Description des outils (*function calling*)

Générée par `openai_tools()` à partir des modèles Pydantic d'arguments (docstring = description de l'outil,
`description` des champs = description des paramètres) :

| Outil | Description envoyée au LLM | Arguments |
|---|---|---|
| `ask_course` | Répondre à une question sur le contenu d'un cours (définition, explication, comparaison, exemple). | `question` (« La question de l'étudiant, complète et autonome. »), `course` |
| `summarize` | Résumer un cours entier, ou expliquer de façon structurée un thème précis du cours (topic). | `course`, `topic` (« Vide pour résumer tout le cours. ») |
| `generate_quiz` | Générer un quiz QCM interactif pour s'entraîner sur un cours. | `course`, `count` (5 ou 10), `difficulty` |
| `generate_flashcards` | Générer un paquet de flashcards de révision sur un cours (enregistré dans « Mes paquets »). | `course`, `count` (10, 20 ou 30) |
| `get_progress` | Afficher la progression de l'étudiant : niveau, statistiques, points faibles. | aucun |

Protections sur les appels d'outil :
- arguments **validés par Pydantic** (`validate_call`) : outil inconnu ou arguments invalides → appel
  ignoré, puis repli par classification ; valeurs approchées corrigées (`count: 7` → 5, `hard` → `difficile`,
  `"null"` → vide) ;
- l'**identité de l'étudiant n'est jamais un argument** : `user_id`, niveau et liste des cours viennent du
  jeton JWT (`AgentContext`, hors du graphe) ;
- un cours proposé par le LLM n'est retenu que s'il existe **et** si l'étudiant l'a nommé ; le cours
  sélectionné dans la page prime toujours ;
- 3 outils au plus par message, doublons ignorés, `recursion_limit = 15` ;
- garde-fou : une demande de résumé du cours entier routée vers `ask_course` est corrigée en `summarize`
  (expression régulière `COURSE_SUMMARY`) ;
- réponse finale coupée avant toute liste et limitée à 3 phrases / 350 caractères (`short_reply`) ; un
  texte qui ressemble à un appel d'outil en JSON est ignoré ; la réponse du tuteur RAG n'est jamais
  reformulée.

### 10.3 Classification de repli (`classify_intent`)

Utilisée quand le modèle n'appelle aucun outil, ou seulement des outils invalides.

Système :

```text
Tu classes la demande d'un étudiant pour choisir l'outil de son assistant d'étude. Tu réponds UNIQUEMENT avec un objet JSON valide.
```

Utilisateur :

```text
Outils possibles :
- ask_course : question précise sur le contenu d'un cours (définition, explication, exemple, comparaison).
- summarize : résumé d'un cours entier (idées principales, points clés, essentiel, synthèse, récapitulatif du cours),
  ou explication structurée d'un thème (theme).
- generate_quiz : quiz, QCM, s'entraîner, se tester (nombre 5 ou 10, difficulte facile, moyen ou difficile).
- generate_flashcards : flashcards, fiches ou cartes de révision.
- get_progress : progrès, statistiques, niveau, points faibles.
- aucun : salutation, remerciement, question sur l'application elle-même.
Cours de l'étudiant : {cours}
Demande précédente : « {demande précédente, 300 caractères} »     ← si elle existe
Demande de l'étudiant : « {message} »

Format attendu : {"outil":"...","cours":null,"theme":null,"nombre":null,"difficulte":null}
(« cours » seulement si l'étudiant nomme un de ses cours.)
```

Appel : température **0**, `max_tokens` **150**, `json_schema=IntentDecision` (l'outil est un `Literal`
parmi 6 valeurs). Prompt entier passé par `mask_pii`. Si la sortie est invalide : `aucun` (message d'aide
par défaut). Technique : le même choix posé en **sortie structurée** plutôt qu'en *tool calling*, pour les
cas où le modèle n'appelle pas d'outil ; mesuré à 289 jetons d'entrée contre 994 pour le *tool calling*.

### 10.4 Étiquetage des notions d'un quiz (`label_concepts`)

Fichier : `app/phase6_agent/tools.py`. Sert à regrouper les erreurs de quiz en points faibles.

```text
Questions d'un quiz de révision :
1. {question}
…

Pour chaque question, dans l'ordre, donne la notion du cours qu'elle teste, en français, en 2 à 6 mots
(par exemple « Pooling » ou « Fonction d'activation »).
Format attendu : {"concepts":["...","..."]}
```

Système : « Tu réponds UNIQUEMENT avec un objet JSON valide. » ; température **0**, `max_tokens` **300**,
`json_schema=CONCEPTS_SCHEMA`. Repli : le début de chaque question si le LLM échoue ou ne renvoie pas une
notion par question.

---

## 11. Prompts du fine-tuning (phase 4 bis, hors application)

Ces prompts ne servent qu'aux scripts hors ligne de `app/phase4_finetuning/`.

| Prompt | Fichier | Rôle | Réglages |
|---|---|---|---|
| `QUESTION_SYSTEM` (« Tu es un enseignant qui prépare des questions d'étudiants à partir d'un cours. Tu réponds UNIQUEMENT avec un objet JSON valide. ») + « Passage d'un cours (page X) … Écris {type de question} qu'un étudiant pourrait poser sur ce passage … » | `dataset.py` | générer une question (définition, rôle, comparaison, exemple, pourquoi) par passage | température 0.7 (`QUESTION_TEMPERATURE`), `max_tokens` 120, `json_schema` `{"question"}`, `mask_pii` |
| Prompt complet du tuteur (`build_system_prompt(level)` + `build_user_prompt`) | `dataset.py` | réponse « idéale » de l'enseignant (qwen2.5:7b) pour chaque niveau | température 0.3 (`ANSWER_TEMPERATURE`, celle du tuteur), `max_tokens` 700 ; filtres : hors cours, anglais, longueur par niveau, référence `[p.X]`, hésitation |
| `FINETUNE_SYSTEM` = `SYSTEM_PROMPT` + « Adapte ton explication au niveau de l'étudiant indiqué dans son message. » | `dataset.py` | prompt système des exemples d'entraînement ; le niveau est donné en tête du message (« Niveau de l'étudiant : débutant. ») au lieu de la consigne détaillée, que le modèle doit apprendre | — |
| `JUDGE_SYSTEM` (« Tu es un enseignant exigeant qui évalue la réponse d'un tuteur à un étudiant. … ») + `judge_prompt` | `evaluate.py` | juge LLM base vs affiné : notes de 1 à 5 sur le niveau, la fidélité et la clarté, avec plafond à 2 pour une réponse hors niveau ou infidèle ; **justification demandée avant les notes** | température 0, `max_tokens` 250, `json_schema` (entiers 1 à 5), `mask_pii` |
| Génération du modèle évalué | `hf_local.py`, notebook | même prompt que le tuteur | température 0.3, `top_p` 0.9, `repetition_penalty` 1.05, 512 jetons au plus (évaluation) |

---

## 12. Comparaison des modèles

### 12.1 Modèles utilisés

| Modèle | Où | Paramètres, quantification | Contexte | Rôle dans le projet |
|---|---|---|---|---|
| `qwen2.5:7b` | Ollama, local | 7,6 milliards, Q4_K_M (4,7 Go) | 4 096 (valeur constatée par `ollama ps`) | LLM de référence du benchmark ; enseignant du jeu de fine-tuning ; juge |
| `qwen2.5-7b-gpu` | Ollama, local (`Modelfile` à la racine) | mêmes poids que `qwen2.5:7b`, `num_gpu 99` | 4 096 (`num_ctx`) | LLM de l'application en développement |
| `qwen/qwen3.8-27b` | Groq (API) | 27 milliards (modèle « preview ») | — | LLM du déploiement Docker / Hugging Face Spaces |
| Qwen2.5-1.5B-Instruct + LoRA `Alinajjaa/study-tutor-qwen2.5-1.5b-lora` | `transformers`, local en 4 bits (`LLM_PROVIDER=hf-local`) | 1,5 milliard, nf4 | 1 024 jetons à l'entraînement | démonstration : style du tuteur (texte libre seulement) ; désactivé par défaut |

### 12.2 Mesures comparées

Un tiret signifie que la mesure n'existe pas pour ce modèle. Les colonnes qwen2.5:7b et qwen2.5-7b-gpu
viennent du même matériel (RTX 4050, 6 Go de VRAM), du même cours (Chapter1_Part_1), des mêmes jeux de test
et du même script de benchmark.

| Mesure | qwen2.5:7b | qwen2.5-7b-gpu | qwen3.8-27b (Groq) | Qwen2.5-1.5B + LoRA |
|---|---|---|---|---|
| Runs du benchmark | 14/10 : 3 examens, 3 paquets, 1 résumé, 14 questions | 18/10 : 1 examen, 1 paquet, 1 résumé, 14 questions | 14/10 : 3 examens, 3 paquets, 1 résumé, 14 questions | 31 réponses de test |
| Répartition CPU / GPU | 18 % / 82 % (équipe) ; 4,23 Go sur 5,03 Go en VRAM (`ollama ps`, 19/10) | 100 % GPU (équipe) | serveur Groq | ≈ 1,5 Go de VRAM en 4 bits (`docs/models.md`) |
| Débit de génération | 24,5 tok/s (équipe) ; 23,0 tok/s (section 4) | 37,8 tok/s (équipe) ; 35,6 tok/s (section 4) | 0,3 à 1,7 s par appel (`docs/deploiement.md`) | — |
| Examen complet : durée | 158 s (σ 15) | **102 s** | 151 s (σ 48), limité par le débit de l'offre gratuite | — (pas de JSON) |
| Examen : points / questions / `taux_reussite` | 20/20 / 15, 18, 15 / 0,982 | 20/20 / 15 / 1,000 | 20/20 / 15 / 1,000 | — |
| Examen : appels au LLM / durée par appel | 48,7 / 3,2 s | 54 / **1,9 s** | 41,0 / — | — |
| Examen : rejets validation / vérification / doublon | 17,9 % / 5,4 % / 16,4 % | 20 % / 10 % / 20 % | 5,1 % / 22,8 % / 0 % | — |
| Flashcards (10) : durée | 129 s (σ 23) | **62 s** | 122 s (σ 3) | — |
| Flashcards : cartes / appels au LLM / durée par appel | 10/10 / 45,0 / 2,9 s | 10/10 / 38 / **1,6 s** | 10/10 / 35,3 / — | — |
| Flashcards : rejets validation / vérification / doublon | 29,7 % / 12,6 % / 8,6 % | 18,8 % / 6,3 % / 12,5 % | 7,1 % / 0 % / 19,6 % | — |
| Résumé du cours entier : durée / appels | 42 s / 6 | **28 s** / 6 | 67 s / 7 | — |
| Résumé : sections, puces, pages valides | 5, 22, 100 % | 5, 22, 100 % | 5, 22, 100 % | — |
| Tuteur : durée moyenne par question (14) | 6,1 s (σ 5,2) | **4,0 s** (σ 5,5) | 3,6 s | — |
| Tuteur : `hit_3` / réponse trouvée / refus hors cours | 100 % / 100 % / 100 % | 100 % / 100 % / 100 % | 100 % / 100 % / 100 % | — |
| Agent : `taux_bon_outil` / durée du choix | 100 % / 1,8 s | — (non repassé) | 100 % / 9,2 s (attentes 429) | — |
| Citations `[p.X]` valides | — | — | — | 97 % (base sans LoRA : 3 %) |
| Note moyenne du juge (1 à 5) | — | — | — | 4,13 (base : 3,99) |
| Coût | nul (local) | nul (local) | offre gratuite : 30 requêtes et 8 000 jetons par minute | nul (entraînement sur Colab gratuit) |
| Confidentialité | cours et questions restent sur la machine | idem | envoyés à Groq (après `mask_pii`) | idem local |

Sources :

- **qwen2.5:7b** : runs MLflow `benchmark` du 14/10 (expériences `exam`, `flashcards`, `summary`, `tutor`),
  résumés dans `docs/evaluation.md` §2.1 à §2.5 ; CSV `Chapter1_Part_1_2026-10-14_0300.csv` (tuteur, jeu complet
  de 14 questions) et `Chapter1_Part_1_2026-10-14_1214.csv` (résumé). Les examens et flashcards de qwen2.5:7b
  n'ont pas de CSV dans `results/` : leurs valeurs viennent des runs MLflow (examens 150,1 s, 148,7 s, 176,1 s ;
  flashcards 116,4 s, 155,3 s, 115,0 s).
- **qwen2.5-7b-gpu** : `backend/app/phase5_evaluation/results/Chapter1_Part_1_2026-10-18_1729.csv` (runs
  MLflow du 18/10, 17 h 22 – 17 h 29). Deux runs du même benchmark lancés juste avant (17 h 22, statut
  `echec`, erreur `ResponseHandlingException`, 0 passage lu : Qdrant injoignable) sont exclus.
- **Groq** : `Chapter1_Part_1_2026-10-14_1735.csv`, `Chapter1_Part_1_2026-10-14_1750.csv`,
  `agent_eval_20261014_173341.csv` (`docs/evaluation.md` §2.8).
- **LoRA** : `docs/evaluation.md` §2.6.
- **Débit et répartition CPU / GPU** : mesures de l'équipe (`ollama ps`, sortie *verbose* d'Ollama),
  recoupées par la section 4.

### 12.3 Optimisation GPU d'Ollama (configuration du serveur)

Réglages : `Modelfile` à la racine (`num_gpu 99`, `num_ctx 4096`) et variables d'environnement du serveur
Ollama (`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=-1`). Aucun changement de
code : seul `LLM_MODEL=qwen2.5-7b-gpu` change dans `backend/.env`.

| Mesure | Avant : qwen2.5:7b (14/10) | Après : qwen2.5-7b-gpu (18/10) | Gain |
|---|---|---|---|
| Débit de génération (*eval rate*, équipe) | 24,5 tok/s | 37,8 tok/s | × 1,54 |
| Répartition CPU / GPU (équipe) | 18 % / 82 % | 100 % GPU | — |
| Examen complet (15 questions, 20/20) | 158 s (moyenne de 3 runs) | 101,5 s | − 36 % |
| Examen : durée par appel au LLM | 3,24 s (158 / 48,7) | 1,88 s (101,5 / 54) | − 42 % |
| Flashcards (10 cartes sur 10) | 129 s (moyenne de 3 runs) | 61,7 s | − 52 % |
| Flashcards : durée par appel au LLM | 2,87 s (129 / 45) | 1,62 s (61,7 / 38) | − 43 % |
| Résumé du cours entier (6 appels) | 42,2 s | 27,8 s | − 34 % |
| Tuteur, moyenne sur 14 questions | 6,08 s | 4,03 s | − 34 % |
| Tuteur : `hit_3`, refus hors cours | 100 %, 100 % | 100 %, 100 % | inchangé |

Lecture :

- **Le gain par appel est stable** (− 34 % à − 43 % selon la génération), ce qui correspond au débit
  × 1,54 : l'accélération vient du modèle, pas d'un changement de code.
- **L'examen gagne moins que les flashcards** parce que le run GPU a fait **plus d'appels** (54 contre 48,7
  en moyenne) : ses rejets ont été un peu plus nombreux (validation 20 %, vérification 10 %, doublons 20 %).
  Ces rejets varient d'un run à l'autre (écart-type de 12,5 points sur les doublons pour qwen2.5:7b) ; le
  paquet de flashcards a, à l'inverse, eu moins de rejets (38 appels contre 45).
- **La qualité ne change pas** : mêmes points, mêmes cartes, mêmes résumés (22 puces, 100 % de pages
  valides), même `hit_3` et même refus hors cours. Le score de recherche maximal moyen du tuteur est identique
  (0,8315) : la recherche Qdrant ne dépend pas du LLM.
- **Écart-type du tuteur** (σ 5,5 s) : le premier appel (22,6 s) inclut le chargement du modèle ; les 13
  suivants durent de 0,4 à 4,4 s.
- **Limite** : un seul run GPU par génération, contre trois pour qwen2.5:7b ; l'écart-type de la variante GPU
  n'est pas mesuré.

Pourquoi ces réglages :

- **`num_gpu 99`** : par défaut, Ollama estime la mémoire libre et laisse une partie des couches sur le CPU
  (82 % sur le GPU ici) ; chaque jeton traverse alors le CPU, beaucoup plus lent. Forcer toutes les couches sur
  le GPU suppose que le reste tienne en mémoire, d'où les deux réglages suivants.
- **`num_ctx 4096`** : le plus long prompt mesuré fait 1 233 jetons, plus 600 de sortie : 4 096 suffit, et la
  taille du cache KV est proportionnelle au contexte.
- **`OLLAMA_FLASH_ATTENTION=1` et `OLLAMA_KV_CACHE_TYPE=q8_0`** : cache KV en 8 bits au lieu de 16, environ deux
  fois moins de VRAM pour le contexte ; la quantification du cache exige la *flash attention*.
- **`OLLAMA_KEEP_ALIVE=-1`** : le modèle reste chargé. Sans ce réglage, le premier appel après 5 minutes
  d'inactivité recharge le modèle (premier appel du tuteur : 22,6 s dans le benchmark du 18/10, 13,9 s dans
  la section 4, contre 4,5 s pour l'appel suivant).

Contrôle indépendant (section 4, 19/10/2026) : 23,0 → 35,6 tok/s en moyenne sur 16 et 17 appels réels, soit
× 1,55, cohérent avec le × 1,54 de l'équipe.

### 12.4 Choix retenus

- **Développement : `qwen2.5-7b-gpu`.** Le plus gros modèle qui tient dans 6 Go de VRAM (un 14 milliards ne
  tient pas), bon en français, avec *tool calling* et `json_schema` dans Ollama ; ni coût ni quota (l'API
  d'inférence de Hugging Face renvoyait des erreurs 402 une fois le quota gratuit épuisé) ; les cours ne
  quittent pas la machine.
- **Déploiement : `qwen/qwen3.8-27b` sur Groq.** Pas de GPU sur l'hébergement ; qualité équivalente sur le
  benchmark, rejets de validation divisés par 3 à 4 ; seul modèle accessible avec la clé du projet qui accepte
  tous les schémas JSON (les gpt-oss échouent, les Llama ne sont pas accessibles).
- **Qwen2.5-1.5B + LoRA : démonstration seulement.** Le fine-tuning a appris le style (citations 3 % → 97 %),
  mais un modèle de 1,5 milliard raisonne moins bien, n'apporte aucun gain au niveau avancé et ne produit pas
  les sorties JSON des autres fonctionnalités.
