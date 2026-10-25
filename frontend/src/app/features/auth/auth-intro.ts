import { Component } from '@angular/core';

/** Accroche des pages de connexion et d'inscription : étiquette, titre et présentation en une phrase. */
@Component({
  selector: 'app-auth-intro',
  template: `
    <div class="intro">
      <p class="kicker">Tuteur · Examens · Flashcards · Résumés</p>
      <h1 class="intro__title">
        Ton cours, expliqué, résumé
        <span class="intro__accent title-accent">et transformé en entraînement.</span>
      </h1>
      <p class="intro__lede">
        Importe un PDF de cours : l'assistant répond uniquement à partir de son contenu et cite ses pages,
        pour que tu puisses toujours vérifier.
      </p>
    </div>
  `,
  styles: `
    .intro {
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
    }
    .intro__title {
      max-width: 14ch;
      font-family: var(--font-display);
      font-size: clamp(2.4rem, 1.3rem + 3.4vw, 4.25rem);
      font-weight: 700;
      line-height: 1.02;
      letter-spacing: -0.035em;
      text-wrap: balance;
    }
    .intro__accent {
      display: block;
      margin-top: 0.06em;
      line-height: 1;
    }
    .intro__lede {
      margin: 0;
      max-width: 46ch;
      color: var(--text-muted);
      font-size: var(--text-lg);
      line-height: 1.6;
    }
  `,
})
export class AuthIntro {}
