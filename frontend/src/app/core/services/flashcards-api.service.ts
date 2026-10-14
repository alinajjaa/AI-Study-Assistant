import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CardCount, DeckSummary, FlashcardDeck } from '../models/flashcard.models';

@Injectable({ providedIn: 'root' })
export class FlashcardsApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  /** Génère et enregistre un paquet de flashcards. Pas de timeout : 2 à 6 min avec le LLM local. */
  generate(course: string, count: CardCount): Observable<FlashcardDeck> {
    return this.http.post<FlashcardDeck>(`${this.apiUrl}/courses/${encodeURIComponent(course)}/flashcards`, {
      count,
    });
  }

  /** Paquets de l'étudiant pour ce cours, le plus récent en premier. */
  listDecks(course: string): Observable<DeckSummary[]> {
    return this.http.get<DeckSummary[]>(`${this.apiUrl}/flashcards/decks`, { params: { course } });
  }

  getDeck(id: number): Observable<FlashcardDeck> {
    return this.http.get<FlashcardDeck>(`${this.apiUrl}/flashcards/decks/${id}`);
  }

  deleteDeck(id: number): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.apiUrl}/flashcards/decks/${id}`);
  }

  /** Enregistre une réponse « Je savais » (known = true) ou « À revoir » (known = false). */
  review(deckId: number, concept: string, known: boolean): Observable<unknown> {
    return this.http.post(`${this.apiUrl}/reviews`, { deck_id: deckId, concept, known });
  }
}
