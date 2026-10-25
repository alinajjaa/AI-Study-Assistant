import { TestBed } from '@angular/core/testing';
import { THEME_KEY, ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('suit le système par défaut, sans attribut data-theme', () => {
    const service = TestBed.inject(ThemeService);
    expect(service.preference()).toBe('system');
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('bascule et mémorise le choix', () => {
    const service = TestBed.inject(ThemeService);
    const before = service.theme();
    service.toggle();
    const after = before === 'dark' ? 'light' : 'dark';
    expect(service.theme()).toBe(after);
    expect(document.documentElement.getAttribute('data-theme')).toBe(after);
    expect(localStorage.getItem(THEME_KEY)).toBe(after);

    service.set('system');
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('reprend un choix mémorisé', () => {
    localStorage.setItem(THEME_KEY, 'dark');
    const service = TestBed.inject(ThemeService);
    expect(service.theme()).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
