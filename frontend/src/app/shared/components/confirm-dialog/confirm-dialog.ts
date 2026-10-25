import { Component, DestroyRef, ElementRef, effect, inject, viewChild } from '@angular/core';
import { Icon } from '../icon/icon';
import { ConfirmService } from './confirm.service';

/** Boîte de confirmation modale (<dialog> natif : focus piégé, Échap = annuler). À placer une fois dans le shell. */
@Component({
  selector: 'app-confirm-dialog',
  imports: [Icon],
  template: `
    <dialog
      #dialog
      class="confirm"
      aria-labelledby="confirm-title"
      aria-describedby="confirm-message"
      (cancel)="$event.preventDefault(); service.answer(false)"
      (click)="onBackdrop($event)"
    >
      @if (service.request(); as request) {
        <div class="panel">
          <span class="icon" [class.icon--danger]="request.danger">
            <app-icon [name]="request.danger ? 'trash' : 'alert'" [size]="20" />
          </span>
          <div class="body">
            <h2 id="confirm-title" class="title">{{ request.title }}</h2>
            <p id="confirm-message" class="message">{{ request.message }}</p>
          </div>
          <div class="actions">
            <button type="button" class="btn btn--ghost" (click)="service.answer(false)">Annuler</button>
            <button
              #confirmButton
              type="button"
              class="btn"
              [class.btn--danger]="request.danger"
              (click)="service.answer(true)"
            >
              {{ request.confirmLabel ?? 'Confirmer' }}
            </button>
          </div>
        </div>
      }
    </dialog>
  `,
  styles: `
    .confirm {
      width: min(28rem, calc(100vw - 2rem));
      padding: 0;
      border: 1px solid var(--border);
      border-radius: var(--radius-card);
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow-lg);
    }
    .confirm::backdrop {
      background: var(--overlay);
    }
    .confirm[open] {
      animation: appear var(--duration-slow) var(--ease);
    }
    @keyframes appear {
      from {
        opacity: 0;
        transform: translateY(8px) scale(0.98);
      }
    }
    .panel {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: var(--space-4);
      padding: var(--space-6);
    }
    .icon {
      display: grid;
      place-items: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: var(--radius-sm);
      background: var(--warning-soft);
      color: var(--warning);
    }
    .icon--danger {
      background: var(--danger-soft);
      color: var(--danger);
    }
    .title {
      font-size: var(--text-lg);
    }
    .message {
      margin: var(--space-2) 0 0;
      color: var(--text-muted);
      font-size: var(--text-sm);
      white-space: pre-line;
    }
    .actions {
      grid-column: 1 / -1;
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: var(--space-2);
    }
  `,
})
export class ConfirmDialog {
  protected readonly service = inject(ConfirmService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly confirmButton = viewChild<ElementRef<HTMLButtonElement>>('confirmButton');

  constructor() {
    this.service.attach();
    inject(DestroyRef).onDestroy(() => this.service.detach());
    effect(() => {
      const dialog = this.dialog().nativeElement;
      const open = this.service.request() !== null;
      if (open && !dialog.open) {
        dialog.showModal?.();
        // Action irréversible : le focus va sur « Annuler » par défaut (premier bouton), sinon sur Confirmer
        queueMicrotask(() => {
          const request = this.service.request();
          if (request && !request.danger) {
            this.confirmButton()?.nativeElement.focus();
          }
        });
      } else if (!open && dialog.open) {
        dialog.close();
      }
    });
  }

  /** Clic sur le fond (hors du panneau) : annuler. */
  protected onBackdrop(event: MouseEvent): void {
    if (event.target === this.dialog().nativeElement) {
      this.service.answer(false);
    }
  }
}
