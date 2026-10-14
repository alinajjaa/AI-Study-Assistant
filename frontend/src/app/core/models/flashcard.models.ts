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

/** Paquet enregistré (GET /api/flashcards/decks/{id}, et réponse de POST /api/courses/{course}/flashcards). */
export interface FlashcardDeck {
  id: number;
  deck_id: number;
  course: string;
  cards: Flashcard[];
  created_at: string;
}

/** Paquet dans la liste « Mes paquets » (GET /api/flashcards/decks). */
export interface DeckSummary {
  id: number;
  course: string;
  card_count: number;
  created_at: string;
}
