# Sécurité et confidentialité

## 1. Confidentialité des données

### 1.1 Masquage des données personnelles (`mask_pii`)

Fichier : `backend/app/core/privacy.py`.

| Donnée | Détection | Remplacement |
|---|---|---|
| Email | `[\w.+-]+@[\w-]+(\.[\w-]+)+` | `[EMAIL]` |
| Numéro (téléphone, CIN…) | 8 à 14 chiffres, indicatif `+216` optionnel, séparateurs espace, point ou tiret | `[NUMÉRO]` |

Exemple : « Contact : ali.najjaa@esprit.tn ou +216 22 345 678 » → « Contact : [EMAIL] ou [NUMÉRO] ».
Les années (« LeNet-5 en 1998 ») ne sont pas touchées.

**Où il est appliqué** : à chaque prompt utilisateur envoyé au LLM (tuteur, examens, vérifications,
flashcards, résumés, classification, étiquetage des quiz), à chaque ligne d'historique, aux noms de cours et
de concepts injectés dans les prompts système, aux messages de l'agent, et à la question écrite dans les
logs du serveur.

**Le LLM ne reçoit jamais** l'email ni l'identifiant de l'étudiant. L'agent ne voit que son niveau et les
noms de ses cours ; l'identité (`AgentContext` : `user_id`, email) reste côté serveur, dans la fermeture du
graphe, et n'est jamais un argument d'outil.

### 1.2 Rien de personnel dans MLflow ni dans les traces

- **Runs MLflow** (`backend/app/phase5_evaluation/tracking.py`) : uniquement des nombres (durée, appels,
  rejets…), des réglages (modèle, format, difficulté, `top_k`), le nom du cours et le niveau. Ni email, ni
  identifiant d'étudiant, ni texte de question, ni thème demandé. En cas d'erreur, seul le **type** de
  l'exception est enregistré, jamais son message. Le benchmark enregistre le numéro de la question du jeu,
  pas son texte.
- **Traces de l'agent** (`backend/app/phase6_agent/tracing.py`) : chaque span passe par `redact_span` avant
  l'export.
  - Le texte écrit par l'étudiant (message actuel, historique, arguments libres `question`, `topic`) est
    remplacé par « [message de l'étudiant masqué] ».
  - Le texte des réponses de l'assistant est remplacé par sa longueur : `mask_pii` ne reconnaît pas les
    noms, et qwen2.5:7b répète parfois un prénom que l'étudiant a tapé.
  - Tout autre texte passe par `mask_pii`.
  - Restent visibles : prompts système (règles, niveau, noms des cours), outils choisis et arguments non
    libres (cours, nombre, difficulté), routage entre les nœuds, durées, jetons.
- `GET /api/stats` renvoie des moyennes globales : les runs ne contenant aucun identifiant, ils ne peuvent
  pas être filtrés par compte.
- Le texte complet des échanges reste dans la base de l'application, consultable par l'étudiant seul dans
  ses conversations.

### 1.3 Cours et données privés par `user_id`

- **Qdrant** : chaque morceau porte le `user_id` de son propriétaire. Toutes les lectures (recherche,
  lecture du cours entier, suppression) filtrent par `user_id`. Un morceau sans propriétaire (scripts en
  ligne de commande) est invisible dans l'API, et un script ne peut pas supprimer le cours d'un étudiant.
- **SQLite** : chaque table personnelle a une colonne `user_id`. Les routes chargent la ressource puis
  vérifient le propriétaire ; la ressource d'un autre étudiant renvoie **404** (même réponse qu'une
  ressource inexistante, pour ne pas révéler son existence). Même règle pour les tâches de fond de l'agent.
- `require_course` vérifie que le cours demandé appartient à l'étudiant avant toute génération.
- Les PDF des examens sont stockés dans `STORAGE_DIR` et servis seulement à leur propriétaire.

## 2. Authentification

### 2.1 JWT

Fichiers : `backend/app/core/security.py`, `backend/app/phase8_personal/deps.py`.

- Jeton **HS256** signé avec `JWT_SECRET`, contenant `sub` (identifiant de l'étudiant), `iat` et `exp`.
- Durée de validité : `JWT_EXPIRE_HOURS` (24 h par défaut).
- `sub` et `exp` sont **obligatoires** au décodage ; un jeton invalide, expiré ou d'un compte supprimé →
  **401** « Session expirée ou invalide : reconnecte-toi. »
- Sans `JWT_SECRET`, le serveur refuse de signer ou de vérifier un jeton (erreur explicite) : pas de secret
  par défaut.
- Toutes les routes sont protégées sauf l'inscription, la connexion et `/health`.
- Côté frontend : un intercepteur ajoute l'en-tête `Authorization: Bearer …` ; un garde redirige vers la
  connexion les pages protégées.

### 2.2 Mots de passe

- Hachage **bcrypt** avec sel aléatoire ; seul le haché est stocké (`users.password_hash`).
- Longueur : 8 caractères au moins, 72 octets au plus (au-delà, bcrypt ignorerait la fin du mot de passe).
- Email normalisé (minuscules, sans espaces) et validé (`EmailStr`) ; 409 si l'email existe déjà, y compris
  pour deux inscriptions simultanées (contrainte d'unicité).
- **Temps constant** à la connexion : un email inconnu est comparé à un haché factice, il prend autant de
  temps qu'un mauvais mot de passe. Message unique : « Email ou mot de passe incorrect. »

## 3. Gestion des erreurs du LLM

Fichier : `backend/app/phase1_llm/llm.py` (même traduction dans l'agent, `_as_llm_error`).

| Situation | Message renvoyé | Code HTTP |
|---|---|---|
| Pas de réponse en `LLM_TIMEOUT` (120 s) | « Le modèle n'a pas répondu en 120 s (timeout). Réessaie. » | 503 |
| Serveur injoignable (Ollama arrêté) | « Impossible de joindre le serveur du LLM. Vérifie qu'Ollama est lancé. » | 503 |
| `LLM_API_KEY` absente | « Clé API du LLM absente : renseigne LLM_API_KEY dans le fichier .env. » | 503 |
| Clé invalide | « Clé API du LLM invalide. » | 503 |
| Limite de débit (429) | attente du délai demandé puis nouvel essai (4 au plus) ; si la limite persiste : « Limite de débit du fournisseur LLM atteinte (trop de requêtes ou de jetons par minute). Réessaie plus tard. » | 503 |
| Limite quotidienne (429, offre gratuite) | sans attendre : « Limite quotidienne du fournisseur LLM atteinte (offre gratuite). Réessaie dans X min, ou choisis un autre modèle (LLM_MODEL). » | 503 |
| Modèle sans `json_schema` (400) | pas d'erreur : nouvel essai en `json_object`, sortie validée par Pydantic | — |
| Autre erreur du fournisseur | « Le fournisseur LLM a renvoyé une erreur (code X). » | 503 |
| Réponse vide | « Le modèle a renvoyé une réponse vide. Réessaie. » | 503 |

- Toutes ces erreurs deviennent une `LLMError`, transformée en **503** par un gestionnaire global
  (`main.py`). Le frontend affiche le champ `detail`.
- **Une génération ne s'arrête pas au premier échec** : un appel raté est compté et ignoré ; l'erreur
  n'est renvoyée que si aucune sortie valide n'a été produite.
- **Rien n'est enregistré si le LLM échoue** (question de conversation, message à l'agent) : l'étudiant
  peut reposer la question.
- Une erreur inattendue dans une tâche de fond renvoie « Erreur interne de l'assistant. Réessaie. » (500) ;
  le détail reste dans les logs du serveur.
- Les erreurs de validation (422) sont renvoyées en français, sans le préfixe anglais de Pydantic.

## 4. Validation des sorties avant affichage

Aucune sortie du LLM n'est affichée sans contrôle :

1. **Sortie structurée** (`json_schema`) : le serveur impose le format JSON.
2. **Validation Pydantic** : longueurs, formats et règles métier (pas de négation ni de « combien »,
   4 choix distincts, texte en français, pas d'hésitation, `[p.X]` obligatoire et page parmi les passages
   fournis…). Un élément invalide est rejeté, jamais affiché. Détails : [prompts.md](prompts.md).
3. **Auto-vérification** (examens, flashcards) et **détection des doublons** par embeddings.
4. **Agent** : arguments d'outil validés ; réponse finale raccourcie ; un texte qui ressemble à un appel
   d'outil en JSON n'est pas affiché.
5. **Frontend** : le markdown est converti par `marked` puis passe par la **sanitization d'Angular**
   (`[innerHTML]`), qui retire scripts et attributs dangereux ; les autres textes sont affichés par
   interpolation (échappés). Une référence `[p.X]` absente des sources est signalée visuellement.
6. **Entrées** : seuls les fichiers `.pdf` sont acceptés ; message limité à 2000 caractères, thème à
   200 caractères ; niveaux, difficultés et nombres limités à des valeurs connues (`Literal`).

## 5. Secrets et fichiers ignorés

- Les secrets (`JWT_SECRET`, `LLM_API_KEY`, `HF_TOKEN`) sont dans `backend/.env`, **ignoré par git**.
  `backend/.env.example` liste les variables sans aucune valeur secrète.
- Ignorés par `backend/.gitignore` : `.env`, `*.db` (base de l'application et base MLflow), `storage/`
  (PDF des examens), `mlruns/`, `app/phase5_evaluation/results/*` (CSV), `app/phase4_finetuning/data/*`
  (sauf `sample.jsonl`), `.venv/`.
- CORS limité à l'origine du frontend (`http://localhost:4200`).

## 6. Limites connues

| Limite | Risque | Piste d'amélioration |
|---|---|---|
| **Jeton JWT dans `localStorage`** | lisible par un script injecté (XSS) ; la sanitization d'Angular réduit ce risque sans l'annuler | cookie `HttpOnly` + `SameSite`, avec protection CSRF |
| Pas de révocation de jeton | un jeton volé reste valide jusqu'à son expiration (24 h) ; la déconnexion ne fait que supprimer le jeton côté navigateur | durée plus courte + jeton de rafraîchissement, liste de révocation |
| **Tâches de fond en mémoire** | perdues au redémarrage du serveur ; un seul processus uvicorn possible ; résultats oubliés après une heure | file de tâches persistante (Celery/RQ + Redis) |
| `mask_pii` ne reconnaît que les emails et les numéros | un nom, une adresse postale ou un identifiant étudiant non numérique passent | reconnaissance d'entités nommées (NER) |
| Données en clair sur le disque | `study.db`, PDF des examens et Qdrant non chiffrés | chiffrement du disque ou de la base |
| Pas de limitation de débit | inscriptions ou connexions en rafale, générations coûteuses lancées en boucle | limiteur de requêtes (ex. `slowapi`) |
| Qdrant sans authentification | accessible à tout processus local sur le port 6333 | clé API Qdrant, réseau Docker privé |
| HTTP en local | trafic non chiffré | HTTPS derrière un proxy inverse en production |
| Contenu des PDF importés | un cours peut contenir des données personnelles qui ne sont ni numéros ni emails ; elles iraient dans Qdrant | avertissement à l'import, NER |
