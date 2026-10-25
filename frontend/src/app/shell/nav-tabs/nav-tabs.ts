import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

/** Onglets de navigation principale (le profil est dans le menu du compte, en bas de la barre latérale). */
export const NAV_LINKS: readonly { path: string; label: string }[] = [
  { path: '/companion', label: 'Assistant' },
  { path: '/flashcards', label: 'Flashcards' },
  { path: '/summaries', label: 'Résumés' },
  { path: '/exams', label: 'Examens' },
  { path: '/courses', label: 'Mes cours' },
];

/** Barre d'onglets discrète en haut de la zone principale ; défile horizontalement sur petit écran. */
@Component({
  selector: 'app-nav-tabs',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './nav-tabs.html',
  styleUrl: './nav-tabs.css',
})
export class NavTabs {
  protected readonly links = NAV_LINKS;
}
