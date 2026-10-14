import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from './core/services/auth.service';
import { Toasts } from './shared/components/toast/toast';

/** Menu principal (l'Assistant regroupe questions, résumés, quiz, flashcards et progrès). */
export const NAV_LINKS: readonly { path: string; label: string }[] = [
  { path: '/companion', label: 'Assistant' },
  { path: '/flashcards', label: 'Flashcards' },
  { path: '/summaries', label: 'Résumés' },
  { path: '/exams', label: 'Mes examens' },
  { path: '/profile', label: 'Mon profil' },
];

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Toasts],
  templateUrl: './app.html',
  styleUrl: './app.css',
  host: { '(document:keydown.escape)': 'closeMenu()' },
})
export class App {
  protected readonly auth = inject(AuthService);
  protected readonly links = NAV_LINKS;
  /** Menu compact ouvert (écrans de moins de 1280 px). */
  protected readonly menuOpen = signal(false);

  constructor() {
    this.auth.restoreSession();
    inject(Router)
      .events.pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.closeMenu());
  }

  protected toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }

  protected closeMenu(): void {
    this.menuOpen.set(false);
  }

  protected logout(): void {
    this.closeMenu();
    this.auth.logout();
  }
}
