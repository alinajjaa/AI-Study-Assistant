import { authGuard } from './core/guards/auth.guard';
import { routes } from './app.routes';

describe('routes', () => {
  it('l’Assistant est la page d’accueil, protégée, titrée « Assistant »', () => {
    const companion = routes.find((r) => r.path === 'companion');
    expect(companion?.title).toBe('Assistant · AI Study Assistant');
    expect(companion?.canActivate).toEqual([authGuard]);
    expect(routes.find((r) => r.path === '')?.redirectTo).toBe('companion');
    expect(routes.find((r) => r.path === '**')?.redirectTo).toBe('companion');
  });

  it('/tutor redirige vers l’Assistant (plus de page Tuteur)', () => {
    const tutor = routes.find((r) => r.path === 'tutor');
    expect(tutor).toEqual({ path: 'tutor', redirectTo: 'companion' });
    expect(routes.some((r) => r.loadComponent?.toString().includes('tutor'))).toBe(false);
  });

  it('toutes les pages de l’application sont protégées par authGuard', () => {
    const pages = routes.filter((r) => r.loadComponent && !['login', 'register'].includes(r.path ?? ''));
    expect(pages.map((r) => r.path)).toEqual(['companion', 'flashcards', 'summaries', 'exams', 'courses', 'profile']);
    expect(pages.every((r) => r.canActivate?.includes(authGuard))).toBe(true);
  });
});
