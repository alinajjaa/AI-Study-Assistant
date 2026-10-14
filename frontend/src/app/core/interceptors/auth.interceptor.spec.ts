import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthService, TOKEN_KEY } from '../services/auth.service';
import { authInterceptor } from './auth.interceptor';
import { errorInterceptor } from './error.interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(TOKEN_KEY, 'jeton-123');
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        provideHttpClient(withInterceptors([errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
  });

  afterEach(() => {
    backend.verify();
    localStorage.clear();
  });

  it("ajoute « Authorization: Bearer <jeton> » aux requêtes vers l'API", () => {
    http.get(`${environment.apiUrl}/courses`).subscribe();
    const req = backend.expectOne(`${environment.apiUrl}/courses`);
    expect(req.request.headers.get('Authorization')).toBe('Bearer jeton-123');
    req.flush([]);
  });

  it("n'envoie pas le jeton à un autre domaine", () => {
    http.get('https://exemple.org/data').subscribe();
    const req = backend.expectOne('https://exemple.org/data');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  it('sans jeton, la requête part sans en-tête', () => {
    auth.clearSession();
    http.get(`${environment.apiUrl}/courses`).subscribe();
    const req = backend.expectOne(`${environment.apiUrl}/courses`);
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush([]);
  });

  it('déconnecte et redirige vers /login sur une réponse 401', async () => {
    const logout = vi.spyOn(auth, 'logout');
    const request = firstValueFrom(http.get(`${environment.apiUrl}/courses`));
    backend
      .expectOne(`${environment.apiUrl}/courses`)
      .flush({ detail: 'Session expirée ou invalide : reconnecte-toi.' }, { status: 401, statusText: 'Unauthorized' });
    await expect(request).rejects.toThrow('Session expirée ou invalide : reconnecte-toi.');
    expect(logout).toHaveBeenCalled();
    expect(auth.isAuthenticated()).toBe(false);
  });

  it('ne déconnecte pas sur un 401 de /auth/login (identifiants incorrects)', async () => {
    const logout = vi.spyOn(auth, 'logout');
    const request = firstValueFrom(http.post(`${environment.apiUrl}/auth/login`, {}));
    backend
      .expectOne(`${environment.apiUrl}/auth/login`)
      .flush({ detail: 'Email ou mot de passe incorrect.' }, { status: 401, statusText: 'Unauthorized' });
    await expect(request).rejects.toThrow('Email ou mot de passe incorrect.');
    expect(logout).not.toHaveBeenCalled();
  });

  it('ne déconnecte pas sur une autre erreur (503)', async () => {
    const logout = vi.spyOn(auth, 'logout');
    const request = firstValueFrom(http.get(`${environment.apiUrl}/courses`));
    backend
      .expectOne(`${environment.apiUrl}/courses`)
      .flush({ detail: 'LLM indisponible' }, { status: 503, statusText: 'Service Unavailable' });
    await expect(request).rejects.toThrow('LLM indisponible');
    expect(logout).not.toHaveBeenCalled();
  });
});
