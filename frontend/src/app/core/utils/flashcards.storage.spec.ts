import { StoredDeck } from '../models/flashcard.models';
import { deckStorageKey, loadDeck, saveDeck } from './flashcards.storage';

const deck: StoredDeck = {
  course: 'CNN_intro',
  cards: [
    { concept: 'Convolution', front: "Qu'est-ce qu'une convolution ?", back: 'Un filtre glissant sur l’image.', page: 3 },
    { concept: 'Pooling', front: 'À quoi sert le pooling ?', back: 'À réduire la taille des cartes.', page: 7 },
  ],
  requested: 10,
  createdAt: 1_760_000_000_000,
};

describe('flashcards.storage', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('mémorise et relit le paquet du cours', () => {
    expect(saveDeck(deck)).toBe(true);
    expect(loadDeck('CNN_intro')).toEqual(deck);
  });

  it('garde un paquet distinct par cours', () => {
    saveDeck(deck);
    saveDeck({ ...deck, course: 'Réseaux', cards: [deck.cards[0]] });
    expect(loadDeck('CNN_intro')?.cards).toHaveLength(2);
    expect(loadDeck('Réseaux')?.cards).toHaveLength(1);
    expect(loadDeck('Autre')).toBeNull();
  });

  it('ignore les cartes invalides et rejette un paquet sans carte valide', () => {
    localStorage.setItem(
      deckStorageKey('CNN_intro'),
      JSON.stringify({ ...deck, cards: [deck.cards[0], { concept: 'X', front: 'Q ?', back: 'R', page: 0 }, 'texte'] }),
    );
    expect(loadDeck('CNN_intro')?.cards).toEqual([deck.cards[0]]);

    localStorage.setItem(deckStorageKey('CNN_intro'), JSON.stringify({ cards: [{ front: 'Q ?' }] }));
    expect(loadDeck('CNN_intro')).toBeNull();
  });

  it('déduit un nombre demandé plausible pour une ancienne sauvegarde', () => {
    localStorage.setItem(deckStorageKey('CNN_intro'), JSON.stringify({ cards: deck.cards }));
    expect(loadDeck('CNN_intro')).toMatchObject({ requested: 10, createdAt: 0 });
  });

  it('résiste à un JSON corrompu', () => {
    localStorage.setItem(deckStorageKey('CNN_intro'), '{pas du json');
    expect(loadDeck('CNN_intro')).toBeNull();
  });

  it('résiste à un stockage indisponible', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(saveDeck(deck)).toBe(false);
    expect(loadDeck('CNN_intro')).toBeNull();
  });
});
