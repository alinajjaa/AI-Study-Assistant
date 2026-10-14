import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { CompanionJob } from '../../core/models/companion.models';
import { Conversation, StoredMessage } from '../../core/models/conversation.models';
import { TOKEN_KEY } from '../../core/services/auth.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { CompanionPage } from './companion.page';

const api = environment.apiUrl;

function conversation(id: number, course: string | null = null): Conversation {
  return { id, title: `Conversation ${id}`, course, created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z' };
}

function stored(id: number, role: 'user' | 'assistant', content: string, extra: Partial<StoredMessage> = {}): StoredMessage {
  return { id, role, content, course: 'CNN', sources: [], answered: true, created_at: '2026-10-14T10:00:00Z', ...extra };
}

async function render(courses: string[], conversations: Conversation[] = [], openConversation?: number) {
  localStorage.clear();
  localStorage.setItem(TOKEN_KEY, 'jeton');
  if (openConversation !== undefined) {
    localStorage.setItem('ai-study-assistant.conversation', String(openConversation));
  }
  TestBed.configureTestingModule({
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  });
  TestBed.inject(ConversationsService);
  TestBed.tick(); // effet initial du service (réinitialisation liée au compte), comme au démarrage de l'app
  const fixture = TestBed.createComponent(CompanionPage);
  const backend = TestBed.inject(HttpTestingController);
  backend.expectOne(`${api}/courses`).flush(courses);
  backend.expectOne(`${api}/conversations`).flush(conversations);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const select = el.querySelector<HTMLSelectElement>('#companion-course')!;
  /** Entrées de la liste « Mes cours » (sans les boutons examen / suppression). */
  const courseItems = () => [...el.querySelectorAll<HTMLButtonElement>('app-course-selector .item')];
  return { fixture, el, backend, select, courseItems };
}

describe('CompanionPage (Assistant)', () => {
  afterEach(() => localStorage.clear());

  it('page unique : conversations, puis Mes cours, puis import ; sélecteur et boutons rapides', async () => {
    const { el, select, courseItems } = await render(['CNN', 'Docker']);
    expect(el.querySelector('h1')?.textContent).toBe('Assistant');

    const sidebar = [...el.querySelector('aside')!.children].map((c) => c.tagName.toLowerCase());
    expect(sidebar).toEqual(['app-conversation-list', 'app-course-selector', 'app-upload-panel']);
    expect(courseItems().map((b) => b.textContent?.trim())).toEqual(['Tous les cours', 'CNN', 'Docker']);
    expect(el.querySelector('[aria-label="Générer un examen pour CNN"]')).not.toBeNull();
    expect(el.querySelector('[aria-label="Supprimer le cours Docker"]')).not.toBeNull();
    expect(el.querySelector('app-upload-panel')?.textContent).toContain('Indexer');

    expect([...select.options].map((o) => o.textContent?.trim())).toEqual(['Tous les cours', 'CNN', 'Docker']);
    const quick = [...el.querySelectorAll('.quick')].map((b) => b.textContent?.trim());
    expect(quick).toEqual(['Résumer le cours', 'Générer un quiz', 'Flashcards', 'Mes progrès']);
    expect(el.querySelector('textarea')?.getAttribute('placeholder')).toBe('Demande ce que tu veux…');
  });

  it('une seule source de vérité : la liste « Mes cours » et le sélecteur restent synchronisés', async () => {
    const { fixture, select, courseItems } = await render(['CNN', 'Docker']);
    courseItems()[2].click(); // Docker dans la liste
    await fixture.whenStable();
    expect(select.value).toBe('Docker');
    expect(courseItems()[2].getAttribute('aria-current')).toBe('true');

    select.value = 'CNN';
    select.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    expect(courseItems()[1].getAttribute('aria-current')).toBe('true');
    expect(courseItems()[2].getAttribute('aria-current')).toBeNull();

    courseItems()[0].click(); // Tous les cours
    await fixture.whenStable();
    expect(select.value).toBe('');
  });

  it('bug a : le cours sélectionné est celui envoyé à l’agent et affiché dans le message', async () => {
    const { fixture, el, backend, courseItems } = await render(['CNN', 'Docker']);
    courseItems()[2].click(); // Docker
    await fixture.whenStable();
    el.querySelectorAll<HTMLButtonElement>('.quick')[0].click(); // « Résumer le cours »
    await fixture.whenStable();

    expect(el.querySelector('.student .meta')?.textContent).toBe('Toi · Docker');
    const create = backend.expectOne(`${api}/conversations`);
    expect(create.request.body).toEqual({ course: 'Docker' });
    create.flush(conversation(4, 'Docker'));
    const send = backend.expectOne(`${api}/companion/messages`);
    expect(send.request.body).toEqual({ conversation_id: 4, course: 'Docker', message: 'Résume le cours.' });

    const job: CompanionJob = {
      job_id: 'j1', status: 'done', tool: 'summarize', elapsed_s: 1, error: null,
      exchange: {
        conversation: conversation(4, 'Docker'),
        user_message: stored(10, 'user', 'Résume le cours.', { course: 'Docker' }),
        assistant_messages: [stored(11, 'assistant', 'Je n’ai pas pu préparer ce résumé.', { course: 'Docker', kind: 'text' })],
        tools: ['summarize'], fallback: false,
      },
    };
    send.flush(job);
    await fixture.whenStable();
    expect(el.querySelector('.student .meta')?.textContent).toBe('Toi · Docker');
    expect(el.querySelector('#companion-course')).toHaveProperty('value', 'Docker');
  });

  it('un seul cours : sélectionné d’office ; plusieurs : « Tous les cours »', async () => {
    const single = await render(['CNN']);
    expect(single.select.value).toBe('CNN');
    expect(single.el.querySelector('.target strong')?.textContent).toBe('CNN');
    TestBed.resetTestingModule();

    const several = await render(['CNN', 'Docker']);
    expect(several.select.value).toBe('');
    expect(several.el.querySelector('.target strong')?.textContent).toBe('tous les cours');
  });

  it('une ancienne conversation du tuteur s’ouvre avec sa carte de réponse sourcée et reprend son cours', async () => {
    const { fixture, el, backend, select } = await render(['CNN', 'Docker'], [conversation(3, 'Docker')], 3);
    backend.expectOne(`${api}/conversations/3/messages`).flush([
      stored(1, 'user', 'Qu’est-ce qu’un conteneur ?', { course: 'Docker' }),
      // Réponse du tuteur, enregistrée avant l'Assistant : pas de kind
      stored(2, 'assistant', 'Un conteneur isole une application [p.2].', {
        course: 'Docker', sources: [{ course: 'Docker', page: 2, score: 0.8, excerpt: 'Un conteneur…' }],
      }),
    ]);
    await fixture.whenStable();
    expect(select.value).toBe('Docker');
    expect(el.querySelector('app-answer-card .tag')?.textContent?.trim()).toBe('Tuteur');
    expect(el.querySelector('app-answer-card .page-ref')?.textContent).toBe('p.2');
    expect(el.querySelector('app-sources-list')).not.toBeNull();
  });

  it('bug d : boutons rapides et champ forment un seul bloc de saisie, après la liste des messages', async () => {
    const { el } = await render(['CNN']);
    const main = el.querySelector('.main')!;
    const composer = main.querySelector('.composer')!;
    expect(main.lastElementChild).toBe(composer);
    expect([...composer.children].map((c) => c.tagName.toLowerCase())).toEqual(['ul', 'app-question-input']);
    expect(composer.firstElementChild?.classList).toContain('quick-actions');
    // Les messages ne sont jamais dans la zone de saisie : elle vient après eux, sans les recouvrir
    const thread = main.querySelector('app-companion-thread')!;
    expect(composer.contains(thread)).toBe(false);
    expect(thread.classList).toContain('thread');
    expect(thread.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('bug d : la zone de saisie est opaque et collée en bas ; la liste garde de l’espace sous le dernier échange', async () => {
    const { el } = await render(['CNN']);
    const composer = getComputedStyle(el.querySelector('.composer')!);
    expect(composer.position).toBe('sticky');
    expect(composer.bottom).toBe('0px');
    expect(composer.backgroundColor === '' || composer.backgroundColor === 'transparent').toBe(false);
    expect(getComputedStyle(el.querySelector('app-companion-thread')!).paddingBottom).not.toBe('0px');
  });

  it('import d’un PDF : la liste est rechargée et le nouveau cours sélectionné', async () => {
    const { fixture, backend, select } = await render(['CNN', 'Docker']);
    const page = fixture.componentInstance as unknown as { onUploaded(res: { course: string; chunks: number }): void };
    page.onUploaded({ course: 'Réseaux', chunks: 12 });
    backend.expectOne(`${api}/courses`).flush(['CNN', 'Docker', 'Réseaux']);
    await fixture.whenStable();
    expect(select.value).toBe('Réseaux');
  });

  it('suppression d’un cours après confirmation ; l’icône examen ouvre la modale', async () => {
    const { fixture, el, backend, courseItems } = await render(['CNN', 'Docker']);
    courseItems()[2].click();
    await fixture.whenStable();

    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    el.querySelector<HTMLButtonElement>('[aria-label="Supprimer le cours Docker"]')!.click();
    expect(confirm).toHaveBeenCalled();
    backend.expectOne((r) => r.method === 'DELETE' && r.url === `${api}/courses/Docker`).flush({ deleted: 'Docker' });
    backend.expectOne(`${api}/courses`).flush(['CNN']);
    await fixture.whenStable();
    expect(courseItems().map((b) => b.textContent?.trim())).toEqual(['Tous les cours', 'CNN']);
    confirm.mockRestore();

    el.querySelector<HTMLButtonElement>('[aria-label="Générer un examen pour CNN"]')!.click();
    await fixture.whenStable();
    expect(el.querySelector('app-exam-dialog')?.textContent).toContain('CNN');
  });
});
