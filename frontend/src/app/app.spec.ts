import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { App } from './app';
import { TOKEN_KEY } from './core/services/auth.service';
import { SHELL_COLLAPSED_KEY } from './core/services/shell.service';

@Component({ template: '' })
class Blank {}

async function render() {
  await TestBed.configureTestingModule({
    imports: [App],
    providers: [provideRouter([{ path: '**', component: Blank }]), provideHttpClient(), provideHttpClientTesting()],
  }).compileComponents();
  const fixture = TestBed.createComponent(App);
  await fixture.whenStable();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

async function createApp(): Promise<HTMLElement> {
  return (await render()).el;
}

describe('App', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => localStorage.clear());

  it('should render the header title', async () => {
    const compiled = await createApp();
    expect(compiled.querySelector('.brand')?.textContent).toContain('AI Study Assistant');
  });

  it('masque la navigation et la déconnexion sans session', async () => {
    const compiled = await createApp();
    expect(compiled.querySelector('nav')).toBeNull();
    expect(compiled.textContent).not.toContain('Déconnexion');
  });

  it('affiche la navigation et la Déconnexion (menu du compte) quand un jeton est présent', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const { fixture, el } = await render();
    expect(el.querySelector('nav')).not.toBeNull();
    el.querySelector<HTMLButtonElement>('app-account-menu .trigger')!.click();
    await fixture.whenStable();
    expect(el.querySelector('app-account-menu [role="menu"]')?.textContent).toContain('Déconnexion');
  });

  it('onglets en haut de la zone principale : Assistant · Flashcards · Résumés · Examens · Mes cours (plus de « Tuteur »)', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const { fixture, el } = await render();
    const nav = el.querySelector('main app-nav-tabs nav')!;
    expect(nav.getAttribute('aria-label')).toBe('Navigation principale');
    const links = [...nav.querySelectorAll<HTMLAnchorElement>('a')];
    expect(links.map((a) => a.textContent?.trim())).toEqual(['Assistant', 'Flashcards', 'Résumés', 'Examens', 'Mes cours']);
    expect(links.map((a) => a.getAttribute('href'))).toEqual(['/companion', '/flashcards', '/summaries', '/exams', '/courses']);
    // La barre latérale ne contient plus la navigation ; le profil est dans le menu du compte
    expect(el.querySelector('header nav')).toBeNull();
    expect(el.querySelectorAll('nav')).toHaveLength(1);
    el.querySelector<HTMLButtonElement>('app-account-menu .trigger')!.click();
    await fixture.whenStable();
    expect(el.querySelector('app-account-menu a[href="/profile"]')?.textContent?.trim()).toBe('Profil et statistiques');
    expect(el.textContent).not.toContain('Tuteur');
    expect(el.querySelector('a[href="/tutor"]')).toBeNull();
  });

  it('onglet actif souligné : aria-current="page" sur la page courante', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const { fixture, el } = await render();
    await TestBed.inject(Router).navigateByUrl('/courses');
    await fixture.whenStable();
    const active = [...el.querySelectorAll<HTMLAnchorElement>('main nav a')].filter(
      (a) => a.getAttribute('aria-current') === 'page',
    );
    expect(active.map((a) => a.textContent?.trim())).toEqual(['Mes cours']);
    expect(active[0].classList).toContain('tab--active');
  });

  it('tiroir (moins de 1024 px) : le bouton Menu ouvre et ferme la barre latérale (Échap, clic extérieur, navigation)', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const { fixture, el } = await render();
    const toggle = el.querySelector<HTMLButtonElement>('.menu-toggle')!;
    const menu = el.querySelector('#main-menu')!;
    expect(toggle.getAttribute('aria-controls')).toBe('main-menu');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(menu.classList).toContain('menu--drawer');
    // Le tiroir contient la barre latérale : nouvelle conversation, recherche, récents, compte
    expect(menu.querySelector('app-shell-sidebar .new')?.textContent?.trim()).toBe('Nouvelle conversation');
    expect(menu.querySelector('app-shell-sidebar app-conversation-list')).not.toBeNull();
    expect(menu.querySelector('app-account-menu .trigger')).not.toBeNull();

    toggle.click();
    await fixture.whenStable();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(menu.classList).toContain('menu--open');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await fixture.whenStable();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    toggle.click();
    await fixture.whenStable();
    el.querySelector<HTMLElement>('.menu-backdrop')!.click(); // clic à l'extérieur
    await fixture.whenStable();
    expect(menu.classList).not.toContain('menu--open');

    toggle.click();
    await fixture.whenStable();
    el.querySelector<HTMLAnchorElement>('main nav a')!.click();
    await fixture.whenStable();
    expect(menu.classList).not.toContain('menu--open');
  });

  describe('barre latérale repliable (à partir de 1024 px)', () => {
    // jsdom ignore les media queries : on affiche la barre comme à partir de 1024 px (sinon rien n'est focalisable)
    let desktop: HTMLStyleElement;
    beforeEach(() => {
      desktop = document.createElement('style');
      desktop.textContent =
        '.sidebar-toggle, .menu { display: block !important; } .app--collapsed .search__rail { visibility: visible !important; }';
      document.head.append(desktop);
    });
    afterEach(() => desktop.remove());

    async function signedIn() {
      localStorage.setItem(TOKEN_KEY, 'jeton');
      const { fixture, el } = await render();
      const toggle = el.querySelector<HTMLButtonElement>('.sidebar-toggle')!;
      return { fixture, el, toggle };
    }

    const ctrlB = (init: KeyboardEventInit = {}) =>
      new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, bubbles: true, cancelable: true, ...init });

    it('ouverte par défaut ; le bouton replie et déplie, avec aria-expanded et un libellé explicite', async () => {
      const { fixture, el, toggle } = await signedIn();
      expect(toggle.getAttribute('aria-controls')).toBe('main-menu');
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(toggle.getAttribute('aria-label')).toBe('Replier la barre latérale');
      expect(el.classList).not.toContain('app--collapsed');

      toggle.focus();
      toggle.click();
      await fixture.whenStable();
      expect(toggle.getAttribute('aria-expanded')).toBe('false');
      expect(toggle.getAttribute('aria-label')).toBe('Déplier la barre latérale');
      expect(el.classList).toContain('app--collapsed');
      expect(document.activeElement).toBe(toggle); // même bouton, toujours au même endroit : le focus reste

      toggle.click();
      await fixture.whenStable();
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      expect(el.classList).not.toContain('app--collapsed');
    });

    it('Ctrl+B (ou Cmd+B) bascule la barre, sauf quand le focus est dans un champ de saisie', async () => {
      const { fixture, el, toggle } = await signedIn();
      const event = ctrlB();
      document.body.dispatchEvent(event);
      await fixture.whenStable();
      expect(event.defaultPrevented).toBe(true);
      expect(toggle.getAttribute('aria-expanded')).toBe('false');

      document.body.dispatchEvent(ctrlB({ ctrlKey: false, metaKey: true }));
      await fixture.whenStable();
      expect(toggle.getAttribute('aria-expanded')).toBe('true');

      // Dans un champ : Ctrl+B garde son comportement habituel
      for (const tag of ['input', 'textarea']) {
        const field = document.createElement(tag);
        document.body.append(field);
        const inField = ctrlB();
        field.dispatchEvent(inField);
        await fixture.whenStable();
        expect(inField.defaultPrevented).toBe(false);
        expect(toggle.getAttribute('aria-expanded')).toBe('true');
        field.remove();
      }

      // Autres combinaisons ignorées
      document.body.dispatchEvent(ctrlB({ shiftKey: true }));
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', bubbles: true }));
      await fixture.whenStable();
      expect(el.classList).not.toContain('app--collapsed');
    });

    it('Ctrl+B sans session : rien ne se passe', async () => {
      const { fixture, el } = await render();
      const event = ctrlB();
      document.body.dispatchEvent(event);
      await fixture.whenStable();
      expect(event.defaultPrevented).toBe(false);
      expect(el.querySelector('.sidebar-toggle')).toBeNull();
    });

    it('état mémorisé dans localStorage et restauré au démarrage', async () => {
      const first = await signedIn();
      first.toggle.click();
      await first.fixture.whenStable();
      expect(localStorage.getItem(SHELL_COLLAPSED_KEY)).toBe('1');

      first.fixture.destroy();
      TestBed.resetTestingModule();
      const again = await signedIn();
      expect(again.toggle.getAttribute('aria-expanded')).toBe('false');
      expect(again.el.classList).toContain('app--collapsed');

      again.toggle.click();
      await again.fixture.whenStable();
      expect(localStorage.getItem(SHELL_COLLAPSED_KEY)).toBe('0');
    });

    it('stockage indisponible : barre ouverte par défaut, la bascule fonctionne quand même', async () => {
      localStorage.setItem(TOKEN_KEY, 'jeton');
      const getItem = Storage.prototype.getItem;
      const setItem = Storage.prototype.setItem;
      const read = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, key: string) {
        if (key === SHELL_COLLAPSED_KEY) {
          throw new Error('stockage bloqué');
        }
        return getItem.call(this, key);
      });
      const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, key: string, value: string) {
        if (key === SHELL_COLLAPSED_KEY) {
          throw new Error('stockage bloqué');
        }
        setItem.call(this, key, value);
      });
      const { fixture, el } = await render();
      const toggle = el.querySelector<HTMLButtonElement>('.sidebar-toggle')!;
      expect(toggle.getAttribute('aria-expanded')).toBe('true');
      toggle.click();
      await fixture.whenStable();
      expect(toggle.getAttribute('aria-expanded')).toBe('false');
      read.mockRestore();
      write.mockRestore();
    });

    it('rail : nouvelle conversation, rechercher, avatar ; nom accessible, info-bulle au survol et au focus, flèches', async () => {
      const { fixture, el, toggle } = await signedIn();
      toggle.click();
      await fixture.whenStable();

      const rail = [...el.querySelectorAll<HTMLElement>('header [data-tip]')].filter((r) => r !== toggle);
      expect(rail.map((r) => r.dataset['tip'])).toEqual(['Nouvelle conversation', 'Rechercher', 'Mon compte']);
      const [newConversation, search, account] = rail;
      expect(newConversation.textContent?.trim()).toBe('Nouvelle conversation'); // libellé masqué visuellement, toujours lu
      expect(search.getAttribute('aria-label')).toBe('Rechercher');
      expect(account.getAttribute('aria-label')).toMatch(/^Compte de Mon compte/);
      // Plus de navigation, de cours ni d'import dans la barre
      expect(el.querySelector('header nav, header app-course-picker, header app-upload-panel')).toBeNull();

      newConversation.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));
      await fixture.whenStable();
      expect(el.querySelector('.shell-tip')?.textContent?.trim()).toBe('Nouvelle conversation');
      newConversation.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
      await fixture.whenStable();
      expect(el.querySelector('.shell-tip')).toBeNull();

      // Flèches : jsdom ne calcule pas la mise en page, chaque icône est considérée visible
      const offsetParent = vi.spyOn(HTMLElement.prototype, 'offsetParent', 'get').mockReturnValue(document.body);
      newConversation.focus();
      newConversation.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
      expect(document.activeElement).toBe(search);
      search.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
      expect(document.activeElement).toBe(newConversation);
      newConversation.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
      expect(document.activeElement).toBe(toggle);
      toggle.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
      expect(document.activeElement).toBe(account);
      offsetParent.mockRestore();
    });

    it('replier avec le focus dans une partie masquée (recherche) : le focus revient sur le bouton de bascule', async () => {
      const { fixture, el, toggle } = await signedIn();
      el.querySelector<HTMLInputElement>('.search__field')!.focus();
      toggle.click(); // jsdom ne déplace pas le focus au clic : il est encore dans la recherche
      await fixture.whenStable();
      expect(document.activeElement).toBe(toggle);
    });

    it('barre ouverte : pas d’info-bulle sur les lignes (le texte est visible), seulement sur le bouton de bascule', async () => {
      const { fixture, el, toggle } = await signedIn();
      el.querySelector('header .new')!.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      await fixture.whenStable();
      expect(el.querySelector('.shell-tip')).toBeNull();
      toggle.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
      await fixture.whenStable();
      expect(el.querySelector('.shell-tip')?.textContent).toMatch(/^Replier la barre \((Ctrl\+B|⌘B)\)$/);
    });
  });
});
