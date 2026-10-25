import { Component, DestroyRef, ElementRef, computed, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from './core/services/auth.service';
import { ShellService } from './core/services/shell.service';
import { ThemeService } from './core/services/theme.service';
import { ConfirmDialog } from './shared/components/confirm-dialog/confirm-dialog';
import { Icon } from './shared/components/icon/icon';
import { Toasts } from './shared/components/toast/toast';
import { NavTabs } from './shell/nav-tabs/nav-tabs';
import { ShellSidebar } from './shell/sidebar/shell-sidebar';

/** En dessous : barre du haut et menu en tiroir, pas de rail. */
const COMPACT_QUERY = '(max-width: 1023.98px)';

/** Champ de saisie : Ctrl+B y garde son comportement habituel. */
function isEditable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, Toasts, ConfirmDialog, Icon, ShellSidebar, NavTabs],
  templateUrl: './app.html',
  styleUrls: ['./app.css', './app-sidebar.css'],
  host: {
    '(document:keydown.escape)': 'closeMenu()',
    '(document:keydown)': 'onShortcut($event)',
    '[class.app--signed-in]': 'auth.isAuthenticated()',
    '[class.app--collapsed]': 'collapsed()',
  },
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly theme = inject(ThemeService);
  protected readonly shell = inject(ShellService);
  private readonly header = viewChild.required<ElementRef<HTMLElement>>('header');
  private readonly sidebarToggle = viewChild<ElementRef<HTMLButtonElement>>('sidebarToggle');

  /** Menu en tiroir ouvert (écrans de moins de 1024 px). */
  protected readonly menuOpen = this.shell.menuOpen;
  /** Moins de 1024 px : pas de rail, le menu est un tiroir. */
  private readonly compact = signal(false);
  /** Barre repliée en rail (uniquement à partir de 1024 px). */
  protected readonly collapsed = computed(() => this.auth.isAuthenticated() && !this.compact() && this.shell.collapsed());
  protected readonly shortcut = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform ?? '') ? '⌘B' : 'Ctrl+B';
  /** Info-bulle des icônes du rail (position fixe : jamais coupée par la barre). */
  protected readonly tip = signal<{ text: string; top: number; left: number } | null>(null);
  protected readonly themeLabel = computed(() =>
    this.theme.theme() === 'dark' ? 'Passer en mode clair' : 'Passer en mode sombre',
  );

  constructor() {
    this.auth.restoreSession();
    this.watchCompact();
    inject(Router)
      .events.pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.closeMenu());
  }

  private watchCompact(): void {
    const media = typeof window !== 'undefined' ? window.matchMedia?.(COMPACT_QUERY) : undefined;
    if (!media) {
      return;
    }
    this.compact.set(media.matches);
    const onChange = (event: MediaQueryListEvent) => this.compact.set(event.matches);
    media.addEventListener('change', onChange);
    inject(DestroyRef).onDestroy(() => media.removeEventListener('change', onChange));
  }

  protected toggleMenu(): void {
    this.shell.toggleMenu();
  }

  protected closeMenu(): void {
    this.shell.closeMenu();
  }

  /**
   * Replie ou déplie ; le focus resté dans une partie masquée par le rail (tout ce qui n'est pas une icône du
   * rail) revient sur le bouton de bascule.
   */
  protected toggleCollapsed(): void {
    const collapsing = !this.shell.collapsed();
    this.shell.toggleCollapsed();
    this.tip.set(null);
    const active = document.activeElement;
    if (
      collapsing &&
      active instanceof HTMLElement &&
      this.header().nativeElement.contains(active) &&
      !active.matches('[data-tip]')
    ) {
      this.sidebarToggle()?.nativeElement.focus();
    }
  }

  /** Ctrl+B (⌘B sur Mac) : replie / déplie la barre, ou ouvre / ferme le tiroir sous 1024 px. */
  protected onShortcut(event: KeyboardEvent): void {
    if (
      !(event.ctrlKey || event.metaKey) ||
      event.altKey ||
      event.shiftKey ||
      event.key.toLowerCase() !== 'b' ||
      !this.auth.isAuthenticated() ||
      isEditable(event.target)
    ) {
      return;
    }
    event.preventDefault();
    if (this.compact()) {
      this.toggleMenu();
    } else {
      this.toggleCollapsed();
    }
  }

  /** Rail : flèches haut / bas, Début / Fin entre les icônes (en plus de Tab). */
  protected onRailKeydown(event: KeyboardEvent): void {
    if (!this.collapsed() || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      return;
    }
    const items = [...this.header().nativeElement.querySelectorAll<HTMLElement>('a[data-tip], button[data-tip]')].filter(
      (el) => el.offsetParent !== null && getComputedStyle(el).visibility !== 'hidden',
    );
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index === -1) {
      return;
    }
    const last = items.length - 1;
    const next =
      event.key === 'Home' ? 0 : event.key === 'End' ? last : event.key === 'ArrowDown' ? Math.min(index + 1, last) : Math.max(index - 1, 0);
    event.preventDefault();
    items[next].focus();
  }

  protected showTip(event: Event): void {
    const target = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-tip]') : null;
    if (!target || (!this.collapsed() && !target.hasAttribute('data-tip-always')) || this.compact()) {
      this.tip.set(null);
      return;
    }
    const rect = target.getBoundingClientRect();
    this.tip.set({ text: target.dataset['tip'] ?? '', top: rect.top + rect.height / 2, left: rect.right + 8 });
  }

  protected hideTip(): void {
    this.tip.set(null);
  }

}
