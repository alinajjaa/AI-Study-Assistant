import { Component } from '@angular/core';
import { Icon } from '../../shared/components/icon/icon';

interface Feature {
  title: string;
  text: string;
}

const FEATURES: readonly Feature[] = [
  {
    title: 'Tuteur',
    text: 'Pose ta question : la réponse vient de ton cours, avec la page de chaque information.',
  },
  {
    title: 'Examens',
    text: 'Un sujet noté sur 20 en PDF, avec QCM, vrai/faux, questions courtes et corrigé.',
  },
  {
    title: 'Flashcards',
    text: 'Les notions clés en cartes recto-verso, et tes points faibles suivis au fil des révisions.',
  },
  {
    title: 'Résumés',
    text: "Tout le cours partie par partie, ou un thème expliqué à ton niveau, pages à l'appui.",
  },
];

/** Fonctions de l'application et engagement de confidentialité, sous le formulaire de connexion ou d'inscription. */
@Component({
  selector: 'app-auth-features',
  imports: [Icon],
  template: `
    <section class="features" aria-labelledby="features-title">
      <h2 id="features-title" class="kicker">Ce que tu peux faire</h2>

      <ol class="features__list">
        @for (feature of features; track feature.title; let i = $index) {
          <li class="feature">
            <span class="feature__num" aria-hidden="true">0{{ i + 1 }}</span>
            <p class="feature__title">{{ feature.title }}</p>
            <p class="feature__text">{{ feature.text }}</p>
          </li>
        }
      </ol>

      <div class="trust">
        <app-icon name="shield" [size]="20" />
        <p class="trust__text">
          <strong>Tes données restent à toi.</strong>
          Tes cours sont privés : personne d'autre ne les voit. Emails et numéros de téléphone sont masqués avant
          tout envoi au modèle, et les statistiques d'évaluation ne contiennent aucune donnée personnelle.
        </p>
      </div>
    </section>
  `,
  styles: `
    .features {
      display: flex;
      flex-direction: column;
      gap: var(--space-8);
    }
    .features__list {
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
      gap: var(--space-8) var(--space-6);
      margin: 0;
      padding: 0;
    }
    .feature {
      display: flex;
      flex-direction: column;
      gap: var(--space-2);
      padding-top: var(--space-5);
      border-top: 1px solid var(--border-strong);
      transition: border-color var(--duration) var(--ease);
    }
    .feature:hover {
      border-top-color: var(--text);
    }
    .feature__num {
      font-family: var(--font-label);
      font-size: var(--text-xs);
      letter-spacing: 0.12em;
      color: var(--text-muted);
    }
    .feature__title {
      margin: 0;
      font-family: var(--font-display);
      font-size: var(--text-xl);
      font-weight: 700;
      letter-spacing: -0.02em;
    }
    .feature__text {
      margin: 0;
      color: var(--text-muted);
      font-size: var(--text-sm);
      line-height: 1.6;
    }
    .trust {
      display: flex;
      align-items: flex-start;
      gap: var(--space-3);
      padding: var(--space-5) var(--space-6);
      border-radius: var(--radius-lg);
      background: var(--surface-alt);
      color: var(--accent);
    }
    .trust__text {
      margin: 0;
      max-width: 90ch;
      color: var(--text-muted);
      font-size: var(--text-sm);
      line-height: 1.6;
    }
    .trust__text strong {
      color: var(--text);
      font-weight: 600;
    }
  `,
})
export class AuthFeatures {
  protected readonly features = FEATURES;
}
