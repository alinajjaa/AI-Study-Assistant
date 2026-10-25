import { Component, computed, input } from '@angular/core';

/** Squelette de chargement : lignes de texte ou rangées de liste. Annoncé « Chargement » aux lecteurs d'écran. */
@Component({
  selector: 'app-skeleton',
  template: `
    <span class="sr-only">{{ label() }}</span>
    <div class="skeleton-group" [class.skeleton-group--rows]="variant() === 'rows'" aria-hidden="true">
      @for (width of widths(); track $index) {
        @if (variant() === 'rows') {
          <div class="row">
            <span class="skeleton dot"></span>
            <span class="skeleton" [style.width.%]="width"></span>
          </div>
        } @else {
          <span class="skeleton" [style.width.%]="width"></span>
        }
      }
    </div>
  `,
  styles: `
    :host {
      display: block;
    }
    .skeleton-group {
      display: grid;
      gap: var(--space-3);
    }
    .skeleton-group--rows {
      gap: var(--space-4);
    }
    .row {
      display: flex;
      align-items: center;
      gap: var(--space-3);
    }
    .dot {
      width: 1.25rem;
      height: 1.25rem;
      border-radius: var(--radius-sm);
    }
  `,
  host: { role: 'status' },
})
export class Skeleton {
  readonly lines = input(3);
  readonly variant = input<'text' | 'rows'>('text');
  readonly label = input('Chargement…');
  /** Largeurs variées : un bloc de texte qui ressemble à du texte. */
  protected readonly widths = computed(() =>
    Array.from({ length: this.lines() }, (_, i) => [92, 78, 85, 64, 88, 70][i % 6]),
  );
}
