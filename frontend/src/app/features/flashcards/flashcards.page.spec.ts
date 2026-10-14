import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { DeckSummary, FlashcardDeck } from '../../core/models/flashcard.models';
import { FlashcardsApiService } from '../../core/services/flashcards-api.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { FlashcardsPage } from './flashcards.page';

const summary: DeckSummary = { id: 9, course: 'CNN', card_count: 2, created_at: '2026-10-14T10:00:00Z' };
const deck: FlashcardDeck = {
  id: 9,
  deck_id: 9,
  course: 'CNN',
  created_at: '2026-10-14T10:00:00Z',
  cards: [
    { concept: 'Pooling', front: 'Rôle du pooling ?', back: 'Réduire la taille.', page: 3 },
    { concept: 'Filtre', front: 'Qu’est-ce qu’un filtre ?', back: 'Une matrice de poids.', page: 4 },
  ],
};

function setup(decks: DeckSummary[] = []) {
  const flashcards = {
    listDecks: vi.fn(() => of(decks)),
    getDeck: vi.fn(() => of(deck)),
    review: vi.fn(() => of({})),
    deleteDeck: vi.fn(() => of({ deleted: 9 })),
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: TutorApiService, useValue: { getCourses: () => of(['CNN']) } },
      { provide: FlashcardsApiService, useValue: flashcards },
    ],
  });
  return flashcards;
}

describe('FlashcardsPage — durée estimée', () => {
  beforeEach(() => setup());

  it('affiche 3, 5 et 8 min pour 10, 20 et 30 cartes', async () => {
    const fixture = TestBed.createComponent(FlashcardsPage);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const minutesFor = async (count: string): Promise<string | undefined> => {
      const segment = [...el.querySelectorAll<HTMLButtonElement>('.segment')].find((b) => b.textContent?.trim() === count);
      segment?.click();
      await fixture.whenStable();
      return /environ (\d+) min/.exec(el.querySelector('.estimate')?.textContent ?? '')?.[1];
    };

    expect(await minutesFor('10')).toBe('3');
    expect(await minutesFor('20')).toBe('5');
    expect(await minutesFor('30')).toBe('8');
  });
});

describe('FlashcardsPage — paquets enregistrés', () => {
  it('liste « Mes paquets » du cours depuis le backend', async () => {
    const api = setup([summary]);
    const fixture = TestBed.createComponent(FlashcardsPage);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(api.listDecks).toHaveBeenCalledWith('CNN');
    expect(el.querySelector('.deck-list')?.textContent).toContain('2 cartes');
    expect(el.querySelector('.deck__badge')?.textContent).toContain('Dernier paquet');
  });

  it('enregistre chaque « Je savais » / « À revoir » pendant la révision', async () => {
    const api = setup([summary]);
    const fixture = TestBed.createComponent(FlashcardsPage);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const button = (label: string) =>
      [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes(label));

    button('Réviser')?.click();
    await fixture.whenStable();
    expect(api.getDeck).toHaveBeenCalledWith(9);

    button('Afficher la réponse')?.click();
    await fixture.whenStable();
    button('Je savais')?.click();
    await fixture.whenStable();
    button('Afficher la réponse')?.click();
    await fixture.whenStable();
    button('À revoir')?.click();
    await fixture.whenStable();

    expect(api.review).toHaveBeenNthCalledWith(1, 9, 'Pooling', true);
    expect(api.review).toHaveBeenNthCalledWith(2, 9, 'Filtre', false);
    expect(el.textContent).toContain('Révision terminée');
  });
});
