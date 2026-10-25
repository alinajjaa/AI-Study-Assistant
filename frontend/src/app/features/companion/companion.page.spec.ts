import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { CompanionJob } from '../../core/models/companion.models';
import { Conversation, StoredMessage } from '../../core/models/conversation.models';
import { TOKEN_KEY } from '../../core/services/auth.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { ShellService } from '../../core/services/shell.service';
import { ShellSidebar } from '../../shell/sidebar/shell-sidebar';
import { CompanionPage } from './companion.page';

const api = environment.apiUrl;

/** Comme le shell : la barre latérale (récents) à côté de la page. */
@Component({
  imports: [CompanionPage, ShellSidebar],
  template: `
    <aside><app-shell-sidebar /></aside>
    <app-companion-page />
  `,
})
class ShellHost {}

function conversation(id: number, course: string | null = null): Conversation {
  return { id, title: `Conversation ${id}`, course, created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z' };
}

function stored(id: number, role: 'user' | 'assistant', content: string, extra: Partial<StoredMessage> = {}): StoredMessage {
  return { id, role, content, course: 'CNN', sources: [], answered: true, created_at: '2026-10-14T10:00:00Z', ...extra };
}

/** Évènement de glisser-déposer avec un fichier (jsdom n'a pas de DataTransfer). */
function dragEvent(type: string, file: File | null = null): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', {
    value: { types: ['Files'], files: { item: () => file } },
  });
  return event;
}

async function render(courses: string[], conversations: Conversation[] = [], openConversation?: number) {
  localStorage.clear();
  localStorage.setItem(TOKEN_KEY, 'jeton');
  if (openConversation !== undefined) {
    localStorage.setItem('ai-study-assistant.conversation', String(openConversation));
  }
  TestBed.configureTestingModule({
    // Route attrape-tout : la barre latérale navigue vers /companion
    providers: [provideRouter([{ path: '**', children: [] }]), provideHttpClient(), provideHttpClientTesting()],
  });
  TestBed.inject(ConversationsService);
  TestBed.tick(); // effet initial du service (réinitialisation liée au compte), comme au démarrage de l'app
  const fixture = TestBed.createComponent(ShellHost);
  const backend = TestBed.inject(HttpTestingController);
  backend.expectOne(`${api}/courses`).flush(courses);
  backend.expectOne(`${api}/conversations`).flush(conversations);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const page = fixture.debugElement.query(By.directive(CompanionPage));
  const main = page.nativeElement as HTMLElement;
  /** Chip du cours interrogé, dans la zone de saisie. */
  const chip = () => main.querySelector<HTMLButtonElement>('app-course-picker .chip')!;
  const chipLabel = () => chip().querySelector('.chip__label')?.textContent?.trim();
  /** Ouvre le menu de la chip et renvoie ses entrées. */
  const openPicker = async () => {
    if (chip().getAttribute('aria-expanded') !== 'true') {
      chip().click();
      await fixture.whenStable();
    }
    return [...main.querySelectorAll<HTMLButtonElement>('app-course-picker [role^="menuitem"]')];
  };
  /** Nom d'une entrée du menu (sans l'initiale de l'avatar). */
  const itemName = (item: HTMLElement) => item.querySelector('.menu__name')?.textContent?.trim();
  const choose = async (label: string) => {
    (await openPicker()).find((b) => itemName(b) === label)!.click();
    await fixture.whenStable();
  };
  const quick = (label: string) =>
    [...main.querySelectorAll<HTMLButtonElement>('.quick')].find((b) => b.textContent?.trim() === label)!;
  return { fixture, el, main, backend, chip, chipLabel, openPicker, itemName, choose, quick, page: page.componentInstance as CompanionPage };
}

describe('CompanionPage (Assistant)', () => {
  afterEach(() => localStorage.clear());

  it('accueil : titre centré, saisie au centre avec « + » et choix du cours, actions rapides dessous', async () => {
    const { main, chipLabel } = await render(['CNN', 'Docker']);
    expect(main.querySelector('h1')?.textContent?.replace(/\s+/g, ' ')).toBe("Que veux-tu réviser aujourd'hui ?");
    expect(main.querySelector('.page')?.classList).toContain('page--home');
    expect(main.querySelector('app-companion-thread')).toBeNull();

    const composer = main.querySelector('.composer')!;
    expect([...composer.children].map((c) => c.tagName.toLowerCase())).toEqual(['app-upload-panel', 'app-question-input', 'ul']);
    expect(main.querySelector('textarea')?.getAttribute('placeholder')).toBe('Demande ce que tu veux…');
    // Outils dans la zone de saisie : « + » pour importer, chip du cours
    const tools = composer.querySelector('app-question-input .tools')!;
    expect(tools.querySelector('.tool')?.getAttribute('aria-label')).toBe('Importer un PDF');
    expect(chipLabel()).toBe('Tous les cours');
    expect(composer.querySelector('app-question-input .target')).toBeNull();
    // Plus de liste de cours ni de zone d'import dans la page : tout passe par la zone de saisie
    expect(main.querySelector('app-upload-panel .import')).toBeNull();

    const quick = composer.querySelector('.quick-actions')!;
    expect(quick.classList).toContain('quick-actions--shown');
    expect([...quick.querySelectorAll('.quick')].map((b) => b.textContent?.trim())).toEqual([
      'Flashcards',
      'Résumé',
      'Examen',
      'Quiz',
    ]);
  });

  it('une seule source de vérité : le cours choisi dans la chip est celui de la page', async () => {
    const { fixture, main, chip, chipLabel, openPicker, itemName, choose } = await render(['CNN', 'Docker']);
    const items = await openPicker();
    expect(chip().getAttribute('aria-expanded')).toBe('true');
    expect(items.map(itemName)).toEqual(['Tous les cours', 'CNN', 'Docker', 'Importer un PDF']);
    expect(items.map((b) => b.getAttribute('role'))).toEqual(['menuitemradio', 'menuitemradio', 'menuitemradio', 'menuitem']);
    expect(items[0].getAttribute('aria-checked')).toBe('true');
    expect(items[1].querySelector('.course-avatar')?.textContent).toBe('C');

    await choose('Docker');
    expect(chipLabel()).toBe('Docker');
    expect(main.querySelector('app-course-picker [role="menu"]')).toBeNull(); // menu refermé
    expect(document.activeElement).toBe(chip()); // focus rendu à la chip
    const reopened = await openPicker();
    expect(itemName(reopened.find((b) => b.getAttribute('aria-checked') === 'true')!)).toBe('Docker');

    // Clavier : flèches entre les entrées, Échap referme et rend le focus à la chip
    reopened[2].focus();
    reopened[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(reopened[3]);
    reopened[3].dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await fixture.whenStable();
    expect(main.querySelector('app-course-picker [role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(chip());

    await choose('Tous les cours');
    expect(chipLabel()).toBe('Tous les cours');
  });

  it('bug a : le cours sélectionné est celui envoyé à l’agent et affiché dans le message', async () => {
    const { fixture, main, backend, choose, quick, chipLabel } = await render(['CNN', 'Docker']);
    await choose('Docker');
    quick('Résumé').click();
    await fixture.whenStable();

    expect(main.querySelector('.student .meta')?.textContent).toBe('Toi · Docker');
    expect(main.querySelector('.page')?.classList).not.toContain('page--home'); // la conversation commence
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
    expect(main.querySelector('.student .meta')?.textContent).toBe('Toi · Docker');
    expect(chipLabel()).toBe('Docker');
  });

  it('actions rapides : Flashcards et Quiz demandent à l’agent sur le cours choisi', async () => {
    const { fixture, backend, choose, quick } = await render(['CNN', 'Docker']);
    await choose('CNN');
    quick('Flashcards').click();
    await fixture.whenStable();
    backend.expectOne(`${api}/conversations`).flush(conversation(5, 'CNN'));
    const flashcards = backend.expectOne(`${api}/companion/messages`);
    expect(flashcards.request.body).toEqual({
      conversation_id: 5,
      course: 'CNN',
      message: 'Prépare-moi des flashcards pour réviser.',
    });
    // Une demande est en cours : les actions qui interrogent l'agent sont désactivées, pas « Examen »
    expect(quick('Quiz').disabled).toBe(true);
    expect(quick('Examen').disabled).toBe(false);
  });

  it('action « Examen » : sans cours, invite à en choisir un ; avec un cours, ouvre la modale d’examen', async () => {
    const { fixture, main, chip, choose, quick } = await render(['CNN', 'Docker']);
    quick('Examen').click();
    await fixture.whenStable();
    expect(main.querySelector('.course-hint')?.textContent).toContain('Choisis un cours');
    expect(chip().getAttribute('aria-expanded')).toBe('true');

    await choose('CNN');
    expect(main.querySelector('.course-hint')).toBeNull();
    quick('Examen').click();
    await fixture.whenStable();
    expect(main.querySelector('app-exam-dialog')?.textContent).toContain('CNN');
  });

  it('un seul cours : sélectionné d’office ; plusieurs : « Tous les cours »', async () => {
    const single = await render(['CNN']);
    expect(single.chipLabel()).toBe('CNN');
    TestBed.resetTestingModule();

    const several = await render(['CNN', 'Docker']);
    expect(several.chipLabel()).toBe('Tous les cours');
  });

  it('une ancienne conversation du tuteur s’ouvre avec sa carte de réponse sourcée et reprend son cours', async () => {
    const { fixture, main, backend, chipLabel } = await render(['CNN', 'Docker'], [conversation(3, 'Docker')], 3);
    backend.expectOne(`${api}/conversations/3/messages`).flush([
      stored(1, 'user', 'Qu’est-ce qu’un conteneur ?', { course: 'Docker' }),
      // Réponse du tuteur, enregistrée avant l'Assistant : pas de kind
      stored(2, 'assistant', 'Un conteneur isole une application [p.2].', {
        course: 'Docker', sources: [{ course: 'Docker', page: 2, score: 0.8, excerpt: 'Un conteneur…' }],
      }),
    ]);
    await fixture.whenStable();
    expect(chipLabel()).toBe('Docker');
    expect(main.querySelector('h1')?.textContent).toBe('Assistant');
    expect(main.querySelector('h1')?.classList).toContain('sr-only');
    expect(main.querySelector('app-answer-card .tag')?.textContent?.trim()).toBe('Tuteur');
    expect(main.querySelector('app-answer-card .page-ref')?.textContent).toBe('p.2');
    expect(main.querySelector('app-sources-list')).not.toBeNull();
  });

  it('une conversation choisie dans la barre latérale s’ouvre et reprend son cours ; « Nouvelle conversation » revient à l’accueil', async () => {
    const { fixture, el, main, backend, chipLabel } = await render(['CNN', 'Docker'], [conversation(3, 'Docker'), conversation(2, 'CNN')]);
    const rows = [...el.querySelectorAll<HTMLButtonElement>('app-conversation-list .item')];
    rows[1].click(); // Conversation 2 (CNN)
    backend.expectOne(`${api}/conversations/2/messages`).flush([stored(1, 'user', 'Bonjour', { course: 'CNN' })]);
    await fixture.whenStable();
    expect(chipLabel()).toBe('CNN');
    expect(main.querySelector('.page')?.classList).not.toContain('page--home');
    expect(rows[1].getAttribute('aria-current')).toBe('true');

    el.querySelector<HTMLButtonElement>('app-shell-sidebar .new')!.click();
    await fixture.whenStable();
    expect(main.querySelector('.page')?.classList).toContain('page--home');
    expect(document.activeElement).toBe(main.querySelector('textarea'));
    expect(TestBed.inject(ShellService).composerFocusRequest()).toBe(false);
  });

  it('bug d : actions rapides et champ forment un seul bloc de saisie, après la liste des messages', async () => {
    const { fixture, main, backend } = await render(['CNN'], [conversation(3, 'CNN')], 3);
    backend.expectOne(`${api}/conversations/3/messages`).flush([stored(1, 'user', 'Bonjour')]);
    await fixture.whenStable();
    const pageEl = main.querySelector('.page')!;
    const composer = pageEl.querySelector('.composer')!;
    expect(pageEl.lastElementChild).toBe(composer);
    expect([...composer.children].map((c) => c.tagName.toLowerCase())).toEqual(['app-upload-panel', 'app-question-input', 'ul']);
    expect(composer.lastElementChild?.classList).toContain('quick-actions');
    // Pendant une conversation, les actions rapides ne s'affichent qu'au focus de la zone de saisie
    expect(composer.lastElementChild?.classList).not.toContain('quick-actions--shown');
    // Les messages ne sont jamais dans la zone de saisie : elle vient après eux, sans les recouvrir
    const thread = pageEl.querySelector('app-companion-thread')!;
    expect(composer.contains(thread)).toBe(false);
    expect(thread.classList).toContain('thread');
    expect(thread.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('bug d : la zone de saisie est opaque et collée en bas ; la liste garde de l’espace sous le dernier échange', async () => {
    const { fixture, main, backend } = await render(['CNN'], [conversation(3, 'CNN')], 3);
    backend.expectOne(`${api}/conversations/3/messages`).flush([stored(1, 'user', 'Bonjour')]);
    await fixture.whenStable();
    const composer = getComputedStyle(main.querySelector('.composer')!);
    expect(composer.position).toBe('sticky');
    expect(composer.bottom).toBe('0px');
    expect(composer.backgroundColor === '' || composer.backgroundColor === 'transparent').toBe(false);
    expect(getComputedStyle(main.querySelector('app-companion-thread')!).paddingBottom).not.toBe('0px');
  });

  it('import d’un PDF : « + » et « Importer un PDF » de la chip ouvrent le sélecteur ; la liste est rechargée et le cours sélectionné', async () => {
    const { fixture, main, backend, openPicker, chipLabel, page } = await render(['CNN', 'Docker']);
    const picker = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);
    main.querySelector<HTMLButtonElement>('.tool[aria-label="Importer un PDF"]')!.click();
    expect(picker).toHaveBeenCalledTimes(1);
    expect((picker.mock.contexts[0] as HTMLInputElement).type).toBe('file');
    (await openPicker()).at(-1)!.click();
    await fixture.whenStable();
    expect(picker).toHaveBeenCalledTimes(2);
    picker.mockRestore();

    (page as unknown as { onUploaded(res: { course: string; chunks: number }): void }).onUploaded({ course: 'Réseaux', chunks: 12 });
    backend.expectOne(`${api}/courses`).flush(['CNN', 'Docker', 'Réseaux']);
    await fixture.whenStable();
    expect(chipLabel()).toBe('Réseaux');
  });

  it('glisser-déposer d’un PDF sur la conversation : surcouche, puis fichier prêt à indexer dans la zone de saisie', async () => {
    const { fixture, main } = await render(['CNN']);
    const pageEl = main.querySelector('.page')!;
    pageEl.dispatchEvent(dragEvent('dragover'));
    await fixture.whenStable();
    expect(main.querySelector('.drop')?.textContent).toContain('Dépose ton PDF ici');

    const pdf = new File(['%PDF'], 'cours-reseaux.pdf', { type: 'application/pdf' });
    pageEl.dispatchEvent(dragEvent('drop', pdf));
    await fixture.whenStable();
    expect(main.querySelector('.drop')).toBeNull();
    const upload = main.querySelector('.composer app-upload-panel')!;
    expect(upload.textContent).toContain('cours-reseaux.pdf');
    expect(upload.querySelector('button.btn')?.textContent?.trim()).toBe('Indexer le cours');
  });
});
