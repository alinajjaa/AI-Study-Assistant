import { Injectable, signal } from '@angular/core';

/** Clé localStorage de l'état replié de la barre latérale (à partir de 1024 px). */
export const SHELL_COLLAPSED_KEY = 'ai-study-assistant.shell.collapsed';

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(SHELL_COLLAPSED_KEY) === '1';
  } catch {
    // Stockage indisponible (navigation privée…) : barre ouverte
    return false;
  }
}

/**
 * État d'interface du shell : barre latérale repliée en rail (à partir de 1024 px), menu en tiroir (moins de
 * 1024 px), et demande de focus de la zone de saisie de l'Assistant. Aucune donnée métier.
 */
@Injectable({ providedIn: 'root' })
export class ShellService {
  /** Menu en tiroir ouvert (écrans de moins de 1024 px). */
  readonly menuOpen = signal(false);
  /** Barre latérale repliée en rail d'icônes (à partir de 1024 px), mémorisé. */
  readonly collapsed = signal(readCollapsed());
  /** « Nouvelle conversation » (barre latérale) : l'Assistant place le focus dans sa saisie, puis l'efface. */
  readonly composerFocusRequest = signal(false);

  toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }

  closeMenu(): void {
    this.menuOpen.set(false);
  }

  toggleCollapsed(): void {
    this.setCollapsed(!this.collapsed());
  }

  requestComposerFocus(): void {
    this.composerFocusRequest.set(true);
  }

  /** Déplie la barre (action du rail qui mène à la recherche). */
  expand(): void {
    this.setCollapsed(false);
  }

  private setCollapsed(collapsed: boolean): void {
    this.collapsed.set(collapsed);
    try {
      localStorage.setItem(SHELL_COLLAPSED_KEY, collapsed ? '1' : '0');
    } catch {
      // L'état reste valable pour la session
    }
  }
}
