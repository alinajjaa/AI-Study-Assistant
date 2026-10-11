import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'tutor' },
  {
    path: 'tutor',
    title: 'Tuteur de cours · AI Study Assistant',
    loadComponent: () => import('./features/tutor/tutor.page').then((m) => m.TutorPage),
  },
  // Futures fonctionnalités (quiz, flashcards…) : ajouter leurs routes ici.
  { path: '**', redirectTo: 'tutor' },
];
