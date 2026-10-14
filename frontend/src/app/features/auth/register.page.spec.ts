import { safeReturnUrl } from './login.page';
import { validateRegistration } from './register.page';

describe('validateRegistration', () => {
  it('accepte un email et un mot de passe valides', () => {
    expect(validateRegistration('ali@example.com', 'motdepasse')).toBeNull();
  });

  it('refuse un email invalide', () => {
    expect(validateRegistration('ali@', 'motdepasse')).toBe('Adresse email invalide.');
  });

  it('impose 8 à 72 caractères (en octets) pour le mot de passe', () => {
    expect(validateRegistration('ali@example.com', 'court')).toContain('au moins 8');
    expect(validateRegistration('ali@example.com', 'x'.repeat(72))).toBeNull();
    expect(validateRegistration('ali@example.com', 'é'.repeat(40))).toContain('dépasser 72');
  });
});

describe('safeReturnUrl', () => {
  it('garde un chemin interne, refuse le reste', () => {
    expect(safeReturnUrl('/flashcards')).toBe('/flashcards');
    expect(safeReturnUrl('//pirate.example')).toBe('/tutor');
    expect(safeReturnUrl('https://pirate.example')).toBe('/tutor');
    expect(safeReturnUrl(null)).toBe('/tutor');
  });
});
