import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FlashcardsPayload } from '../../../../core/models/companion.models';

const SHOWN_CONCEPTS = 6;

/** « Paquet de flashcards prêt → Réviser » : ouvre le paquet enregistré dans la page Flashcards. */
@Component({
  selector: 'app-flashcards-card',
  imports: [RouterLink],
  template: `
    <article class="deck">
      <span class="deck__icon" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" focusable="false">
          <rect x="3" y="6" width="14" height="14" rx="2" /><path d="M7 3h12a2 2 0 0 1 2 2v12" />
        </svg>
      </span>
      <div class="deck__body">
        <h3 class="deck__title">Paquet de {{ deck().card_count }} flashcards prêt</h3>
        <p class="hint">« {{ deck().course }} » · enregistré dans « Mes paquets »</p>
        @if (concepts().length) {
          <ul class="concepts" aria-label="Notions du paquet">
            @for (concept of concepts(); track $index) {
              <li class="concept">{{ concept }}</li>
            }
            @if (more() > 0) {
              <li class="concept concept--more">+{{ more() }}</li>
            }
          </ul>
        }
      </div>
      <a class="btn btn--sm deck__action" routerLink="/flashcards" [queryParams]="{ course: deck().course, deck: deck().deck_id }">
        Réviser
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      </a>
    </article>
  `,
  styles: `
    .deck {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-4);
      padding: var(--space-4) var(--space-5);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
    }
    .deck__icon {
      display: grid;
      place-items: center;
      width: 2.6rem;
      height: 2.6rem;
      border-radius: var(--radius);
      background: var(--accent-soft);
      color: var(--accent);
    }
    .deck__body {
      flex: 1;
      min-width: 12rem;
    }
    .deck__title {
      font-size: var(--text-lg);
    }
    .deck__body .hint {
      margin: var(--space-1) 0 0;
    }
    .concepts {
      list-style: none;
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-1);
      margin: var(--space-3) 0 0;
      padding: 0;
    }
    .concept {
      padding: 0 var(--space-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-pill);
      font-size: var(--text-xs);
      color: var(--text-muted);
    }
    .concept--more {
      font-weight: 600;
    }
    .deck__action {
      text-decoration: none;
    }
  `,
})
export class FlashcardsCard {
  readonly deck = input.required<FlashcardsPayload>();

  protected readonly concepts = computed(() => this.deck().concepts.slice(0, SHOWN_CONCEPTS));
  protected readonly more = computed(() => this.deck().concepts.length - SHOWN_CONCEPTS);
}
