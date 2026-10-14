import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, map, tap } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthResponse, Level, User } from '../models/auth.models';

export const TOKEN_KEY = 'ai-study-assistant.token';

function readToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string | null): void {
  try {
    if (token === null) {
      localStorage.removeItem(TOKEN_KEY);
    } else {
      localStorage.setItem(TOKEN_KEY, token);
    }
  } catch {
    // Stockage indisponible (navigation privée…) : la session ne dure que le temps de l'onglet.
  }
}

/** Compte de l'étudiant connecté et jeton JWT (gardé dans localStorage). */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly apiUrl = environment.apiUrl;

  private readonly _token = signal<string | null>(readToken());
  private readonly _user = signal<User | null>(null);

  readonly token = this._token.asReadonly();
  /** null tant que /api/me n'a pas répondu. */
  readonly user = this._user.asReadonly();
  readonly isAuthenticated = computed(() => this._token() !== null);

  /**
   * Page rechargée avec un jeton : récupère le compte (un jeton expiré renverra 401 → /login).
   * Appelé par le shell de l'application, pas par le constructeur : l'intercepteur injecte ce service.
   */
  restoreSession(): void {
    if (this._token() !== null && this._user() === null) {
      this.loadMe().subscribe({ error: () => undefined });
    }
  }

  login(email: string, password: string): Observable<User> {
    return this.http
      .post<AuthResponse>(`${this.apiUrl}/auth/login`, { email, password })
      .pipe(map((res) => this.startSession(res)));
  }

  register(email: string, password: string, level: Level): Observable<User> {
    return this.http
      .post<AuthResponse>(`${this.apiUrl}/auth/register`, { email, password, level })
      .pipe(map((res) => this.startSession(res)));
  }

  loadMe(): Observable<User> {
    return this.http.get<User>(`${this.apiUrl}/me`).pipe(tap((user) => this._user.set(user)));
  }

  updateLevel(level: Level): Observable<User> {
    return this.http.patch<User>(`${this.apiUrl}/me`, { level }).pipe(tap((user) => this._user.set(user)));
  }

  /** Oublie le jeton et renvoie vers /login (avec la page à rouvrir après reconnexion). */
  logout(returnUrl?: string): void {
    this.clearSession();
    const queryParams = returnUrl && returnUrl !== '/' && !returnUrl.startsWith('/login') ? { returnUrl } : {};
    void this.router.navigate(['/login'], { queryParams });
  }

  clearSession(): void {
    writeToken(null);
    this._token.set(null);
    this._user.set(null);
  }

  private startSession(res: AuthResponse): User {
    writeToken(res.access_token);
    this._token.set(res.access_token);
    this._user.set(res.user);
    return res.user;
  }
}
