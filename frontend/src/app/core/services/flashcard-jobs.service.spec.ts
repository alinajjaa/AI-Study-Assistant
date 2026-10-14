import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { ToastService } from '../../shared/components/toast/toast.service';
import { FLASHCARD_MINUTES, FlashcardDeck } from '../models/flashcard.models';
import { FlashcardJobsService } from './flashcard-jobs.service';
import { FlashcardsApiService } from './flashcards-api.service';

const cards = (n: number): FlashcardDeck['cards'] =>
  Array.from({ length: n }, (_, i) => ({ concept: `C${i}`, front: `Question ${i} ?`, back: `Réponse ${i}`, page: i + 1 }));
const deck = (n: number): FlashcardDeck => ({
  id: 7,
  deck_id: 7,
  course: 'CNN',
  cards: cards(n),
  created_at: '2026-10-14T10:00:00Z',
});

describe('FlashcardJobsService', () => {
  let response: Subject<FlashcardDeck>;
  let jobs: FlashcardJobsService;
  let toasts: ToastService;

  beforeEach(() => {
    localStorage.clear();
    response = new Subject<FlashcardDeck>();
    TestBed.configureTestingModule({
      providers: [{ provide: FlashcardsApiService, useValue: { generate: () => response } }],
    });
    jobs = TestBed.inject(FlashcardJobsService);
    toasts = TestBed.inject(ToastService);
  });

  const lastToast = () => toasts.toasts().at(-1);

  it('annonce le lancement avec la durée estimée et marque le cours en génération', () => {
    jobs.start('CNN', 20);
    expect(jobs.isGenerating('CNN')).toBe(true);
    expect(lastToast()).toMatchObject({ kind: 'info', message: expect.stringContaining('Environ 5 min') });
  });

  it('utilise les durées mesurées : 10 → 3 min, 20 → 5 min, 30 → 8 min', () => {
    const expected = { 10: 3, 20: 5, 30: 8 } as const;
    expect(FLASHCARD_MINUTES).toEqual(expected);
    for (const count of [10, 20, 30] as const) {
      jobs.start(`cours-${count}`, count);
      expect(lastToast()?.message).toContain(`Environ ${expected[count]} min`);
    }
  });

  it('signale le paquet enregistré et annonce le nombre réel de cartes', () => {
    jobs.start('CNN', 10);
    response.next(deck(10));
    response.complete();

    expect(jobs.isGenerating('CNN')).toBe(false);
    expect(jobs.lastDeck()?.deck_id).toBe(7);
    expect(localStorage.length).toBe(0); // plus de paquets dans le navigateur
    expect(lastToast()).toMatchObject({ kind: 'success', title: 'Flashcards « CNN » prêtes : 10 cartes' });
  });

  it('avertit quand le backend renvoie moins de cartes que demandé', () => {
    jobs.start('CNN', 30);
    response.next(deck(12));
    response.complete();

    expect(lastToast()).toMatchObject({ kind: 'warning', title: 'Flashcards « CNN » prêtes : 12 cartes au lieu de 30' });
  });

  it("affiche l'erreur de l'intercepteur et libère le cours", () => {
    jobs.start('CNN', 10);
    response.error(new Error('Le cours « CNN » est introuvable ou vide.'));

    expect(jobs.isGenerating('CNN')).toBe(false);
    expect(lastToast()).toMatchObject({ kind: 'error', message: 'Le cours « CNN » est introuvable ou vide.' });
  });

  it('refuse une seconde génération pour le même cours', () => {
    jobs.start('CNN', 10);
    jobs.start('CNN', 20);
    expect(toasts.toasts().filter((t) => t.kind === 'info')).toHaveLength(1);
  });
});
