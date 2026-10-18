# Prompts du projet

Ce document recense **tous les prompts** envoyés au LLM par l'application (prompts système et prompts
utilisateur), avec pour chacun :

- le **fichier source** (chemins relatifs à `backend/`) ;
- le **rôle** du prompt ;
- les **variables injectées** ;
- les **protections** associées : masquage des données personnelles (`mask_pii`), sorties structurées
  (`json_schema`), validateurs Pydantic, vérifications et replis.

Tous les appels passent par `chat()` dans `app/phase1_llm/llm.py` (un message `system`, un message `user`),
sauf l'agent, qui passe par `ChatOpenAI` (LangChain) avec le même serveur et le même modèle.

## Protections communes

| Protection | Où | Effet |
|---|---|---|
| `mask_pii(text)` | `app/core/privacy.py` | Remplace les emails par `[EMAIL]` et les numéros de 8 à 14 chiffres (téléphone, CIN) par `[NUMÉRO]`. Appliqué à **chaque prompt utilisateur** avant l'envoi au LLM, et aux noms de cours et de concepts injectés dans les prompts système. |
| `json_schema` | `chat(..., json_schema=Model.model_json_schema())` | Sortie structurée : le serveur (Ollama, API compatible OpenAI) contraint la réponse à respecter le schéma JSON (`response_format: {"type": "json_schema"}`). |
| Validateurs Pydantic | `schemas.py` de chaque phase | Après le schéma, chaque élément est relu par un modèle Pydantic (longueurs, formats, règles métier). Un élément invalide est rejeté et compté (`reject("validation")`), jamais affiché. |
| Auto-vérification | examens, flashcards | Un second appel (température 0) relit la sortie avec le cours. Une sortie jugée fausse est écartée. |
| Doublons de sens | examens, flashcards | Similarité cosinus entre embeddings e5 : au-delà d'un seuil, la sortie est écartée. |
| Erreurs du LLM | `LLMError` | Timeout, serveur injoignable, clé absente ou invalide, quota, réponse vide → message clair en français et réponse HTTP 503. |

Le prompt système **ne contient jamais** l'email ni le nom de l'étudiant. Seuls son **niveau**
(débutant, intermédiaire, avancé), les **noms de ses cours** et les **noms de concepts** issus du cours y
figurent.

---

## 1. Tuteur RAG (phase 3)

Fichier : `app/phase3_rag/rag.py`. Appel : `chat(system, user_prompt)`, température **0.3**,
`max_tokens` **1024**, texte libre (markdown).

### 1.1 Prompt système de base (`SYSTEM_PROMPT`)

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

Variable injectée : `NOT_FOUND` (phrase de refus, constante).

### 1.2 Règles ajoutées selon le contexte (`build_system_prompt`)

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

Variables : `level` (colonne `users.level`), `concepts` (noms des points faibles, chacun passé par
`mask_pii`, calculés à partir des révisions de flashcards et des réponses aux quiz).

### 1.3 Prompt utilisateur (`build_user_prompt`)

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
- `mask_pii` sur **tout** le prompt utilisateur, et sur chaque ligne de l'historique ;
- la question est journalisée masquée (`logger.info(... mask_pii(question))`) ;
- détection du refus : si la réponse contient `NOT_FOUND`, aucune source n'est renvoyée (`answered = False`) ;
  côté agent, seule la phrase de refus est gardée (le modèle la complète parfois) ;
- pas de schéma JSON (texte libre) ; côté frontend, le markdown est converti par `marked` puis nettoyé par
  la sanitization d'Angular (`[innerHTML]`), et les `[p.X]` absentes des sources sont signalées.
- **streaming** (`/api/ask/stream`, `/api/companion/messages/stream`) : mêmes prompts, envoyés par
  `chat_stream()`. Les fragments sont affichés tels quels pendant l'écriture (texte brut, échappé) ; la réponse
  validée (refus détecté, sources, `[p.X]`) arrive dans l'événement final et remplace le brouillon.

---

## 2. Générateur d'examens (phase 4)

Fichiers : `app/phase4_exam/generator.py` (prompts) et `app/phase4_exam/schemas.py` (validateurs).
Une question est générée **par appel**, ancrée sur un passage différent du cours.

### 2.1 Prompt système de génération (`SYSTEM_PROMPT`)

```text
Tu es un enseignant qui rédige des sujets d'examen à partir d'un cours. Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour.
```

### 2.2 Prompt utilisateur (`build_prompt`)

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
(alternance pour équilibrer les Vrai/Faux).

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

### 2.3 Consignes par type de question (`TYPE_SPECS`)

| Type | Passages | `max_tokens` | Consignes (résumé fidèle) | Format |
|---|---|---|---|---|
| `qcm` | 1 | 500 | 1 question affirmative (jamais « lequel n'est PAS ») ; une seule bonne réponse, les 3 autres clairement fausses selon le cours ; aucun autre élément d'une liste du cours comme mauvaise réponse ; interdits : « Tous les éléments… », « Toutes les réponses », « Aucune de ces réponses » ; 4 choix courts, comparables, distincts et plausibles ; `answer` = A à D ; `explanation` en une phrase. | `{"items":[{"question","choices":[4],"answer","explanation","page"}]}` |
| `vrai_faux` | 1 | 300 | 1 affirmation tirée du passage, **{truth}** = « VRAIE selon le cours » ou « FAUSSE : elle modifie un seul détail précis du cours » ; une fausse reste plausible ; `correction` en une phrase (version correcte si fausse). | `{"items":[{"statement","answer":bool,"correction","page"}]}` |
| `courte` | 1 | 300 | 1 question sur UNE notion (définition, signification, rôle, exemple) ; réponse en 1 ou 2 phrases, clairement dans le cours ; `expected_answer` rédigée comme un corrigé. | `{"items":[{"question","expected_answer","page"}]}` |
| `ouverte` | 3 | 600 | 1 seule question de réflexion cohérente (ex. comparer deux notions), sans réponse ni explication ; relie plusieurs notions ; `expected_points` = **exactement 4** éléments (1 point chacun), tirés du cours, sans répéter la question. | `{"items":[{"question","expected_points":[4],"page"}]}` |

Appel : `chat(SYSTEM_PROMPT, prompt, max_tokens=…, temperature=0.5, json_schema=<Batch>.model_json_schema())`.

### 2.4 Prompts de vérification

Prompt système commun (`VERIFY_SYSTEM_PROMPT`) :

```text
Tu es un étudiant rigoureux qui répond uniquement à partir du cours fourni. Tu réponds UNIQUEMENT avec un objet JSON valide.
```

| Fonction | Prompt utilisateur | Schéma | `max_tokens` | Décision |
|---|---|---|---|---|
| `verify_mcq` | « Cours : … QCM : Q1. … A. … D. … Pour chacune des N questions, dans l'ordre, donne la lettre de la seule bonne réponse selon le cours. Format : {"answers":["A","C"]} » | `LetterAnswers` | 100 | garde la question si la lettre trouvée = corrigé |
| `verify_true_false` | « Cours : … Affirmations : A1. … Pour chacune des N affirmations, dans l'ordre, réponds true si elle est vraie selon le cours, false sinon. Format : {"answers":[true,false]} » | `BoolAnswers` | 60 | garde si vrai/faux trouvé = corrigé |
| `verify_written` (courte, ouverte) | « Cours : … Question : … Réponse attendue : … La réponse attendue est-elle correcte selon le cours ET répond-elle exactement à la question posée ? Format : {"answers":[true]} ou {"answers":[false]} » | `BoolAnswers` | 20 | garde si `true` |

Toutes à température **0**, prompt passé par `mask_pii`. Si la vérification échoue (erreur LLM, JSON
invalide, nombre de réponses différent), la question est **gardée sans contrôle** et l'événement est compté
(`verifications_impossibles`).

**Vérification groupée** (`verify_group`) : les candidats d'un même type générés pendant un tour (2 à 4) sont
vérifiés en **un seul appel**, chacun avec son propre passage. Un seul candidat : vérification unitaire ci-dessus.

```text
--- Question 1 ---
Extrait du cours :
[page {page}] {passage}
Question : {question}            ← QCM : suivie des choix A. … D.
                                 ← Vrai/Faux : « Affirmation : {affirmation} »
                                 ← courte / réflexion : « Question : … » puis « Réponse attendue : … »
--- Question 2 ---
…

Pour chacune des {n} questions, dans l'ordre, donne la lettre de la seule bonne réponse selon SON extrait du cours.
Format : {"answers":[...]} avec exactement {n} lettres.
```

(Vrai/Faux : « réponds true si elle est vraie selon SON extrait du cours, false sinon » ; réponses rédigées :
« true si la réponse attendue est correcte selon SON extrait du cours ET répond exactement à la question posée ».)

Protections : `json_schema` dérivé de `LetterAnswers` / `BoolAnswers` avec **exactement n réponses**
(`minItems = maxItems = n` ; sans cela qwen2.5 recopiait l'exemple de format à 2 valeurs), puis validation par le
modèle Pydantic inchangé. JSON invalide ou incomplet : **repli sur la vérification unitaire** de chaque question
(compté `verifications_groupees_repli`). Les doublons de sens sont écartés **avant** cet appel.

### 2.5 Validateurs Pydantic (`schemas.py`)

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

## 3. Flashcards (phase 7)

Fichiers : `app/phase7_flashcards/generator.py` et `app/phase7_flashcards/schemas.py`.
Deux étapes : repérer les concepts clés, puis une carte par concept (RAG sur les passages du cours).

Prompt système de génération :

```text
Tu es un enseignant qui prépare des fiches de révision à partir d'un cours. Tu réponds UNIQUEMENT avec un objet JSON valide et compact, sans aucun texte autour.
```

### 3.1 Extraction des concepts (`extract_concepts`)

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

Appel : température **0.2**, `max_tokens` **200**, `json_schema=ConceptBatch`. Validateur `Concept` : nom de
2 à 80 caractères, importance 1, 2 ou 3. Les concepts en double (même nom, ou similarité ≥ 0.97) sont
fusionnés, les plus importants sont gardés.

### 3.2 Rédaction d'une carte (`make_card`)

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
`json_schema=FlashcardBatch`. Le concept est imposé par le code (pas par le modèle).

Validateur `Flashcard` : recto de 8 à 150 caractères terminé par un seul `?` ; verso de 5 à 250
caractères, sans oui/non, sans numéro de page, sans hésitation (« probablement », « peut-être »,
« le cours ne »…), terminé par une ponctuation (réponse non coupée), en français, et apportant au moins
2 mots absents du recto.

### 3.3 Vérification d'une carte (`verify_card`)

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

Température **0**, `max_tokens` **20**, `json_schema=BoolAnswers`. Carte écartée si `true`.

### 3.4 Vérification groupée des cartes (`verify_cards`)

Les cartes rédigées pendant un tour (2 à 5) sont vérifiées en un seul appel, même prompt système :

```text
--- Carte 1 ---
Extrait du cours :
{passages de la carte}
Question : {front}
Réponse : {back}
--- Carte 2 ---
…

Pour chacune des {n} cartes, dans l'ordre : sa réponse contient-elle une ERREUR, c'est-à-dire une information qui
contredit SON extrait du cours ou qui ne s'y trouve pas ? Réponds true seulement si tu es sûr qu'il y a une erreur.
Format : {"answers":[...]} avec exactement {n} valeurs true/false.
```

Température **0**, `max_tokens` **60**, `json_schema` à exactement n booléens, validation `BoolAnswers`. JSON
invalide ou incomplet : vérification unitaire de chaque carte. Une carte trop proche d'une carte déjà gardée
(similarité ≥ 0.92) est écartée **avant** la vérification. Une carte rejetée (validation ou vérification) a une
deuxième chance au tour suivant (température 0.7).

L'extraction des concepts (3.1) est mise en cache en mémoire par (étudiant, cours, empreinte du contenu) : un
deuxième paquet sur le même cours ne refait pas ces appels.

---

## 4. Résumés (phase 9)

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

Tous les appels passent par `ask_structured` : `json_schema` du modèle Pydantic, validation avec le
**contexte des pages autorisées**, seconde tentative si rejet (température **0.3** puis **0.5**).

### 4.1 Étape « map » : résumé d'une section (`summarize_section`)

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

### 4.2 Étape « reduce » : vue d'ensemble (`write_overview`)

```text
Résumés des parties d'un cours, dans l'ordre :
{titre de chaque section + ses puces}

Rédige une vue d'ensemble du cours entier en 4 à 6 phrases, en français : le sujet du cours, les grandes
notions et la façon dont elles s'enchaînent. N'utilise que les résumés ci-dessus, n'invente rien.

Format attendu :
{"overview":"..."}
```

`max_tokens` **500**, schéma `OverviewDraft` : 80 à 1500 caractères, 3 à 7 phrases, en français.
Repli **sans invention** si deux rejets : « Ce cours aborde les parties suivantes : {titres}. »

### 4.3 Explication d'un thème (`explain_topic`)

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
`SummaryRequest`), niveau de l'étudiant, pages autorisées.

### 4.4 Validateur des puces (`check_bullet`)

Chaque puce : au moins 10 caractères hors référence, en français, **au moins une référence `[p.X]`**, et
**toutes les pages citées font partie des passages fournis**. Sinon la sortie est rejetée (seconde
tentative, puis section ignorée).

---

## 5. Agent Study Companion (phase 6)

Fichiers : `app/phase6_agent/graph.py` (prompts) et `app/phase6_agent/tools.py` (outils).
Client : `ChatOpenAI` (LangChain), température **0**, même `LLM_BASE_URL` / `LLM_MODEL` / `LLM_TIMEOUT`.

### 5.1 Prompt système de l'agent (`SYSTEM_PROMPT`)

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
(chaque nom passé par `mask_pii`) ; `level` = consigne de niveau du tuteur.

Après l'exécution d'un outil, on ajoute `AFTER_TOOLS_RULE` :

```text
Les outils ont été exécutés et leur résultat est affiché à l'étudiant (quiz, résumé, flashcards, progression).
Écris maintenant ta réponse finale : 1 à 3 phrases courtes et chaleureuses, en tutoyant l'étudiant, adaptées
à son niveau, qui présentent ce qui a été préparé. Ne recopie pas le contenu et n'invente rien. N'appelle un autre
outil que si la demande de l'étudiant n'est pas encore satisfaite.
```

Messages envoyés : les 6 derniers messages de la conversation (300 caractères au plus chacun) puis le
message de l'étudiant, **tous passés par `mask_pii`**.

### 5.2 Description des outils (function calling)

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

### 5.3 Classification de repli (`classify_intent`)

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
par défaut).

### 5.4 Étiquetage des notions d'un quiz (`label_concepts`)

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

## 6. Annexe : prompts du fine-tuning (phase 4 bis, hors application)

Ces prompts ne servent qu'aux scripts hors ligne de `app/phase4_finetuning/`.

| Prompt | Fichier | Rôle | Réglages |
|---|---|---|---|
| `QUESTION_SYSTEM` + prompt « Passage d'un cours (page X) … Écris {type de question} qu'un étudiant pourrait poser sur ce passage … » | `dataset.py` | générer une question (définition, rôle, comparaison, exemple, pourquoi) par passage | température 0.7, `max_tokens` 120, `json_schema` `{"question"}`, `mask_pii` |
| Prompt complet du tuteur (`build_system_prompt(level)` + `build_user_prompt`) | `dataset.py` | réponse « idéale » de l'enseignant pour chaque niveau | température 0.3, `max_tokens` 700 ; filtres : hors cours, anglais, longueur par niveau, référence `[p.X]`, hésitation |
| `FINETUNE_SYSTEM` = `SYSTEM_PROMPT` + « Adapte ton explication au niveau de l'étudiant indiqué dans son message. » | `dataset.py` | prompt système des exemples d'entraînement (sans la consigne détaillée du niveau) | — |
| `JUDGE_SYSTEM` + `judge_prompt` (notes de 1 à 5 : niveau, fidélité, clarté, justification d'abord) | `evaluate.py` | juge LLM base vs affiné | température 0, `max_tokens` 250, `json_schema` (entiers 1 à 5), `mask_pii` |
