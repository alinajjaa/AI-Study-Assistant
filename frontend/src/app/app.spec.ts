import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';
import { TOKEN_KEY } from './core/services/auth.service';

async function createApp(): Promise<HTMLElement> {
  await TestBed.configureTestingModule({
    imports: [App],
    providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
  }).compileComponents();
  const fixture = TestBed.createComponent(App);
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
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
});
