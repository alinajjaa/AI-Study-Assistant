import { Component, input } from '@angular/core';
import { Icon, IconName } from '../icon/icon';

/** État vide utile : ce qui manque, pourquoi, et l'action pour commencer (contenu projeté : boutons, liens). */
@Component({
  selector: 'app-empty-state',
  imports: [Icon],
  template: `
    <div class="empty" [class.empty--compact]="compact()">
      <span class="empty__icon"><app-icon [name]="icon()" [size]="compact() ? 20 : 26" /></span>
      <div class="empty__body">
        <p class="empty__title">{{ title() }}</p>
        @if (text()) {
          <p class="empty__text">{{ text() }}</p>
        }
        <div class="empty__actions"><ng-content /></div>
      </div>
    </div>
  `,
  styles: `
    .empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-3);
      padding: var(--space-8) var(--space-4);
      text-align: center;
    }
    .empty__icon {
      display: grid;
      place-items: center;
      width: 3.5rem;
      height: 3.5rem;
      border-radius: var(--radius);
      background: var(--accent-soft);
      color: var(--accent);
    }
    .empty__body {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: var(--space-1);
    }
    .empty__title {
      margin: 0;
      font-family: var(--font-heading);
      font-size: var(--text-lg);
      font-weight: 600;
      color: var(--text);
    }
    .empty__text {
      margin: 0;
      max-width: 42ch;
      color: var(--text-muted);
      font-size: var(--text-sm);
    }
    .empty__actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: var(--space-2);
      margin-top: var(--space-2);
    }
    .empty__actions:empty {
      display: none;
    }
    .empty--compact {
      flex-direction: row;
      align-items: flex-start;
      padding: var(--space-3) 0;
      text-align: left;
    }
    .empty--compact .empty__icon {
      width: 2.5rem;
      height: 2.5rem;
      border-radius: var(--radius-sm);
    }
    .empty--compact .empty__body {
      align-items: flex-start;
    }
    .empty--compact .empty__title {
      font-family: var(--font-sans);
      font-size: var(--text-sm);
    }
    .empty--compact .empty__actions {
      justify-content: flex-start;
      margin-top: var(--space-1);
    }
  `,
})
export class EmptyState {
  readonly icon = input<IconName>('book');
  readonly title = input.required<string>();
  readonly text = input('');
  readonly compact = input(false);
}
