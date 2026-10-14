import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'tutor' },
  {
    path: 'login',
    title: 'Connexion · AI Study Assistant',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'register',
    title: 'Créer un compte · AI Study Assistant',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register.page').then((m) => m.RegisterPage),
  },
  {
    path: 'tutor',
    title: 'Tuteur de cours · AI Study Assistant',
    canActivate: [authGuard],
    loadComponent: () => import('./features/tutor/tutor.page').then((m) => m.TutorPage),
  },
  {
    path: 'flashcards',
    title: 'Flashcards · AI Study Assistant',
    canActivate: [authGuard],
    loadComponent: () => import('./features/flashcards/flashcards.page').then((m) => m.FlashcardsPage),
  },
  {
    path: 'summaries',
    title: 'Résumés · AI Study Assistant',
    canActivate: [authGuard],
    loadComponent: () => import('./features/summaries/summaries.page').then((m) => m.SummariesPage),
  },
  {
    path: 'exams',
    title: 'Mes examens · AI Study Assistant',
    canActivate: [authGuard],
    loadComponent: () => import('./features/exams/exams.page').then((m) => m.ExamsPage),
  },
  {
    path: 'profile',
    title: 'Mon profil · AI Study Assistant',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile.page').then((m) => m.ProfilePage),
  },
  // Futures fonctionnalités : ajouter leurs routes ici (avec canActivate: [authGuard]).
  { path: '**', redirectTo: 'tutor' },
];
