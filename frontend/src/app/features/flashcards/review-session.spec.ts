import { Flashcard } from '../../core/models/flashcard.models';
import { ReviewSession } from './review-session';

const card = (n: number): Flashcard => ({
  concept: `Notion ${n}`,
  front: `Question ${n} ?`,
  back: `Réponse ${n}.`,
  page: n,
});
const deck = [card(1), card(2), card(3), card(4)];

describe('ReviewSession', () => {
  it('démarre sur le recto de la première carte', () => {
    const s = new ReviewSession(deck);
    expect(s.current()).toEqual(card(1));
    expect(s.flipped()).toBe(false);
    expect(s.position()).toBe(1);
    expect(s.total()).toBe(4);
    expect(s.finished()).toBe(false);
  });

  it('retourne la carte dans les deux sens', () => {
    const s = new ReviewSession(deck);
    s.flip();
    expect(s.flipped()).toBe(true);
    s.flip();
    expect(s.flipped()).toBe(false);
  });

  it("ne note pas une carte avant qu'elle soit retournée", () => {
    const s = new ReviewSession(deck);
    s.answer('known');
    expect(s.index()).toBe(0);
    expect(s.knownCount()).toBe(0);
  });

  it('note la carte, passe à la suivante et remet le recto', () => {
    const s = new ReviewSession(deck);
    s.flip();
    s.answer('known');
    expect(s.index()).toBe(1);
    expect(s.flipped()).toBe(false);
    expect(s.answers()).toEqual(['known', null, null, null]);
  });

  it('calcule le score et termine après la dernière carte', () => {
    const s = new ReviewSession(deck);
    for (const answer of ['known', 'review', 'known', 'known'] as const) {
      s.flip();
      s.answer(answer);
    }
    expect(s.finished()).toBe(true);
    expect(s.current()).toBeNull();
    expect(s.knownCount()).toBe(3);
    expect(s.toReview()).toEqual([card(2)]);
  });

  it('compte une carte passée sans être notée comme « à revoir »', () => {
    const s = new ReviewSession(deck);
    s.flip();
    s.answer('known'); // carte 1
    s.next(); // carte 2 passée avec →
    s.flip();
    s.answer('known'); // carte 3
    s.flip();
    s.answer('review'); // carte 4
    expect(s.finished()).toBe(true);
    expect(s.toReview()).toEqual([card(2), card(4)]);
  });

  it('navigue avec précédent / suivant sans dépasser le début', () => {
    const s = new ReviewSession(deck);
    s.previous();
    expect(s.index()).toBe(0);
    s.next();
    s.flip();
    s.previous();
    expect(s.index()).toBe(0);
    expect(s.flipped()).toBe(false);
  });

  it("revient de l'écran de fin à la dernière carte", () => {
    const s = new ReviewSession([card(1)]);
    s.next();
    expect(s.finished()).toBe(true);
    s.previous();
    expect(s.finished()).toBe(false);
    expect(s.current()).toEqual(card(1));
  });

  it('« Revoir les cartes à revoir » ne garde que celles-là, avec un score remis à zéro', () => {
    const s = new ReviewSession(deck);
    for (const answer of ['review', 'known', 'review', 'known'] as const) {
      s.flip();
      s.answer(answer);
    }
    s.reset(s.toReview());
    expect(s.cards()).toEqual([card(1), card(3)]);
    expect(s.total()).toBe(2);
    expect(s.knownCount()).toBe(0);
    expect(s.index()).toBe(0);
    expect(s.finished()).toBe(false);
  });

  it('un paquet vide est directement terminé', () => {
    const s = new ReviewSession([]);
    expect(s.finished()).toBe(true);
    s.flip();
    expect(s.flipped()).toBe(false);
  });
});
