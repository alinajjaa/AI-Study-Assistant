import { CARD_COUNTS, CardCount, Flashcard, StoredDeck } from '../models/flashcard.models';

const KEY_PREFIX = 'ai-study-assistant.flashcards.';

/** Une clé par cours : un paquet volumineux n'empêche pas de mémoriser les autres. */
export function deckStorageKey(course: string): string {
  return KEY_PREFIX + encodeURIComponent(course);
}

function readCard(value: unknown): Flashcard | null {
  if (typeof value !== 'object' || value === null) {
    return null;
  }
  const concept = 'concept' in value ? value.concept : null;
  const front = 'front' in value ? value.front : null;
  const back = 'back' in value ? value.back : null;
  const page = 'page' in value ? value.page : null;
  if (
    typeof concept !== 'string' ||
    typeof front !== 'string' ||
    typeof back !== 'string' ||
    typeof page !== 'number' ||
    !Number.isInteger(page) ||
    page < 1
  ) {
    return null;
  }
  return { concept, front, back, page };
}

/** Nombre demandé inconnu (ancienne sauvegarde) : plus petit choix contenant toutes les cartes. */
function smallestCountFor(cardCount: number): CardCount {
  return CARD_COUNTS.find((n) => n >= cardCount) ?? CARD_COUNTS[CARD_COUNTS.length - 1];
}

/** Dernier paquet généré pour ce cours, ou null (absent, corrompu, stockage indisponible). */
export function loadDeck(course: string): StoredDeck | null {
  try {
    const raw = localStorage.getItem(deckStorageKey(course));
    const saved: unknown = raw ? JSON.parse(raw) : null;
    if (typeof saved !== 'object' || saved === null || !('cards' in saved) || !Array.isArray(saved.cards)) {
      return null;
    }
    const cards = saved.cards.map(readCard).filter((card): card is Flashcard => card !== null);
    if (cards.length === 0) {
      return null;
    }
    const requested = 'requested' in saved ? saved.requested : null;
    const createdAt = 'createdAt' in saved ? saved.createdAt : null;
    return {
      course,
      cards,
      requested: CARD_COUNTS.find((n) => n === requested) ?? smallestCountFor(cards.length),
      createdAt: typeof createdAt === 'number' ? createdAt : 0,
    };
  } catch {
    return null;
  }
}

/** Mémorise le paquet ; renvoie false si le stockage est indisponible (navigation privée, quota…). */
export function saveDeck(deck: StoredDeck): boolean {
  try {
    localStorage.setItem(deckStorageKey(deck.course), JSON.stringify(deck));
    return true;
  } catch {
    return false;
  }
}
