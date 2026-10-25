# Charte graphique — AI Study Assistant

La page de connexion (`frontend/src/app/features/auth`) sert de référence. Toutes les valeurs ci-dessous sont des
variables CSS globales définies dans `frontend/src/styles.css`. Les composants n'utilisent que ces variables :
ils ne contiennent aucune couleur, police ou rayon codés en dur.

Le thème sombre reprend exactement la même charte. Seules les couleurs changent : polices, tailles, rayons,
espacements et composants restent identiques.

## 1. Palette

| Rôle | Variable | Clair | Sombre |
|---|---|---|---|
| Fond de page | `--bg` | `#ffffff` | `#0c0e12` |
| Surface / carte | `--surface` | `#ffffff` | `#13161c` |
| Surface secondaire (barres, zones neutres) | `--surface-alt` | `#f4f5f7` | `#1a1e26` |
| Surface surélevée (toasts) | `--surface-raised` | `#ffffff` | `#181c23` |
| Fond des champs | `--field-bg` | `#f3f6fa` | `#1c212a` |
| Texte principal | `--text` | `#111316` | `#f1f2f4` |
| Texte secondaire | `--text-muted` | `#565c66` | `#a3a9b3` |
| Accent bleu | `--accent` | `#0a5fd6` | `#6aa8ff` |
| Accent au survol | `--accent-hover` | `#084db0` | `#8dbcff` |
| Fond d'accent doux | `--accent-soft` | `#e8f0fc` | `#14233b` |
| Bordure | `--border` | `#e7e8ec` | `#262b35` |
| Bordure marquée | `--border-strong` | `#cfd2d8` | `#3a404c` |
| Bouton principal (fond) | `--btn-primary-bg` | `#111316` (noir) | `#f1f2f4` (blanc) |
| Bouton principal (texte) | `--btn-primary-text` | `#ffffff` | `#0c0e12` |
| Succès / fond | `--success` / `--success-soft` | `#1a7a46` / `#e3f4ea` | `#7fd3a1` / `#12291c` |
| Erreur / fond | `--danger` / `--danger-soft` | `#b4232a` / `#fcebec` | `#ff9b95` / `#331618` |
| Avertissement / fond | `--warning` / `--warning-soft` | `#8a5a00` / `#fdf2dc` | `#f0c274` / `#2e2412` |
| Information / fond | `--info` / `--info-soft` | `#0a5fd6` / `#e8f0fc` | `#8dbcff` / `#14233b` |
| Anneau de focus | `--focus-ring` | `#0a5fd6` | `#6aa8ff` |
| Squelette | `--skeleton` / `--skeleton-shine` | `#eceef2` / `#f7f8fa` | `#1a1e26` / `#252a34` |
| Graphiques | `--chart-1` / `--chart-2` / `--chart-track` | `#0a5fd6` / `#9cc0f0` / `#eceef2` | `#6aa8ff` / `#2f5f9e` / `#1f242d` |

En sombre, l'accent est éclairci (`#0a5fd6` → `#6aa8ff`) pour rester lisible sur le fond encre.

Contrastes calculés (WCAG 2.1, AA = 4,5:1 pour le texte courant) :

| Paire | Clair | Sombre |
|---|---|---|
| Texte principal / fond | 18,6 | 17,2 |
| Texte secondaire / fond | 6,7 | 8,2 |
| Texte secondaire / champ | 6,2 | 6,8 |
| Accent / fond | 5,8 | 8,0 |
| Accent / fond d'accent doux | 5,1 | 6,5 |
| Texte du bouton principal / bouton | 18,6 | 17,2 |
| Succès, erreur, avertissement / leur fond | 4,7 · 5,7 · 5,3 | 8,6 · 8,2 · 9,2 |

## 2. Typographie

| Usage | Police | Variable | Style |
|---|---|---|---|
| Titres (h1 à h4, noms de cartes, chiffres clés) | Space Grotesk | `--font-heading` | graisse 700, interlettrage −0,02 em (−0,03 em pour le h1 de page), interligne 1,2 |
| Accent des titres | Instrument Serif | `--font-accent` | italique, graisse 400, 1,08 em, couleur `--accent` (classe `.title-accent`) |
| Libellé de section | JetBrains Mono | `--font-label` | 0,75 rem, MAJUSCULES, interlettrage 0,2 em, gris `--text-muted`, précédé d'un point bleu de 6 px (classe `.kicker`) |
| Texte courant | Inter | `--font-sans` | 0,9375 rem, interligne 1,65, `--text` (gris très foncé en clair) |
| Chapeau | Inter | — | 1 rem, `--text-muted`, largeur max. 68 caractères (classe `.lede`) |

Échelle de tailles : `--text-xs` 0,75 · `--text-sm` 0,875 · `--text-md` 0,9375 · `--text-base` 1 · `--text-lg` 1,125 ·
`--text-xl` 1,375 · `--text-2xl` 1,75 · `--text-3xl` 2,25 rem. Le h1 de page varie de 1,75 à 2,75 rem selon la largeur
de l'écran. Le titre de la connexion varie de 2,4 à 4,25 rem.

Structure de chaque page :

```html
<header class="page-header">
  <p class="kicker">Bibliothèque · PDF importés</p>
  <h1>Mes <span class="title-accent">cours</span></h1>
  <p class="lede">…</p>
</header>
```

## 3. Espacements, rayons, ombres

- **Espacements** : `--space-1` 4 px · `-2` 8 · `-3` 12 · `-4` 16 · `-5` 20 · `-6` 24 · `-8` 32 · `-10` 40 · `-12` 48.
- **Rayons** : `--radius-sm` 8 px · `--radius` 12 px (champs, alertes) · `--radius-lg` 16 px (toasts, menus) ·
  `--radius-card` **24 px** (cartes, dialogues, zone de saisie : même rayon que la carte de connexion) ·
  `--radius-pill` (boutons, badges, segments).
- **Ombres (clair)** : `--shadow-card` (légère, cartes), `--shadow-card-lg` (carte de connexion),
  `--shadow-lg` (dialogues, toasts, menus).
- **Ombres (sombre)** : `--shadow-card` et `--shadow-card-lg` valent `none`. Les cartes ne gardent que leur bordure
  fine `--border`. Les éléments flottants (dialogues, menus, toasts) conservent une ombre profonde et leur bordure.

## 4. Composants

| Composant | Classe | Clair | Sombre |
|---|---|---|---|
| Bouton principal | `.btn` (+ `.btn--arrow` pour la flèche →) | pilule noire, texte blanc, graisse 600 | pilule blanche, texte noir |
| Bouton secondaire | `.btn--ghost` | pilule en contour `--border-strong`, fond transparent | contour clair `#3a404c`, texte clair |
| Bouton discret | `.btn--quiet` | texte bleu, fond bleu doux au survol | idem, avec l'accent éclairci |
| Lien d'action | `.link-arrow` | souligné fin (1 px, décalé de 0,3 em), suivi de →, bleu au survol | idem |
| Champ | `.field` | fond `#f3f6fa`, bordure `#e7e8ec`, rayon 12 px, hauteur 44 px ; focus : bordure bleue + halo bleu de 4 px | fond `#1c212a` (plus clair que la carte), texte clair, même focus bleu |
| Carte | `.card` | blanche, rayon 24 px, bordure fine, ombre légère | `#13161c`, bordure fine, sans ombre |
| Badge | `.badge` | pilule, fond doux de la couleur, texte de la couleur | idem, couleurs sombres |
| Toast | `app-toasts` | surface surélevée, rayon 16 px, icône sur fond doux | idem |
| Boîte de dialogue | `app-confirm-dialog`, dialogue d'examen | surface, rayon 24 px, voile `--overlay` | idem, voile plus opaque |
| Menu déroulant | menu du compte, menu de ligne, sélecteur de cours | surface, rayon 12 px, ombre `--shadow-lg` | idem |
| Contrôle segmenté | `.segmented` | pilule à fond de champ, option active = pilule noire | option active = pilule blanche |
| État vide | `app-empty-state` | icône sur fond bleu doux, titre très gras | idem |
| État d'erreur | `app-error-state` | fond `--danger-soft`, texte `--danger`, rayon 12 px | idem |
| Squelette | `.skeleton` | dégradé `#eceef2` → `#f7f8fa` | dégradé `#1a1e26` → `#252a34` |
| Bouton lune/soleil | `.theme-toggle--icon` | bouton rond de 36 px à bordure fine, en haut à droite sur toutes les pages | idem |

## 5. Mise en page et mouvement

- Grands espaces blancs : 32 px sous l'en-tête de page, 24 px de marge intérieure dans les cartes.
- Largeur de lecture : 68 caractères pour le texte (`--measure`), 760 px pour la colonne de l'Assistant
  (`--reading-width`), 1180 px au maximum pour le contenu (`--content-width`).
- Grilles : `auto-fill` / `auto-fit` avec des colonnes d'au moins 14 à 17 rem, sur une seule colonne en mobile.
- Points de rupture testés : 360 px, 768 px, 1024 px (barre latérale) et bureau.
- Animations courtes (`--duration` 160 ms, `--duration-slow` 420 ms). Avec `prefers-reduced-motion`, elles sont
  ramenées à 0.

## 6. Thème

- Au premier chargement, l'application suit `prefers-color-scheme`.
- Le bouton lune/soleil mémorise le choix dans `localStorage` (clé `ai-study-assistant.theme`, accès dans un
  `try/catch`) et le pose en `data-theme` sur `<html>`.
- Pour éviter tout flash blanc, un script dans `index.html` applique le choix avant le premier rendu, et
  `<meta name="theme-color">` vaut `#ffffff` en clair et `#0c0e12` en sombre.
