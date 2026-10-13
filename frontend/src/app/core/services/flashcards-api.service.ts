import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CardCount, FlashcardDeck } from '../models/flashcard.models';

@Injectable({ providedIn: 'root' })
export class FlashcardsApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  /** Génère un paquet de flashcards. Pas de timeout : 2 à 6 min avec le LLM local. */
  generate(course: string, count: CardCount): Observable<FlashcardDeck> {
    return this.http.post<FlashcardDeck>(`${this.apiUrl}/courses/${encodeURIComponent(course)}/flashcards`, {
      count,
    });
  }
}
