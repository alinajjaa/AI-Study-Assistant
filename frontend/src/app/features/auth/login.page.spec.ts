import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { of, Subject, throwError } from 'rxjs';
import { User } from '../../core/models/auth.models';
import { AuthService } from '../../core/services/auth.service';
import { LoginPage } from './login.page';
import { RegisterPage } from './register.page';

const USER = { id: 1, email: 'etudiant@example.com', level: 'intermediaire' } as unknown as User;

async function render<T>(component: Type<T>, auth: Partial<AuthService>, query: Record<string, string> = {}) {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: AuthService, useValue: auth },
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(query) } } },
    ],
  });
  const router = TestBed.inject(Router);
  const navigate = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  const fixture = TestBed.createComponent(component);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const type = (selector: string, value: string) => {
    const input = el.querySelector<HTMLInputElement>(selector)!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
  };
  const submit = async () => {
    el.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { el, navigate, type, submit };
}

describe('LoginPage', () => {
  it('champs vides : message, aucun appel au backend', async () => {
    const login = vi.fn();
    const { el, submit } = await render(LoginPage, { login });
    await submit();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Renseigne ton email et ton mot de passe.');
    expect(login).not.toHaveBeenCalled();
  });

  it('connexion réussie : email sans espaces, retour à la page demandée', async () => {
    const login = vi.fn().mockReturnValue(of(USER));
    const { navigate, type, submit } = await render(LoginPage, { login }, { returnUrl: '/flashcards' });
    type('#login-email', '  etudiant@example.com ');
    type('#login-password', 'motdepasse123');
    await submit();
    expect(login).toHaveBeenCalledWith('etudiant@example.com', 'motdepasse123');
    expect(navigate).toHaveBeenCalledWith('/flashcards');
  });

  it('page de retour externe refusée : Assistant par défaut', async () => {
    const login = vi.fn().mockReturnValue(of(USER));
    const { navigate, type, submit } = await render(LoginPage, { login }, { returnUrl: '//pirate.example' });
    type('#login-email', 'etudiant@example.com');
    type('#login-password', 'motdepasse123');
    await submit();
    expect(navigate).toHaveBeenCalledWith('/companion');
  });

  it('session expirée : invitation à se reconnecter', async () => {
    const { el } = await render(LoginPage, { login: vi.fn() }, { returnUrl: '/summaries' });
    expect(el.querySelector('[role="status"]')?.textContent).toContain('Connecte-toi pour continuer.');
  });

  it('erreur du backend (ex. 429) : message affiché, formulaire réactivé', async () => {
    const login = vi.fn().mockReturnValue(throwError(() => new Error('Trop de tentatives de connexion : réessaie dans 15 min.')));
    const { el, navigate, type, submit } = await render(LoginPage, { login });
    type('#login-email', 'etudiant@example.com');
    type('#login-password', 'mauvais-mot');
    await submit();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Trop de tentatives');
    expect(el.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(false);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('pendant la connexion : bouton désactivé, pas de double envoi', async () => {
    const pending = new Subject<User>();
    const login = vi.fn().mockReturnValue(pending);
    const { el, type, submit } = await render(LoginPage, { login });
    type('#login-email', 'etudiant@example.com');
    type('#login-password', 'motdepasse123');
    await submit();
    await submit();
    expect(login).toHaveBeenCalledTimes(1);
    expect(el.querySelector('button[type="submit"]')?.textContent).toContain('Connexion…');
  });
});

describe('RegisterPage', () => {
  it('email invalide : message, aucun appel au backend', async () => {
    const register = vi.fn();
    const { el, type, submit } = await render(RegisterPage, { register });
    type('input[type="email"]', 'pas-un-email');
    type('input[type="password"]', 'motdepasse123');
    await submit();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Adresse email invalide.');
    expect(register).not.toHaveBeenCalled();
  });

  it('inscription réussie : niveau par défaut intermédiaire, puis Assistant', async () => {
    const register = vi.fn().mockReturnValue(of(USER));
    const { navigate, type, submit } = await render(RegisterPage, { register });
    type('input[type="email"]', 'etudiant@example.com');
    type('input[type="password"]', 'motdepasse123');
    await submit();
    expect(register).toHaveBeenCalledWith('etudiant@example.com', 'motdepasse123', 'intermediaire');
    expect(navigate).toHaveBeenCalledWith('/companion');
  });

  it('email déjà utilisé : message du backend', async () => {
    const register = vi.fn().mockReturnValue(throwError(() => new Error('Un compte existe déjà avec cet email.')));
    const { el, type, submit } = await render(RegisterPage, { register });
    type('input[type="email"]', 'etudiant@example.com');
    type('input[type="password"]', 'motdepasse123');
    await submit();
    expect(el.querySelector('[role="alert"]')?.textContent).toContain('Un compte existe déjà');
  });
});
