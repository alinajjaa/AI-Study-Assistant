/** Nombre de cartes demandé au backend. */
export type CardCount = 10 | 20 | 30;

export const CARD_COUNTS: readonly CardCount[] = [10, 20, 30];

export const DEFAULT_CARD_COUNT: CardCount = 10;

/** Durée de génération mesurée (Ollama qwen2.5:7b), en minutes. */
export const FLASHCARD_MINUTES: Readonly<Record<CardCount, number>> = { 10: 3, 20: 5, 30: 8 };

export interface Flashcard {
  /** Notion du cours (petite étiquette au recto). */
  concept: string;
  /** Question. */
  front: string;
  /** Réponse. */
  back: string;
  /** Page du cours. */
  page: number;
}

/** Réponse de POST /api/courses/{course}/flashcards. */
export interface FlashcardDeck {
  course: string;
  cards: Flashcard[];
}

/** Paquet mémorisé dans localStorage pour réviser sans regénérer. */
export interface StoredDeck {
  course: string;
  cards: Flashcard[];
  /** Nombre de cartes demandé (le backend peut en renvoyer moins pour un petit cours). */
  requested: CardCount;
  /** Date de génération (ms). */
  createdAt: number;
}
