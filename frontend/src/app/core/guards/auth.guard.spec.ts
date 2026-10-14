import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { TOKEN_KEY } from '../services/auth.service';
import { authGuard, guestGuard } from './auth.guard';

@Component({ template: 'page' })
class Page {}

async function navigate(url: string): Promise<string> {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(),
      provideHttpClientTesting(),
      provideRouter([
        { path: 'login', canActivate: [guestGuard], component: Page },
        { path: 'companion', canActivate: [authGuard], component: Page },
        { path: 'tutor', redirectTo: 'companion' },
        { path: 'flashcards', canActivate: [authGuard], component: Page },
      ]),
    ],
  });
  const harness = await RouterTestingHarness.create();
  await harness.navigateByUrl(url);
  return TestBed.inject(Router).url;
}

describe('authGuard / guestGuard', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it('redirige vers /login (avec returnUrl) sans session', async () => {
    expect(await navigate('/flashcards')).toBe('/login?returnUrl=%2Fflashcards');
  });

  it('laisse passer un étudiant connecté', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    expect(await navigate('/flashcards')).toBe('/flashcards');
  });

  it('renvoie un étudiant connecté de /login vers l’Assistant', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    expect(await navigate('/login')).toBe('/companion');
  });

  it('l’ancienne page /tutor mène à l’Assistant, toujours protégé', async () => {
    expect(await navigate('/tutor')).toBe('/login?returnUrl=%2Fcompanion');
    TestBed.resetTestingModule();
    localStorage.setItem(TOKEN_KEY, 'jeton');
    expect(await navigate('/tutor')).toBe('/companion');
  });

  it('laisse un visiteur ouvrir /login', async () => {
    expect(await navigate('/login')).toBe('/login');
  });
});
