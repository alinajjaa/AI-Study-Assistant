import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { TOKEN_KEY } from './core/services/auth.service';

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

  it('affiche la navigation et le bouton Déconnexion quand un jeton est présent', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const compiled = await createApp();
    expect(compiled.querySelector('nav')).not.toBeNull();
    expect(compiled.textContent).toContain('Déconnexion');
  });

  it('menu : Assistant · Flashcards · Résumés · Mes examens · Mon profil (plus de « Tuteur de cours »)', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const compiled = await createApp();
    const links = [...compiled.querySelectorAll<HTMLAnchorElement>('nav a')];
    expect(links.map((a) => a.textContent?.trim())).toEqual(['Assistant', 'Flashcards', 'Résumés', 'Mes examens', 'Mon profil']);
    expect(links[0].getAttribute('href')).toBe('/companion');
    expect(compiled.textContent).not.toContain('Tuteur');
    expect(compiled.querySelector('a[href="/tutor"]')).toBeNull();
  });

  it('menu compact : le bouton Menu ouvre et ferme le panneau (Échap et clic sur un lien le ferment)', async () => {
    localStorage.setItem(TOKEN_KEY, 'jeton');
    const { fixture, el } = await render();
    const toggle = el.querySelector<HTMLButtonElement>('.menu-toggle')!;
    const menu = el.querySelector('#main-menu')!;
    expect(toggle.getAttribute('aria-controls')).toBe('main-menu');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    // Le menu contient la navigation, l'email et la Déconnexion (une seule ligne à partir de 1280 px)
    expect(menu.querySelector('nav')).not.toBeNull();
    expect(menu.textContent).toContain('Déconnexion');

    toggle.click();
    await fixture.whenStable();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(menu.classList).toContain('menu--open');

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await fixture.whenStable();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    toggle.click();
    await fixture.whenStable();
    menu.querySelector<HTMLAnchorElement>('nav a')!.click();
    await fixture.whenStable();
    expect(menu.classList).not.toContain('menu--open');
  });
});
