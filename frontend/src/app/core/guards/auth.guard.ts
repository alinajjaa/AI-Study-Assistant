import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/** Pages réservées aux étudiants connectés : sinon, redirection vers /login. */
export const authGuard: CanActivateFn = (_route, state) => {
  const auth = inject(AuthService);
  if (auth.isAuthenticated()) {
    return true;
  }
  const queryParams = state.url && state.url !== '/' ? { returnUrl: state.url } : {};
  return inject(Router).createUrlTree(['/login'], { queryParams });
};

/** /login et /register : un étudiant déjà connecté va directement au tuteur. */
export const guestGuard: CanActivateFn = () =>
  inject(AuthService).isAuthenticated() ? inject(Router).createUrlTree(['/tutor']) : true;
