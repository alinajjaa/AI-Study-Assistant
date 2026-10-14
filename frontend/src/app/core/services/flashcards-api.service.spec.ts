import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { FlashcardDeck } from '../models/flashcard.models';
import { FlashcardsApiService } from './flashcards-api.service';

describe('FlashcardsApiService', () => {
  let api: FlashcardsApiService;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    api = TestBed.inject(FlashcardsApiService);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('POST /courses/{course}/flashcards avec {count}, nom de cours encodé', async () => {
    const deck: FlashcardDeck = {
      id: 3,
      deck_id: 3,
      created_at: '2026-10-14T10:00:00Z',
      course: 'Réseaux & IA',
      cards: [{ concept: 'TCP', front: 'Que garantit TCP ?', back: "L'ordre et la fiabilité.", page: 12 }],
    };
    const result = firstValueFrom(api.generate('Réseaux & IA', 20));

    const req = backend.expectOne(`${environment.apiUrl}/courses/R%C3%A9seaux%20%26%20IA/flashcards`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ count: 20 });
    req.flush(deck);

    expect(await result).toEqual(deck);
  });

  it('liste, ouvre et supprime les paquets enregistrés', () => {
    api.listDecks('CNN').subscribe();
    const list = backend.expectOne((r) => r.url === `${environment.apiUrl}/flashcards/decks`);
    expect(list.request.params.get('course')).toBe('CNN');
    list.flush([]);

    api.getDeck(4).subscribe();
    backend.expectOne(`${environment.apiUrl}/flashcards/decks/4`).flush({});

    api.deleteDeck(4).subscribe();
    expect(backend.expectOne(`${environment.apiUrl}/flashcards/decks/4`).request.method).toBe('DELETE');
  });

  it('POST /reviews avec deck_id, concept et known', () => {
    api.review(4, 'Pooling', false).subscribe();
    const req = backend.expectOne(`${environment.apiUrl}/reviews`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ deck_id: 4, concept: 'Pooling', known: false });
    req.flush({});
  });
});
