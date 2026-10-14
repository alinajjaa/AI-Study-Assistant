import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { Profile } from '../../core/models/profile.models';
import { ProfilePage } from './profile.page';

const profile: Profile = {
  email: 'ali@example.com',
  level: 'intermediaire',
  stats: { courses: 2, questions: 14, exams: 3, cards_reviewed: 40, known_rate: 0.9 },
  weak_points: [{ course: 'CNN intro', concept: 'Max pooling', reviews: 3, to_review_rate: 0.667 }],
  level_suggestion: { level: 'avance', direction: 'up', reviews: 25, known_rate: 0.92 },
};

describe('ProfilePage', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    backend.verify();
    localStorage.clear();
  });

  async function render(data: Profile = profile) {
    const fixture = TestBed.createComponent(ProfilePage);
    fixture.detectChanges();
    backend.expectOne(`${environment.apiUrl}/profile`).flush(data);
    await fixture.whenStable();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const button = (el: HTMLElement, label: string) =>
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes(label));

  it('affiche le niveau, les statistiques et le taux de cartes sues', async () => {
    const { el } = await render();
    expect(el.querySelector('[role="radio"][aria-checked="true"]')?.textContent).toContain('Intermédiaire');
    const stats = el.querySelector('.stats')?.textContent ?? '';
    expect(stats).toContain('14');
    expect(stats).toContain('40');
    expect(stats).toContain('90 %');
  });

  it('affiche les points faibles avec un bouton Réviser vers les flashcards du cours', async () => {
    const { el } = await render();
    const weak = el.querySelector('.weak');
    expect(weak?.textContent).toContain('Max pooling');
    expect(weak?.textContent).toContain('67 % à revoir · 3 révisions');
    const link = weak?.querySelector('a');
    expect(link?.textContent).toContain('Réviser');
    expect(link?.getAttribute('href')).toBe('/flashcards?course=CNN%20intro');
  });

  it('accepter la suggestion change le niveau (PATCH /me) puis recharge le profil', async () => {
    const { el, fixture } = await render();
    expect(el.querySelector('.suggestion')?.textContent).toContain('92 %');
    button(el, 'Passer en Avancé')?.click();

    const patch = backend.expectOne(`${environment.apiUrl}/me`);
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.body).toEqual({ level: 'avance' });
    patch.flush({ id: 1, email: 'ali@example.com', level: 'avance', created_at: '2026-10-14T10:00:00Z' });

    backend.expectOne(`${environment.apiUrl}/profile`).flush({ ...profile, level: 'avance', level_suggestion: null });
    await fixture.whenStable();
    expect(el.querySelector('.suggestion')).toBeNull();
    expect(el.querySelector('[role="radio"][aria-checked="true"]')?.textContent).toContain('Avancé');
  });

  it('ignorer masque la suggestion sans changer le niveau', async () => {
    const { el, fixture } = await render();
    button(el, 'Ignorer')?.click();
    await fixture.whenStable();
    expect(el.querySelector('.suggestion')).toBeNull();
    backend.expectNone(`${environment.apiUrl}/me`);
  });

  it('changer de niveau depuis le sélecteur', async () => {
    const { el } = await render({ ...profile, level_suggestion: null });
    button(el, 'Débutant')?.click();
    const patch = backend.expectOne(`${environment.apiUrl}/me`);
    expect(patch.request.body).toEqual({ level: 'debutant' });
    patch.flush({ id: 1, email: 'ali@example.com', level: 'debutant', created_at: '2026-10-14T10:00:00Z' });
    backend.expectOne(`${environment.apiUrl}/profile`).flush({ ...profile, level: 'debutant', level_suggestion: null });
  });

  it('message d’aide quand il n’y a pas encore de point faible', async () => {
    const { el } = await render({ ...profile, weak_points: [], stats: { ...profile.stats, known_rate: null } });
    expect(el.textContent).toContain('Aucun point faible pour l\'instant');
    expect(el.querySelector('.stats')?.textContent).toContain('—');
  });
});
