import { Component, ElementRef, Injector, afterNextRender, computed, inject, input, signal, viewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { ShellService } from '../../core/services/shell.service';
import { ThemeService } from '../../core/services/theme.service';
import { Icon } from '../../shared/components/icon/icon';

/** Prénom affiché à partir de l'email (« jean.dupont@… » → « Jean »). */
export function displayName(email: string): string {
  const local = email.split('@')[0] ?? '';
  const first = local.split(/[._\-+\d]/).find((part) => part.length > 0) ?? local;
  return first ? first.charAt(0).toUpperCase() + first.slice(1).toLowerCase() : email;
}

/**
 * Compte, en bas de la barre latérale : avatar + prénom, menu « Profil et statistiques », « Thème »,
 * « Déconnexion ». Menu en position fixe (au-dessus du bouton, ou à sa droite dans le rail) : jamais coupé.
 * Clavier : flèches, Début/Fin, Échap (rend le focus au bouton), Tab ferme le menu.
 */
@Component({
  selector: 'app-account-menu',
  imports: [RouterLink, Icon],
  templateUrl: './account-menu.html',
  styleUrl: './account-menu.css',
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'onEscape($event)',
  },
})
export class AccountMenu {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
  private readonly shell = inject(ShellService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);
  private readonly trigger = viewChild.required<ElementRef<HTMLButtonElement>>('trigger');

  /** Barre repliée en rail : le menu s'ouvre à droite du bouton. */
  readonly collapsed = input(false);

  protected readonly open = signal(false);
  /**
   * Position fixe du menu (null = au-dessus du bouton, en absolu : sous 1024 px, la barre du haut floutée
   * sert de repère au position: fixed).
   */
  protected readonly position = signal<{ left: number; bottom: number; width: number | null } | null>(null);
  protected readonly email = computed(() => this.auth.user()?.email ?? '');
  protected readonly name = computed(() => (this.email() ? displayName(this.email()) : 'Mon compte'));
  protected readonly initial = computed(() => this.name().charAt(0).toUpperCase() || '?');
  protected readonly themeLabel = computed(() => (this.theme.theme() === 'dark' ? 'Thème clair' : 'Thème sombre'));

  protected toggle(): void {
    if (this.open()) {
      this.close(false);
      return;
    }
    const rect = this.trigger().nativeElement.getBoundingClientRect();
    const sidebar = window.matchMedia?.('(min-width: 1024px)').matches ?? false;
    this.position.set(
      !sidebar
        ? null
        : this.collapsed()
          ? { left: rect.right + 8, bottom: window.innerHeight - rect.bottom, width: null }
          : { left: rect.left, bottom: window.innerHeight - rect.top + 6, width: rect.width },
    );
    this.open.set(true);
    afterNextRender(() => this.items()[0]?.focus(), { injector: this.injector });
  }

  protected toggleTheme(): void {
    // Le menu reste ouvert : le changement se voit tout de suite
    this.theme.toggle();
  }

  protected goToProfile(): void {
    this.close(false);
    this.shell.closeMenu();
  }

  protected logout(): void {
    this.close(false);
    this.shell.closeMenu();
    this.auth.logout();
  }

  protected onMenuKeydown(event: KeyboardEvent): void {
    const items = this.items();
    const index = items.indexOf(document.activeElement as HTMLElement);
    let next: HTMLElement | undefined;
    if (event.key === 'ArrowDown') {
      next = items[(index + 1) % items.length];
    } else if (event.key === 'ArrowUp') {
      next = items[(index - 1 + items.length) % items.length];
    } else if (event.key === 'Home') {
      next = items[0];
    } else if (event.key === 'End') {
      next = items[items.length - 1];
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
    if (refocus) {
      this.trigger().nativeElement.focus();
    }
  }

  private items(): HTMLElement[] {
    return [...this.host.nativeElement.querySelectorAll<HTMLElement>('[role="menuitem"]')];
  }
}
