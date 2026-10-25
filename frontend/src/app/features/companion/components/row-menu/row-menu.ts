import { Component, DestroyRef, ElementRef, Injector, afterNextRender, inject, input, output, signal } from '@angular/core';

export interface RowMenuItem {
  id: string;
  label: string;
  danger?: boolean;
  disabled?: boolean;
}

/** Hauteur approximative d'une entrée, pour ouvrir le menu vers le haut s'il manque de place en bas. */
const ITEM_HEIGHT = 40;
const MENU_PADDING = 10;

/**
 * Bouton « ⋯ » d'une ligne (visible au survol, au focus clavier, toujours sur écran tactile) : ouvre un petit
 * menu d'actions, en position fixe pour ne jamais être coupé par la liste qui défile.
 * Clavier : flèches haut/bas, Début/Fin, Échap (rend le focus au bouton), Tab ferme le menu.
 */
@Component({
  selector: 'app-row-menu',
  templateUrl: './row-menu.html',
  styleUrl: './row-menu.css',
  host: {
    '[class.row-menu--open]': 'open()',
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'onEscape($event)',
  },
})
export class RowMenu {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  /** Libellé accessible du bouton et du menu (« Actions pour … »). */
  readonly label = input.required<string>();
  readonly items = input.required<RowMenuItem[]>();
  readonly pick = output<string>();

  protected readonly open = signal(false);
  /**
   * Position du menu (fixe, en pixels depuis le haut et la droite de la fenêtre). Toujours par le haut : sous
   * 1024 px, la barre du haut (floutée) sert de repère au position: fixed, et elle commence en haut de l'écran.
   */
  protected readonly position = signal({ top: 0, right: 0 });

  private readonly onScroll = (event: Event) => {
    // Défilement de la liste : le menu fixe ne suivrait plus sa ligne, on le ferme
    if (!(event.target instanceof Node && this.host.nativeElement.contains(event.target))) {
      this.close(false);
    }
  };

  constructor() {
    inject(DestroyRef).onDestroy(() => document.removeEventListener('scroll', this.onScroll, true));
  }

  protected toggle(): void {
    if (this.open()) {
      this.close(false);
      return;
    }
    const rect = this.host.nativeElement.querySelector('.more')!.getBoundingClientRect();
    const height = this.items().length * ITEM_HEIGHT + MENU_PADDING;
    const below = rect.bottom + 2 + height <= window.innerHeight;
    this.position.set({
      top: below ? rect.bottom + 2 : Math.max(4, rect.top - 2 - height),
      right: Math.max(4, window.innerWidth - rect.right),
    });
    this.open.set(true);
    document.addEventListener('scroll', this.onScroll, true);
    afterNextRender(() => this.menuItems().find((b) => !b.disabled)?.focus(), { injector: this.injector });
  }

  protected choose(item: RowMenuItem): void {
    this.close(true);
    this.pick.emit(item.id);
  }

  protected onMenuKeydown(event: KeyboardEvent): void {
    const buttons = this.menuItems().filter((b) => !b.disabled);
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    let next: HTMLButtonElement | undefined;
    if (event.key === 'ArrowDown') {
      next = buttons[(index + 1) % buttons.length];
    } else if (event.key === 'ArrowUp') {
      next = buttons[(index - 1 + buttons.length) % buttons.length];
    } else if (event.key === 'Home') {
      next = buttons[0];
    } else if (event.key === 'End') {
      next = buttons[buttons.length - 1];
    } else if (event.key === 'Tab') {
      this.close(false);
      return;
    }
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  protected onEscape(event: Event): void {
    if (this.open()) {
      // Échap ferme d'abord ce menu, pas le tiroir qui le contient
      event.stopPropagation();
      this.close(true);
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) {
      this.close(false);
    }
  }

  private close(refocus: boolean): void {
    this.open.set(false);
    document.removeEventListener('scroll', this.onScroll, true);
    if (refocus) {
      this.host.nativeElement.querySelector<HTMLButtonElement>('.more')?.focus();
    }
  }

  private menuItems(): HTMLButtonElement[] {
    return [...this.host.nativeElement.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')];
  }
}
