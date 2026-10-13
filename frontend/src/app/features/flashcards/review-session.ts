import { computed, signal } from '@angular/core';
import { Flashcard } from '../../core/models/flashcard.models';

export type CardAnswer = 'known' | 'review';

/**
 * Une révision d'un paquet, une carte à la fois (logique pure, sans DOM).
 * Une carte non notée (passée avec les flèches) compte comme « à revoir ».
 */
export class ReviewSession {
  private readonly _cards = signal<readonly Flashcard[]>([]);
  private readonly _index = signal(0);
  private readonly _flipped = signal(false);
  private readonly _finished = signal(false);
  private readonly _answers = signal<readonly (CardAnswer | null)[]>([]);

  readonly cards = this._cards.asReadonly();
  readonly index = this._index.asReadonly();
  readonly flipped = this._flipped.asReadonly();
  readonly finished = this._finished.asReadonly();
  readonly answers = this._answers.asReadonly();

  readonly total = computed(() => this._cards().length);
  readonly current = computed<Flashcard | null>(() => (this._finished() ? null : (this._cards()[this._index()] ?? null)));
  /** Position affichée « 3 / 10 » (1-indexée). */
  readonly position = computed(() => Math.min(this._index() + 1, this.total()));
  /** Cartes notées « Je savais ». */
  readonly knownCount = computed(() => this._answers().filter((a) => a === 'known').length);
  /** Cartes à revoir : notées « À revoir » ou jamais notées. */
  readonly toReview = computed(() => this._cards().filter((_, i) => this._answers()[i] !== 'known'));

  constructor(cards: readonly Flashcard[]) {
    this.reset(cards);
  }

  flip(): void {
    if (!this._finished() && this.current()) {
      this._flipped.update((flipped) => !flipped);
    }
  }

  /** Note la carte (uniquement après retournement) et passe à la suivante. */
  answer(answer: CardAnswer): void {
    if (this._finished() || !this._flipped()) {
      return;
    }
    const index = this._index();
    this._answers.update((answers) => answers.map((a, i) => (i === index ? answer : a)));
    this.next();
  }

  /** Carte suivante ; après la dernière, écran de fin. */
  next(): void {
    if (this._finished()) {
      return;
    }
    this._flipped.set(false);
    if (this._index() < this.total() - 1) {
      this._index.update((i) => i + 1);
    } else {
      this._finished.set(true);
    }
  }

  /** Carte précédente ; depuis l'écran de fin, revient à la dernière carte. */
  previous(): void {
    this._flipped.set(false);
    if (this._finished()) {
      this._finished.set(false);
    } else if (this._index() > 0) {
      this._index.update((i) => i - 1);
    }
  }

  /** Recommence avec ces cartes (tout le paquet ou seulement celles à revoir). */
  reset(cards: readonly Flashcard[]): void {
    this._cards.set([...cards]);
    this._answers.set(cards.map(() => null));
    this._index.set(0);
    this._flipped.set(false);
    this._finished.set(cards.length === 0);
  }
}
