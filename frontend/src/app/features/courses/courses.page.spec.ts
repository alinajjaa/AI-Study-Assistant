import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { TOKEN_KEY } from '../../core/services/auth.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { CoursesPage } from './courses.page';

const api = environment.apiUrl;

/** jsdom n'implémente pas toujours showModal/close : on simule l'attribut open (comme exam-dialog.spec). */
function stubDialog(): void {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute('open');
    this.dispatchEvent(new Event('close'));
  };
}

async function render(courses: string[] | 'error') {
  stubDialog();
  localStorage.clear();
  localStorage.setItem(TOKEN_KEY, 'jeton');
  TestBed.configureTestingModule({
    providers: [provideRouter([{ path: '**', children: [] }]), provideHttpClient(), provideHttpClientTesting()],
  });
  const fixture = TestBed.createComponent(CoursesPage);
  const backend = TestBed.inject(HttpTestingController);
  const request = backend.expectOne(`${api}/courses`);
  if (courses === 'error') {
    request.flush({ detail: 'Panne' }, { status: 500, statusText: 'Erreur' });
  } else {
    request.flush(courses);
  }
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const cards = () => [...el.querySelectorAll<HTMLElement>('.grid .course')];
  return { fixture, el, backend, cards };
}

describe('CoursesPage (Mes cours)', () => {
  afterEach(() => localStorage.clear());

  it('une carte par cours (avatar, nom, actions) et une carte d’import', async () => {
    const { el, cards } = await render(['CNN', 'Docker']);
    expect(el.querySelector('h1')?.textContent).toBe('Mes cours');
    expect(cards().map((c) => c.querySelector('h2')?.textContent)).toEqual(['CNN', 'Docker']);
    expect(cards()[0].querySelector('.course-avatar')?.textContent).toBe('C');
    expect(cards()[0].querySelector('h2')?.getAttribute('title')).toBe('CNN');

    const actions = [...cards()[0].querySelectorAll<HTMLElement>('.course__actions > *')];
    expect(actions.map((a) => a.textContent?.trim())).toEqual(['Discuter', 'Examen', 'Flashcards', 'Résumé']);
    expect(actions.map((a) => a.getAttribute('aria-label'))).toEqual([
      'Discuter de CNN',
      'Générer un examen pour CNN',
      'Flashcards de CNN',
      'Résumé de CNN',
    ]);
    expect(actions[0].getAttribute('href')).toBe('/companion?course=CNN');
    expect(actions[2].getAttribute('href')).toBe('/flashcards?course=CNN');
    expect(actions[3].getAttribute('href')).toBe('/summaries?course=CNN');
    expect(cards()[1].querySelector('[aria-label="Supprimer le cours Docker"]')).not.toBeNull();

    const importCard = el.querySelector('.grid .import')!;
    expect(importCard.querySelector('h2')?.textContent).toBe('Importer un cours');
    expect(importCard.querySelector('app-upload-panel .import')?.textContent?.trim()).toBe('Importer un PDF');
    expect(importCard.textContent).toContain('PDF · 50 Mo max');
  });

  it('« Discuter » démarre une nouvelle conversation dans l’Assistant sur ce cours', async () => {
    const { cards } = await render(['CNN']);
    const conversations = TestBed.inject(ConversationsService);
    const startNew = vi.spyOn(conversations, 'startNew');
    cards()[0].querySelector<HTMLAnchorElement>('[aria-label="Discuter de CNN"]')!.click();
    expect(startNew).toHaveBeenCalled();
  });

  it('« Examen » ouvre la modale d’examen ; la génération part en arrière-plan et la carte l’indique', async () => {
    const { fixture, el, cards } = await render(['CNN']);
    const jobs = TestBed.inject(ExamJobsService);
    const start = vi.spyOn(jobs, 'start').mockImplementation(() => undefined);
    cards()[0].querySelector<HTMLButtonElement>('[aria-label="Générer un examen pour CNN"]')!.click();
    await fixture.whenStable();
    const dialog = el.querySelector('app-exam-dialog')!;
    expect(dialog.textContent).toContain('CNN');
    [...dialog.querySelectorAll<HTMLButtonElement>('button')].find((b) => /Générer/.test(b.textContent ?? ''))!.click();
    await fixture.whenStable();
    expect(start).toHaveBeenCalledWith('CNN', expect.anything());
  });

  it('suppression d’un cours après la confirmation existante, puis la liste est rechargée', async () => {
    const { fixture, backend, cards } = await render(['CNN', 'Docker']);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    cards()[1].querySelector<HTMLButtonElement>('[aria-label="Supprimer le cours Docker"]')!.click();
    expect(confirm).toHaveBeenCalled();
    backend.expectOne((r) => r.method === 'DELETE' && r.url === `${api}/courses/Docker`).flush({ deleted: 'Docker' });
    backend.expectOne(`${api}/courses`).flush(['CNN']);
    await fixture.whenStable();
    expect(cards().map((c) => c.querySelector('h2')?.textContent)).toEqual(['CNN']);
    confirm.mockRestore();
  });

  it('suppression annulée : aucune requête', async () => {
    const { backend, cards } = await render(['CNN']);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    cards()[0].querySelector<HTMLButtonElement>('[aria-label="Supprimer le cours CNN"]')!.click();
    backend.expectNone((r) => r.method === 'DELETE');
    confirm.mockRestore();
  });

  it('aucun cours : état vide et zone d’import ; erreur : message et « Réessayer »', async () => {
    const empty = await render([]);
    expect(empty.el.querySelector('app-empty-state')?.textContent).toContain('Aucun cours pour l');
    expect(empty.el.querySelector('.grid .import')).not.toBeNull();
    TestBed.resetTestingModule();

    const failed = await render('error');
    expect(failed.el.querySelector('app-error-state')).not.toBeNull();
    expect(failed.el.querySelector('app-empty-state')).toBeNull();
  });

  it('import réussi : la liste est rechargée', async () => {
    const { fixture, backend, cards } = await render(['CNN']);
    const page = fixture.componentInstance as unknown as { onUploaded(res: { course: string; chunks: number }): void };
    page.onUploaded({ course: 'Réseaux', chunks: 8 });
    backend.expectOne(`${api}/courses`).flush(['CNN', 'Réseaux']);
    await fixture.whenStable();
    expect(cards().map((c) => c.querySelector('h2')?.textContent)).toEqual(['CNN', 'Réseaux']);
  });
});
