# Déploiement

Trois façons de lancer l'application :

| Mode | LLM | Qdrant | Données | Usage |
|---|---|---|---|---|
| Développement (`uvicorn` + `ng serve`) | Ollama local (qwen2.5:7b) ou Groq | Docker (port 6333) | `backend/study.db`, `storage/`, `mlruns/` | développement, tests, benchmark |
| **Docker Compose** | **Groq** (par défaut) ou Ollama de la machine | conteneur `qdrant` | volumes Docker (persistants) | démonstration locale complète |
| **Hugging Face Spaces** | Groq | intégré (`qdrant-client path=`) | disque du Space (**effacé au redémarrage**) | démonstration publique |

Le code métier est le même partout : seules les variables d'environnement changent.

## 1. Le LLM : Ollama ou Groq

Le LLM est toujours configuré par `LLM_BASE_URL`, `LLM_MODEL` et `LLM_API_KEY` (API compatible OpenAI).

| Profil | `LLM_BASE_URL` | Clé | `LLM_MODEL` |
|---|---|---|---|
| Ollama (local) | `http://localhost:11434/v1` | `LLM_API_KEY=ollama` | `qwen2.5:7b` |
| Groq | `https://api.groq.com/openai/v1` | `GROQ_API_KEY=gsk_…` | `qwen/qwen3.8-27b` |

Quand `LLM_BASE_URL` pointe vers `api.groq.com`, **`GROQ_API_KEY` est prioritaire** sur `LLM_API_KEY`. Le même
`backend/.env` sert ainsi aux deux profils : Docker Compose ne change que `LLM_BASE_URL` et `LLM_MODEL`.
Les deux profils sont décrits, commentés, dans [backend/.env.example](../backend/.env.example).

### Choix du modèle Groq

Vérifié le 14 octobre 2026 dans la documentation de Groq (pages *Models*, *Tool Use*, *Structured Outputs*,
*Rate Limits*) et par des appels réels avec la clé du projet.

| Modèle | Accessible avec la clé | Tool calling | `json_schema` | Constat |
|---|---|---|---|---|
| **qwen/qwen3.8-27b** | oui | oui (y compris parallèle) | oui (strict et best-effort) | **retenu** : schémas Pydantic du projet acceptés, bon outil pour l'agent, très bon français, 0,3 à 1,7 s par appel |
| openai/gpt-oss-120b | oui | oui (pas de parallèle) | oui | rejeté : erreurs 400 `json_validate_failed` sur les schémas du projet ; modèle « à raisonnement » dont la réflexion consomme les petits budgets de jetons (20 à 100 jetons pour les vérifications) |
| openai/gpt-oss-20b | oui | oui (pas de parallèle) | oui | mêmes erreurs que gpt-oss-120b |
| llama-3.3-70b-versatile, llama-3.1-8b-instant | **non** (404 `model_not_found`) | oui | non (json_object seulement) | listés dans la documentation, mais pas disponibles pour ce compte |

Réserve : qwen/qwen3.8-27b est un modèle **« preview »** chez Groq (« pour l'évaluation, peut être retiré à
court terme »). S'il disparaît, il suffit de changer `LLM_MODEL` (ou `DOCKER_LLM_MODEL`).

### Repli `json_schema` → `json_object`

Fichier : `backend/app/phase1_llm/llm.py`. Les appels JSON envoient d'abord `response_format: json_schema`.

- Si le fournisseur répond que le modèle **ne prend pas en charge** `json_schema` (erreur 400), l'appel est
  refait en `json_object` et ce repli est **mémorisé** pour le modèle (une seule erreur).
- Si le modèle **n'arrive pas à produire** un JSON conforme (Groq : `json_validate_failed`), l'appel est refait
  une fois en `json_object`, sans mémoriser.
- `LLM_JSON_MODE=json_object` force ce mode dès le départ.

Dans tous les cas, le JSON reçu passe ensuite par les **validateurs Pydantic** des générateurs, comme avant :
un repli ne laisse passer aucune sortie invalide. Le nombre de replis est compté dans MLflow
(`replis_json_object`).

### Limites de débit (erreur 429)

Offre gratuite de Groq constatée pour qwen/qwen3.8-27b : **30 requêtes et 8 000 jetons par minute, 1 000 requêtes
par jour** (en-têtes `x-ratelimit-*`). La documentation indique aussi un plafond quotidien de jetons.

- Sur une erreur 429, `chat()` attend le délai demandé par Groq (en-tête `retry-after`, ou « try again in 7.5s »
  dans le message), puis réessaie : jusqu'à `LLM_RATE_LIMIT_RETRIES` fois (4), avec une attente maximale de
  `LLM_RATE_LIMIT_MAX_WAIT` secondes (60) par essai. Sans délai indiqué : 2, 4, 8, 16 s.
- **Limite quotidienne** (« per day », TPD/RPD) ou attente trop longue : arrêt immédiat avec un message clair
  (« Limite quotidienne du fournisseur LLM atteinte (offre gratuite). Réessaie dans 23 min, ou choisis un autre
  modèle »), renvoyé en **503** au frontend.
- Agent (LangChain) : le client OpenAI réessaie aussi les 429 (`max_retries = LLM_RATE_LIMIT_RETRIES`) ; même
  message clair si la limite persiste.
- Les attentes sont comptées dans MLflow (`attentes_limite_debit`).

Conséquence pratique : avec 8 000 jetons par minute, un examen complet (≈ 50 appels) prend plusieurs minutes
même si chaque appel ne dure qu'une seconde. Le proxy nginx accepte donc des requêtes de 20 minutes.

## 2. Docker en local

Fichiers : [docker-compose.yml](../docker-compose.yml), [backend/Dockerfile](../backend/Dockerfile),
[frontend/Dockerfile](../frontend/Dockerfile), [frontend/nginx.conf](../frontend/nginx.conf).

```
navigateur ──► frontend (nginx, :8080) ──/api──► backend (uvicorn, :8000) ──► qdrant (:6333)
                     └── fichiers Angular                    └──► Groq (https)
```

| Service | Image | Rôle | Persistance | Healthcheck |
|---|---|---|---|---|
| `qdrant` | `qdrant/qdrant:v1.19.2` | base vectorielle | volume `qdrant-data` | port 6333 ouvert |
| `backend` | `backend/Dockerfile` (Python 3.11 slim) | API FastAPI | volumes `backend-db` (study.db), `backend-storage` (PDF), `backend-mlruns` (MLflow) | `GET /health` |
| `frontend` | `frontend/Dockerfile` (Node 24 → nginx non root) | frontend + proxy `/api` | — | `GET /` |

Seul le port **8080** est publié : Qdrant et le backend restent internes (pas de conflit avec le Qdrant de
développement sur 6333 ni avec uvicorn sur 8000).

Image du backend :
- **torch CPU uniquement** (installé depuis l'index CPU de PyTorch) : les embeddings n'ont pas besoin de GPU ;
- **modèle d'embeddings téléchargé au build** (`HF_HUB_OFFLINE=1` ensuite) : démarrage rapide, aucun accès au
  Hub à l'exécution ;
- **utilisateur non root** (`app`, uid 1000) ;
- aucun secret : `.env`, bases, PDF et MLflow sont exclus par `.dockerignore`.

### Lancer

Prérequis : Docker Desktop, et `backend/.env` avec au moins `JWT_SECRET` et `GROQ_API_KEY`.

```powershell
# depuis la racine du projet
docker compose up --build -d
docker compose ps                 # les 3 services doivent être « healthy »
```

Puis http://localhost:8080 : créer un compte (la base Docker est distincte de `backend/study.db`), importer un
PDF dans l'Assistant.

```powershell
docker compose logs -f backend    # journaux du backend
docker compose down               # arrêter (les volumes sont gardés)
docker compose down -v            # arrêter ET effacer les données (comptes, cours, MLflow)
```

Utiliser l'Ollama de la machine au lieu de Groq (sans modifier les fichiers) :

```powershell
$env:DOCKER_LLM_BASE_URL = "http://host.docker.internal:11434/v1"
$env:DOCKER_LLM_MODEL = "qwen2.5:7b"
docker compose up -d backend
```

MLflow des conteneurs (volume `backend-mlruns`) : `docker compose cp backend:/app/data/mlruns ./mlruns-docker`
puis `mlflow ui --backend-store-uri sqlite:///mlruns-docker/mlflow.db`.

## 3. Hugging Face Spaces

Fichiers : [deploy/hf-space/](../deploy/hf-space/).

| Fichier | Rôle |
|---|---|
| `Dockerfile` | image unique : build Angular, backend Python, frontend servi par FastAPI, port **7860** |
| `space_app.py` | point d'entrée : `app.main` + fichiers statiques du frontend (repli sur `index.html` pour les routes Angular) |
| `README.md` | page du Space, avec l'en-tête YAML (`sdk: docker`, `app_port: 7860`) |
| `prepare-space.ps1` | assemble le dossier à pousser, **sans aucun secret** (vérification incluse) |

Dans le Space : **Qdrant en mode intégré** (`QDRANT_PATH=/app/data/qdrant`, pas de serveur), **MLflow désactivé**
(`MLFLOW_ENABLED=false`), LLM Groq. Le frontend et l'API ont la même origine : pas de CORS à configurer.

### Pas à pas : créer `Alinajjaa/ai-study-assistant`

1. **Créer le Space** : https://huggingface.co/new-space → Owner `Alinajjaa`, Space name `ai-study-assistant`,
   SDK **Docker** (modèle *Blank*), matériel **CPU basic** (gratuit), visibilité au choix.

2. **Secrets** (Settings → *Variables and secrets* → *New secret*) :

   | Secret | Valeur |
   |---|---|
   | `GROQ_API_KEY` | ta clé Groq (`gsk_…`) |
   | `JWT_SECRET` | une nouvelle chaîne aléatoire : `python -c "import secrets; print(secrets.token_hex(32))"` (pas celle du `.env` local) |

   **Variables** (facultatives, mêmes noms que dans `.env`) : `LLM_MODEL` (défaut `qwen/qwen3.8-27b`),
   `LLM_BASE_URL` (défaut Groq), `LLM_TIMEOUT`, `LLM_RATE_LIMIT_RETRIES`, `JWT_EXPIRE_HOURS`, `CORS_ORIGINS`.
   Pour un autre fournisseur : `LLM_BASE_URL`, `LLM_MODEL` et le secret `LLM_API_KEY`.

3. **Préparer le dossier** (depuis la racine du projet, PowerShell) :

   ```powershell
   .\deploy\hf-space\prepare-space.ps1 -Destination ..\ai-study-assistant-space
   ```

4. **Pousser le code**, au choix :

   - avec la CLI Hugging Face (sans git) :

     ```powershell
     pip install -U huggingface_hub
     hf auth login                      # jeton « write » de https://huggingface.co/settings/tokens
     hf upload Alinajjaa/ai-study-assistant ..\ai-study-assistant-space . --repo-type=space
     ```

   - avec git :

     ```powershell
     git clone https://huggingface.co/spaces/Alinajjaa/ai-study-assistant ..\hf-space-repo
     .\deploy\hf-space\prepare-space.ps1 -Destination ..\hf-space-repo
     cd ..\hf-space-repo
     git add . ; git commit -m "Déploiement AI Study Assistant" ; git push
     ```

     Mot de passe demandé par git : le jeton « write » Hugging Face.

5. **Suivre le build** dans l'onglet *Logs* du Space (10 à 20 min la première fois : dépendances Python et
   modèle d'embeddings), puis ouvrir https://alinajjaa-ai-study-assistant.hf.space.

Tester l'image du Space en local avant de pousser :

```powershell
docker build -f deploy/hf-space/Dockerfile -t ai-study-space .
docker run --rm -p 7860:7860 --env-file backend/.env -e QDRANT_PATH=/app/data/qdrant `
  -e DATABASE_URL=sqlite:////app/data/study.db -e STORAGE_DIR=/app/data/storage -e MLFLOW_ENABLED=false `
  -e LLM_BASE_URL=https://api.groq.com/openai/v1 -e LLM_MODEL=qwen/qwen3.8-27b ai-study-space
```

(Les `-e` remplacent les valeurs locales du `.env` ; sur le Space, seuls les secrets sont nécessaires.)

### Limites du Space

- **Données effacées au redémarrage** : comptes, cours, conversations, examens et vecteurs sont sur le disque du
  conteneur. Un Space gratuit s'endort après 48 h d'inactivité et redémarre à chaque nouveau push. Le stockage
  persistant (payant, monté sur `/data`) permettrait de les garder en réglant `DATABASE_URL`, `STORAGE_DIR` et
  `QDRANT_PATH` sous `/data`.
- **MLflow désactivé** : aucun suivi des générations dans le Space (le réactiver écrirait dans un MLflow local
  et éphémère, sans interface).
- **Qdrant intégré** : un seul processus, adapté à quelques cours ; pas d'index de payload (le filtre `user_id`
  reste appliqué).
- **Limites de Groq** partagées par tous les visiteurs du Space (même clé) : la limite quotidienne peut être
  atteinte vite.
- **CPU basic** (2 vCPU, 16 Go) : l'import d'un gros PDF (embeddings sur CPU) prend plusieurs secondes.
- **URL publique et CORS** : l'application est publique à l'adresse du Space. Le frontend et l'API partagent la
  même origine, donc `CORS_ORIGINS` n'est utile que pour un frontend hébergé ailleurs (par exemple
  `CORS_ORIGINS=https://mon-frontend.exemple`). Le Space s'affiche aussi dans un cadre sur huggingface.co : si
  le navigateur bloque le stockage local dans ce cadre (jeton de connexion), ouvrir directement l'URL
  `*.hf.space`.

## 4. Sécurité du déploiement

- **Aucun secret dans les images ni dans le dépôt** : `.dockerignore` exclut `.env`, `*.db`, `storage/`,
  `mlruns/` ; `prepare-space.ps1` refuse de produire un dossier contenant `.env`, une base ou des données ; les
  clés arrivent au démarrage (`env_file` de Compose, secrets du Space). `backend/.env.example` ne contient que
  des valeurs vides ou publiques. Vérification faite sur l'image du backend :
  `docker run --rm --entrypoint sh ai-study-assistant-backend -c 'env | grep -iE "key|secret|token"; find / -name .env'`
  ne montre que `GPG_KEY` (empreinte publique de l'image Python officielle) et aucun fichier `.env`.
- **Secrets distincts par environnement** : un `JWT_SECRET` propre au Space ; une clé Groq qui peut être
  révoquée sur https://console.groq.com/keys sans toucher au reste.
- **Conteneurs non root** (backend uid 1000, nginx non privilégié) ; seuls les ports 8080 (Compose) et 7860
  (Space) sont exposés.
- **Données envoyées à Groq** : avec le profil Groq, les extraits de cours et les questions (après `mask_pii`)
  quittent la machine et sont traités par un service externe. Pour des cours confidentiels, rester sur Ollama.
- Limites connues inchangées (voir [securite.md](securite.md)) : jeton JWT dans `localStorage`, tâches de fond en
  mémoire, pas de limitation de débit côté application — à traiter avant une ouverture large au public.
