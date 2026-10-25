import { Component, input, output } from '@angular/core';
import { Icon } from '../icon/icon';

/**
 * Erreur d'API : le message en français (déjà traduit par l'intercepteur, jamais de JSON brut) et un bouton
 * « Réessayer » qui relance l'action. Sans abonné à (retry), le bouton n'est pas affiché.
 */
@Component({
  selector: 'app-error-state',
  imports: [Icon],
  template: `
    <div class="error" role="alert">
      <app-icon name="error" [size]="20" />
      <div class="error__body">
        <p class="error__title">{{ title() }}</p>
        <p class="error__message">{{ message() }}</p>
      </div>
      @if (retryable()) {
        <button type="button" class="btn btn--ghost btn--sm error__retry" [disabled]="busy()" (click)="retry.emit()">
          <app-icon name="retry" [size]="14" [stroke]="2" />
          {{ busy() ? 'Nouvel essai…' : retryLabel() }}
        </button>
      }
      @if (dismissible()) {
        <button type="button" class="icon-btn error__close" aria-label="Fermer le message d'erreur" (click)="dismiss.emit()">
          <app-icon name="close" [size]="16" [stroke]="2" />
        </button>
      }
    </div>
  `,
  styles: `
    .error {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: var(--space-3);
      padding: var(--space-3) var(--space-4);
      border: 1px solid color-mix(in srgb, var(--danger) 30%, transparent);
      border-radius: var(--radius-sm);
      background: var(--danger-soft);
      color: var(--danger);
    }
    .error__body {
      flex: 1;
      min-width: 12rem;
    }
    .error__title {
      margin: 0;
      font-weight: 600;
      font-size: var(--text-sm);
    }
    .error__message {
      margin: var(--space-1) 0 0;
      font-size: var(--text-sm);
      color: var(--text);
      overflow-wrap: anywhere;
    }
    .error__retry {
      align-self: center;
    }
    .error__close {
      margin: -0.35rem -0.5rem 0 0;
      color: var(--danger);
    }
  `,
})
export class ErrorState {
  readonly message = input.required<string>();
  readonly title = input('Une erreur est survenue');
  readonly retryLabel = input('Réessayer');
  readonly retryable = input(true);
  readonly dismissible = input(false);
  readonly busy = input(false);
  readonly retry = output<void>();
  readonly dismiss = output<void>();
}
