import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService } from '../services/auth.service';

/** Routes où un 401 signifie « identifiants incorrects », pas « session expirée ». */
const AUTH_ROUTES = ['/auth/login', '/auth/register'];

/**
 * Ajoute « Authorization: Bearer <jeton> » aux requêtes vers l'API
 * et renvoie vers /login quand le backend répond 401 (jeton absent, invalide ou expiré).
 * À placer APRÈS errorInterceptor, pour voir la HttpErrorResponse d'origine.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const token = auth.token();
  const toApi = req.url.startsWith(environment.apiUrl);

  const request = toApi && token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(request).pipe(
    catchError((err: unknown) => {
      const isAuthRoute = AUTH_ROUTES.some((route) => req.url.startsWith(environment.apiUrl + route));
      if (toApi && !isAuthRoute && err instanceof HttpErrorResponse && err.status === 401) {
        auth.logout(router.url);
      }
      return throwError(() => err);
    }),
  );
};
