import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { AuthResponse, User } from '../models/auth.models';
import { AuthService, TOKEN_KEY } from './auth.service';

const user: User = { id: 1, email: 'ali@example.com', level: 'debutant', created_at: '2026-10-14T10:00:00Z' };
const response: AuthResponse = { access_token: 'jeton-123', token_type: 'bearer', user };

describe('AuthService', () => {
  let backend: HttpTestingController;

  function setup(): AuthService {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    backend = TestBed.inject(HttpTestingController);
    return TestBed.inject(AuthService);
  }

  beforeEach(() => localStorage.clear());
  afterEach(() => {
    backend.verify();
    localStorage.clear();
  });

  it('démarre déconnecté sans jeton', () => {
    const auth = setup();
    expect(auth.isAuthenticated()).toBe(false);
    expect(auth.user()).toBeNull();
  });

  it('login : enregistre le jeton (signal + localStorage) et le compte', async () => {
    const auth = setup();
    const result = firstValueFrom(auth.login('ali@example.com', 'motdepasse123'));
    const req = backend.expectOne(`${environment.apiUrl}/auth/login`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'ali@example.com', password: 'motdepasse123' });
    req.flush(response);

    expect(await result).toEqual(user);
    expect(auth.isAuthenticated()).toBe(true);
    expect(auth.token()).toBe('jeton-123');
    expect(auth.user()).toEqual(user);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('jeton-123');
  });

  it('register : envoie le niveau choisi', async () => {
    const auth = setup();
    const result = firstValueFrom(auth.register('ali@example.com', 'motdepasse123', 'avance'));
    const req = backend.expectOne(`${environment.apiUrl}/auth/register`);
    expect(req.request.body).toEqual({ email: 'ali@example.com', password: 'motdepasse123', level: 'avance' });
    req.flush(response);
    await result;
    expect(auth.isAuthenticated()).toBe(true);
  });

  it('restoreSession : relit le jeton et charge /me', () => {
    localStorage.setItem(TOKEN_KEY, 'ancien-jeton');
    const auth = setup();
    expect(auth.isAuthenticated()).toBe(true);
    auth.restoreSession();
    backend.expectOne(`${environment.apiUrl}/me`).flush(user);
    expect(auth.user()).toEqual(user);
  });

  it('updateLevel : PATCH /me et met à jour le compte', async () => {
    const auth = setup();
    const result = firstValueFrom(auth.updateLevel('avance'));
    const req = backend.expectOne(`${environment.apiUrl}/me`);
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ level: 'avance' });
    req.flush({ ...user, level: 'avance' });
    await result;
    expect(auth.user()?.level).toBe('avance');
  });

  it('logout : efface le jeton et renvoie vers /login avec la page à rouvrir', () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const auth = setup();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    auth.logout('/flashcards');
    expect(auth.isAuthenticated()).toBe(false);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/flashcards' } });
  });

  it('fonctionne même si localStorage lève une exception', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('bloqué');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('bloqué');
    });
    const auth = setup();
    expect(auth.isAuthenticated()).toBe(false);
    const result = firstValueFrom(auth.login('ali@example.com', 'motdepasse123'));
    backend.expectOne(`${environment.apiUrl}/auth/login`).flush(response);
    await result;
    expect(auth.token()).toBe('jeton-123');
    getItem.mockRestore();
    setItem.mockRestore();
  });
});
