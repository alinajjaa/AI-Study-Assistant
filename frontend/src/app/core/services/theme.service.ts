import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export const THEME_KEY = 'ai-study-assistant.theme';

export type ThemePreference = 'system' | 'light' | 'dark';

function readPreference(): ThemePreference {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === 'light' || value === 'dark' ? value : 'system';
  } catch {
    return 'system';
  }
}

/**
 * Thème clair / sombre. Par défaut, celui du système (prefers-color-scheme) ; un choix explicite est mémorisé et
 * posé en data-theme sur <html> (les jetons de styles.css suivent). index.html l'applique avant le démarrage.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly media = this.document.defaultView?.matchMedia?.('(prefers-color-scheme: dark)') ?? null;
  private readonly systemDark = signal(this.media?.matches ?? false);
  private readonly _preference = signal<ThemePreference>(readPreference());

  readonly preference = this._preference.asReadonly();
  /** Thème réellement affiché. */
  readonly theme = computed<'light' | 'dark'>(() => {
    const preference = this._preference();
    if (preference === 'system') {
      return this.systemDark() ? 'dark' : 'light';
    }
    return preference;
  });

  constructor() {
    this.media?.addEventListener?.('change', (event) => this.systemDark.set(event.matches));
    this.apply(this._preference());
  }

  /** Bascule clair ↔ sombre (le choix est mémorisé). */
  toggle(): void {
    this.set(this.theme() === 'dark' ? 'light' : 'dark');
  }

  set(preference: ThemePreference): void {
    this._preference.set(preference);
    try {
      if (preference === 'system') {
        localStorage.removeItem(THEME_KEY);
      } else {
        localStorage.setItem(THEME_KEY, preference);
      }
    } catch {
      // Stockage indisponible : le choix vaut pour cet onglet seulement
    }
    this.apply(preference);
  }

  private apply(preference: ThemePreference): void {
    const root = this.document.documentElement;
    if (preference === 'system') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', preference);
    }
  }
}
