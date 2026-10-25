import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { Conversation } from '../../core/models/conversation.models';
import { AuthService, TOKEN_KEY } from '../../core/services/auth.service';
import { ConversationsService } from '../../core/services/conversations.service';
import { ShellService } from '../../core/services/shell.service';
import { ThemeService } from '../../core/services/theme.service';
import { displayName } from '../account-menu/account-menu';
import { ShellSidebar } from './shell-sidebar';

const api = environment.apiUrl;

function conversation(id: number, title: string, course: string | null = null): Conversation {
  return { id, title, course, created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z' };
}

async function render(conversations: Conversation[] | 'error' = [], openConversation?: number) {
  localStorage.clear();
  localStorage.setItem(TOKEN_KEY, 'jeton');
  if (openConversation !== undefined) {
    localStorage.setItem('ai-study-assistant.conversation', String(openConversation));
  }
  TestBed.configureTestingModule({
    providers: [provideRouter([{ path: '**', children: [] }]), provideHttpClient(), provideHttpClientTesting()],
  });
  TestBed.inject(ConversationsService);
  TestBed.tick();
  const backend = TestBed.inject(HttpTestingController);
  const auth = TestBed.inject(AuthService);
  auth.restoreSession();
  backend.expectOne(`${api}/me`).flush({ id: 1, email: 'camille.martin@example.com', level: 'intermediaire', created_at: '2026-10-01T00:00:00Z' });
  const fixture = TestBed.createComponent(ShellSidebar);
  const list = backend.expectOne(`${api}/conversations`);
  if (conversations === 'error') {
    list.flush({ detail: 'Panne' }, { status: 500, statusText: 'Erreur' });
  } else {
    list.flush(conversations);
  }
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const rows = () => [...el.querySelectorAll<HTMLButtonElement>('app-conversation-list .item')];
  const search = el.querySelector<HTMLInputElement>('.search__field')!;
  const type = async (value: string) => {
    search.value = value;
    search.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  };
  return { fixture, el, backend, auth, rows, search, type };
}

describe('ShellSidebar (barre latérale minimaliste)', () => {
  afterEach(() => localStorage.clear());

  it('ne contient que : nouvelle conversation, recherche, récents, compte (ni navigation, ni cours, ni import)', async () => {
    const { el } = await render([conversation(1, 'Quiz Docker')]);
    expect([...el.children].map((c) => c.className)).toEqual(['top', 'recents', 'foot']);
    expect(el.querySelector('.top .new')?.textContent?.trim()).toBe('Nouvelle conversation');
    expect(el.querySelector('.top input[type="search"]')?.getAttribute('aria-label')).toBe('Rechercher une conversation');
    expect(el.querySelector('.recents app-conversation-list h2')?.textContent?.trim()).toBe('Récents');
    expect(el.querySelector('.foot app-account-menu')).not.toBeNull();
    expect(el.querySelector('nav')).toBeNull();
    expect(el.querySelector('app-course-picker, app-upload-panel, .course-avatar')).toBeNull();
    expect(el.textContent).not.toContain('Mes cours');
    // Rail (barre repliée) : nouvelle conversation, rechercher, avatar
    const rail = [...el.querySelectorAll<HTMLElement>('[data-tip]')].map((b) => b.dataset['tip']);
    expect(rail).toEqual(['Nouvelle conversation', 'Rechercher', 'Camille']);
  });

  it('récents : une ligne par conversation (titre complet en infobulle), la plus récente en tête, l’ouverte marquée', async () => {
    const long = 'Une question très longue sur les réseaux de neurones convolutifs et le pooling';
    const { rows } = await render([conversation(2, long), conversation(1, 'Quiz Docker')], 1);
    TestBed.inject(HttpTestingController).expectOne(`${api}/conversations/1/messages`).flush([]);
    expect(rows().map((b) => b.title)).toEqual([long, 'Quiz Docker']);
    expect(rows().map((b) => b.querySelector('.name')?.textContent?.trim())).toEqual([long, 'Quiz Docker']);
    expect(rows()[1].getAttribute('aria-current')).toBe('true');
    expect(rows()[1].closest('li')?.classList).toContain('row--active');
    expect(rows()[0].getAttribute('aria-current')).toBeNull();
    expect(rows()[0].textContent).not.toMatch(/\d+ (oct|sept)\./); // pas de date sur les lignes
  });

  it('menu « ⋯ » : renommer (Entrée valide, Échap annule) et supprimer avec la confirmation existante', async () => {
    const { fixture, el, backend } = await render([conversation(2, 'Hier'), conversation(1, 'Quiz Docker')]);
    const more = el.querySelector<HTMLButtonElement>('[aria-label="Actions pour la conversation Hier"]')!;
    expect(more.getAttribute('aria-haspopup')).toBe('menu');
    more.click();
    await fixture.whenStable();
    expect(more.getAttribute('aria-expanded')).toBe('true');
    let items = [...el.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')];
    expect(items.map((b) => b.textContent?.trim())).toEqual(['Renommer', 'Supprimer']);

    // Échap ferme le menu et rend le focus au bouton « ⋯ »
    items[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await fixture.whenStable();
    expect(el.querySelector('[role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(more);

    more.click();
    await fixture.whenStable();
    el.querySelector<HTMLButtonElement>('[role="menuitem"]')!.click(); // Renommer
    await fixture.whenStable();
    const input = el.querySelector<HTMLInputElement>('.rename')!;
    input.value = 'Révisions réseaux';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }));
    const patch = backend.expectOne((r) => r.method === 'PATCH' && r.url === `${api}/conversations/2`);
    expect(patch.request.body).toEqual({ title: 'Révisions réseaux' });
    patch.flush(conversation(2, 'Révisions réseaux'));
    await fixture.whenStable();

    el.querySelector<HTMLButtonElement>('[aria-label="Actions pour la conversation Révisions réseaux"]')!.click();
    await fixture.whenStable();
    items = [...el.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')];
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    items[1].click();
    expect(confirm).toHaveBeenCalled();
    backend.expectOne((r) => r.method === 'DELETE' && r.url === `${api}/conversations/2`).flush({ deleted: 2 });
    await fixture.whenStable();
    confirm.mockRestore();
    expect([...el.querySelectorAll('app-conversation-list .name')].map((n) => n.textContent?.trim())).toEqual(['Quiz Docker']);
  });

  it('la recherche filtre les conversations (sans accents ni casse) ; Échap la vide', async () => {
    const { el, rows, search, type, fixture } = await render([conversation(1, 'Quiz réseaux'), conversation(2, 'Docker')]);
    await type('RESEAU');
    expect(rows().map((b) => b.title)).toEqual(['Quiz réseaux']);

    await type('zzz');
    expect(el.querySelector('app-conversation-list .empty')?.textContent).toContain('Aucune conversation ne correspond');

    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
    search.dispatchEvent(escape);
    await fixture.whenStable();
    expect(search.value).toBe('');
    expect(rows()).toHaveLength(2);
  });

  it('état vide en une ligne, avec lien d’action ; erreur de chargement avec « Réessayer »', async () => {
    const empty = await render([]);
    expect(empty.el.querySelector('app-conversation-list .empty')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'Aucune conversation · en démarrer une',
    );
    expect(empty.el.querySelector('app-conversation-list .empty .link')?.tagName).toBe('BUTTON');
    TestBed.resetTestingModule();

    const failed = await render('error');
    expect(failed.el.querySelector('.load-error')?.textContent).toContain('Conversations indisponibles');
    failed.el.querySelector<HTMLButtonElement>('.load-error .link')!.click();
    failed.backend.expectOne(`${api}/conversations`).flush([conversation(1, 'Quiz Docker')]);
    await failed.fixture.whenStable();
    expect(failed.el.querySelector('.load-error')).toBeNull();
    expect(failed.rows()).toHaveLength(1);
  });

  it('choisir une conversation l’ouvre dans l’Assistant et ferme le tiroir ; « Nouvelle conversation » repart de zéro', async () => {
    const { fixture, el, backend, rows } = await render([conversation(2, 'Hier'), conversation(1, 'Quiz Docker')]);
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigateByUrl');
    const shell = TestBed.inject(ShellService);
    const conversations = TestBed.inject(ConversationsService);
    shell.menuOpen.set(true);

    rows()[0].click();
    backend.expectOne(`${api}/conversations/2/messages`).flush([]);
    await fixture.whenStable();
    expect(conversations.activeId()).toBe(2);
    expect(navigate).toHaveBeenCalledWith('/companion');
    expect(shell.menuOpen()).toBe(false);

    el.querySelector<HTMLButtonElement>('.new')!.click();
    await fixture.whenStable();
    expect(conversations.activeId()).toBeNull();
    expect(shell.composerFocusRequest()).toBe(true);
    expect(navigate).toHaveBeenCalledTimes(2);
  });

  it('rail « Rechercher » : déplie la barre et place le focus dans la recherche', async () => {
    const { fixture, el, search } = await render([conversation(1, 'Quiz Docker')]);
    const shell = TestBed.inject(ShellService);
    shell.toggleCollapsed();
    el.querySelector<HTMLButtonElement>('.search__rail')!.click();
    await fixture.whenStable();
    expect(shell.collapsed()).toBe(false);
    expect(document.activeElement).toBe(search);
  });

  it('compte : avatar + prénom ; menu Profil et statistiques, Thème, Déconnexion (clavier, Échap)', async () => {
    const { fixture, el, auth } = await render([]);
    const trigger = el.querySelector<HTMLButtonElement>('app-account-menu .trigger')!;
    expect(trigger.querySelector('.avatar')?.textContent).toBe('C');
    expect(trigger.querySelector('.trigger__name')?.textContent).toBe('Camille');
    expect(trigger.getAttribute('aria-haspopup')).toBe('menu');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');

    trigger.click();
    await fixture.whenStable();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    const menu = el.querySelector('app-account-menu [role="menu"]')!;
    expect(menu.textContent).toContain('camille.martin@example.com');
    const items = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')];
    expect(items.map((i) => i.textContent?.trim())).toEqual(['Profil et statistiques', expect.stringMatching(/^Thème (sombre|clair)$/), 'Déconnexion']);
    expect(items[0].getAttribute('href')).toBe('/profile');
    expect(document.activeElement).toBe(items[0]);

    // Flèches entre les entrées ; le thème change et le menu reste ouvert
    items[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    expect(document.activeElement).toBe(items[1]);
    const theme = TestBed.inject(ThemeService);
    const before = theme.theme();
    items[1].click();
    await fixture.whenStable();
    expect(theme.theme()).not.toBe(before);
    expect(el.querySelector('app-account-menu [role="menu"]')).not.toBeNull();

    // Échap ferme le menu (et seulement lui : le tiroir reste ouvert) et rend le focus au bouton
    const shell = TestBed.inject(ShellService);
    shell.menuOpen.set(true);
    items[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await fixture.whenStable();
    expect(el.querySelector('app-account-menu [role="menu"]')).toBeNull();
    expect(document.activeElement).toBe(trigger);

    trigger.click();
    await fixture.whenStable();
    const logout = vi.spyOn(auth, 'logout').mockImplementation(() => undefined);
    [...el.querySelectorAll<HTMLElement>('app-account-menu [role="menuitem"]')][2].click();
    expect(logout).toHaveBeenCalled();
    expect(shell.menuOpen()).toBe(false);
    theme.toggle(); // remet le thème d'origine
  });

  it('prénom affiché à partir de l’email', () => {
    expect(displayName('camille.martin@example.com')).toBe('Camille');
    expect(displayName('etudiant@example.com')).toBe('Etudiant');
    expect(displayName('JEAN_dupont42@x.fr')).toBe('Jean');
    expect(displayName('42@x.fr')).toBe('42');
  });
});
