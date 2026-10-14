# Phase 4 bis : fine-tuning LoRA du style du tuteur

Cahier des charges : *fine-tuning a Hugging Face model to produce your desired tutoring style*.

**Objectif** : apprendre à un petit modèle Hugging Face (**Qwen/Qwen2.5-1.5B-Instruct**) le style du tuteur
de l'application. Il doit répondre à partir d'un passage du cours, citer la page `[p.X]` et **adapter son
explication au niveau** de l'étudiant :

| Niveau | Style attendu |
|---|---|
| débutant | mots simples, termes techniques définis, analogie de la vie courante, exemple concret |
| intermédiaire | explication claire avec les termes du cours et un exemple |
| avancé | réponse précise et technique, sans définitions de base, notions reliées entre elles |

**Matériel** : le GPU local (RTX 4050, 6 Go) ne suffit pas pour entraîner. L'entraînement se fait donc sur
**Google Colab** (GPU T4 gratuit, 15 Go). Le jeu de données et l'évaluation se font **en local**, avec Ollama
(qwen2.5:7b) et Qdrant.

```
dataset.py (local)  →  notebooks/finetune_lora.ipynb (Colab)  →  evaluate.py (local)
train/test.jsonl         adaptateur LoRA + results_*.jsonl          juge LLM + MLflow + CSV
```

## Étapes, dans l'ordre

Toutes les commandes se lancent depuis `backend/`, avec le venv (`.venv/Scripts/python.exe` sous Windows).
Ollama et Qdrant doivent tourner.

### 1. Jeu de données (local) : environ 1 h pour 300 exemples

```
python -m app.phase4_finetuning.dataset <email> --n 300
```

- Source : les cours du compte `<email>` dans Qdrant (passages de 200 caractères ou plus). Aucune autre
  donnée de l'étudiant n'est lue (ni conversations, ni historique). `mask_pii` est appliqué partout.
- Pour chaque passage, le LLM configuré pose une question d'un type différent : définition, rôle,
  comparaison, exemple, « pourquoi ».
- Pour chaque question, il rédige la **réponse idéale** pour chacun des 3 niveaux (modèle enseignant), avec le
  prompt complet du tuteur de l'application et la consigne détaillée du niveau.
- Chaque réponse est filtrée. Causes de rejet : `hors_cours`, `anglais`, `francais`, `longueur` (bornes
  en mots selon le niveau : débutant 60 à 260, intermédiaire 35 à 200, avancé 20 à 170), `reference` (aucun
  `[p.X]` ou mauvaise page), `incertitude` (« probablement », « peut-être »…). La cause `question` compte les
  questions inutilisables.
- `--n` est le nombre d'**exemples gardés** (question × niveau) : 300 exemples ≈ 100 questions ≈ 400 appels
  au LLM (≈ 12 s par appel avec qwen2.5:7b).
- **Reprise** : si le script est interrompu (Ctrl+C, panne d'Ollama…), relance la même commande. Il repart
  de `data/all.jsonl` et `data/progress.json`. `--restart` repart de zéro.
- Statistiques finales : exemples gardés (par niveau et par type), rejets par cause, découpage.

Format d'une ligne (format chat, comme `messages` de Hugging Face) :

```json
{"id": "…-role-debutant", "qid": "…-role", "type": "role", "niveau": "debutant", "page": 7,
 "messages": [
   {"role": "system", "content": "Tu es un tuteur… Adapte ton explication au niveau de l'étudiant indiqué dans son message."},
   {"role": "user", "content": "Niveau de l'étudiant : débutant.\n\nExtraits du cours :\n[p.7] …\n\nQuestion de l'étudiant : …"},
   {"role": "assistant", "content": "… [p.7]."}]}
```

Le message `system` du modèle affiné contient les règles du tuteur **sans** la consigne détaillée de chaque
niveau. Le modèle doit apprendre le style à partir du seul mot « débutant », « intermédiaire » ou « avancé ».

Fichiers produits dans `data/` (ignorés par git, sauf `sample.jsonl`) :
- `train.jsonl` (90 %) et `test.jsonl` (10 %), découpés **par question** : les 3 niveaux d'une question
  sont toujours dans le même fichier, donc le test ne contient aucune question vue à l'entraînement ;
- `sample.jsonl` : 10 exemples (les 3 niveaux représentés), pour le rapport.

### 2. Entraînement (Google Colab) : environ 30 à 45 min en tout

1. Ouvrir `notebooks/finetune_lora.ipynb` dans Colab (Fichier → Importer un notebook).
2. **Exécution → Modifier le type d'exécution → GPU T4**.
3. Exécuter les cellules dans l'ordre. Envoyer `train.jsonl` et `test.jsonl` quand le notebook le demande.
4. Dans les secrets Colab (🔑), ajouter et autoriser pour le notebook : `HF_TOKEN` (jeton **en écriture**)
   et `HF_REPO_ID` (ex. `Alinajjaa/study-tutor-qwen2.5-1.5b-lora`) ou, à défaut, `HF_USERNAME`. Rien à
   modifier dans le code. Les fichiers envoyés sont rangés dans `data/train.jsonl` et `data/test.jsonl`, même
   si Colab les renomme lors d'un second envoi.

| Étape | Durée (T4) |
|---|---|
| Installation | 1 à 2 min |
| Chargement du modèle 4 bits | 1 min |
| Entraînement (300 exemples, 3 époques) | 10 à 20 min |
| Génération base + affiné sur le test | 5 à 10 min |
| Publication sur le Hub | 1 min |

Réglages : QLoRA (4 bits nf4, calcul en float16 car le T4 ne gère pas bfloat16, poids LoRA en float32), LoRA `r=16`, `alpha=32`, `dropout=0.05` sur `q/k/v/o_proj` et
`gate/up/down_proj`, `SFTTrainer`, 3 époques, lot effectif de 16 (4 × 4), taux d'apprentissage 2e-4 avec
décroissance cosinus, séquences de 1 024 jetons, `gradient_checkpointing`, optimiseur `paged_adamw_8bit`.
La perte n'est calculée que sur la réponse du tuteur (format prompt / completion).

À télécharger à la fin : `results_base.jsonl`, `results_finetuned.jsonl` (à copier dans `data/`),
`loss_curve.png` et l'adaptateur zippé. L'adaptateur est publié sur
le dépôt `HF_REPO_ID` avec une model card en français. Version publiée :
[Alinajjaa/study-tutor-qwen2.5-1.5b-lora](https://huggingface.co/Alinajjaa/study-tutor-qwen2.5-1.5b-lora).

La comparaison est équitable : mêmes prompts, même température (0.3), même graine. Le modèle de base est le
même modèle 4 bits avec l'adaptateur désactivé.

### 3. Évaluation (local) : environ 10 à 20 min pour 30 exemples de test

```
python -m app.phase4_finetuning.evaluate app/phase4_finetuning/data/results_base.jsonl app/phase4_finetuning/data/results_finetuned.jsonl
```

Option `--limit N` : n'évalue que les N premiers exemples (essai rapide).

- **Juge LLM** (le LLM configuré, qwen2.5:7b, température 0). Il note de 1 à 5 le **respect du niveau**
  demandé, la **fidélité** au passage du cours et la **clarté**, après une courte justification. Il ne sait
  pas quel modèle a écrit la réponse.
- **Mesures automatiques** : longueur en mots (globale et par niveau), taux de références `[p.X]` valides,
  taux de réponses en français, taux de longueurs adaptées au niveau.
- **MLflow** : deux runs (`base` et `affine`) dans l'expérience `finetuning`. Paramètres : modèle,
  adaptateur, hyperparamètres LoRA, époques, taille des jeux, juge. Les métriques sont celles du tableau.
  Interface : `mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db`.
- **Fichiers** : `results/finetuning_<date>.csv` (base, affiné, écart), `results/finetuning_<date>_details.jsonl`
  (notes de chaque réponse, pour retrouver les cas où le modèle affiné fait moins bien).

## Lire les résultats

| Métrique | Ce qu'on espère du modèle affiné |
|---|---|
| `juge_niveau` (et `juge_niveau_<niveau>`) | **hausse** : c'est l'objectif principal du fine-tuning |
| `mots_debutant` > `mots_intermediaire` > `mots_avance` | un écart net entre niveaux = style vraiment adapté |
| `taux_citation_valide` | proche de 1 : le format `[p.X]` est appris |
| `taux_francais` | 1 |
| `juge_fidelite` | stable ou en hausse ; une baisse = le modèle invente (à surveiller) |
| `juge_clarte` | stable ou en hausse |
| `echecs_juge` | 0 (sinon, notes calculées sur moins de réponses) |

- Regarder d'abord l'**écart** (colonne `ecart` du CSV), puis quelques réponses dans le fichier de détails.
- Avec environ 30 réponses de test, un écart de moins de 0,3 point sur une note du juge n'est pas
  significatif.
- La courbe de perte (`loss_curve.png`) montre si l'entraînement a convergé. Une perte de test qui remonte
  signale du surapprentissage : réduire le nombre d'époques.

## Démonstration dans l'application (optionnelle, désactivée par défaut)

Par défaut, l'application utilise Ollama et rien ne change. Pour essayer le modèle affiné sur le GPU local
(4 bits, environ 1,5 Go de VRAM, compatible RTX 4050 6 Go) :

```
pip install torch --index-url https://download.pytorch.org/whl/cu128   # torch avec CUDA
pip install -r requirements-finetuning.txt                             # peft, bitsandbytes, accelerate
```

Dans `backend/.env` :

```
LLM_PROVIDER=hf-local
HF_ADAPTER=Alinajjaa/study-tutor-qwen2.5-1.5b-lora   # ou le dossier local de l'adaptateur
# HF_BASE_MODEL=Qwen/Qwen2.5-1.5B-Instruct               # valeur par défaut
```

Test rapide : `python -m app.phase4_finetuning.hf_local`. Seules les réponses en texte libre (tuteur,
explications) passent par le modèle affiné. Les demandes JSON (examens, flashcards, résumés, routage de
l'agent) restent sur Ollama, car l'adaptateur n'a appris que le style du tuteur. Pour revenir à la
normale : supprimer `LLM_PROVIDER` ou le mettre à `openai`.

## Limites

- **Petit modèle** (1,5 milliard de paramètres) : il raisonne moins bien que qwen2.5:7b. Le fine-tuning
  améliore le **style**, pas les connaissances. On le compare donc à son propre modèle de base, pas à
  l'enseignant.
- **Données générées par un modèle enseignant** : le modèle affiné imite ses qualités et ses défauts. Les
  filtres sont automatiques (aucune relecture humaine) et le jeu est petit (environ 300 exemples) et limité
  aux cours d'un seul compte.
- **Juge LLM** : qwen2.5:7b est aussi l'enseignant. Il peut préférer son propre style (biais
  d'auto-préférence) et les réponses longues. Ses notes sont indicatives. Les mesures automatiques et une
  relecture de quelques réponses les complètent.
- **Petit jeu de test** (environ 10 % des questions) : les écarts faibles ne sont pas significatifs.
- La démonstration `hf-local` utilise le prompt de l'application (consigne de niveau dans le message
  `system`), un peu différent de celui de l'entraînement (niveau dans le message `user`).

## Fichiers

| Fichier | Rôle |
|---|---|
| `dataset.py` | génération, filtres, reprise, export train/test/sample |
| `notebooks/finetune_lora.ipynb` | entraînement QLoRA, génération base/affiné, publication sur le Hub (Colab) |
| `evaluate.py` | juge LLM, mesures automatiques, MLflow, CSV |
| `hf_local.py` | fournisseur optionnel `LLM_PROVIDER=hf-local` |
| `../../requirements-finetuning.txt` | dépendances du fournisseur `hf-local` uniquement |
| `../../tests/test_finetuning.py` | tests (filtres, format JSONL, reprise, scores avec un juge simulé, MLflow) |
