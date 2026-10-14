import { Injectable, computed, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { ToastService } from '../../shared/components/toast/toast.service';
import { toMessage } from '../interceptors/error.interceptor';
import { CardCount, FLASHCARD_MINUTES, FlashcardDeck } from '../models/flashcard.models';
import { FlashcardsApiService } from './flashcards-api.service';

/**
 * Générations de flashcards en arrière-plan, indépendantes des composants :
 * elles continuent si l'on retourne au tuteur. Les paquets sont enregistrés par le backend.
 */
@Injectable({ providedIn: 'root' })
export class FlashcardJobsService {
  private readonly api = inject(FlashcardsApiService);
  private readonly toasts = inject(ToastService);
  private ticker: ReturnType<typeof setInterval> | undefined;

  private readonly _jobs = signal<ReadonlyMap<string, number>>(new Map());
  private readonly _now = signal(Date.now());
  private readonly _lastDeck = signal<FlashcardDeck | null>(null);

  /** Cours → heure de début (ms). */
  readonly jobs = this._jobs.asReadonly();
  /** Heure courante, rafraîchie chaque seconde tant qu'une génération tourne. */
  readonly now = this._now.asReadonly();
  readonly hasJobs = computed(() => this._jobs().size > 0);
  /** Dernier paquet généré : la page Flashcards recharge « Mes paquets » quand il change. */
  readonly lastDeck = this._lastDeck.asReadonly();

  isGenerating(course: string): boolean {
    return this._jobs().has(course);
  }

  start(course: string, count: CardCount): void {
    if (this.isGenerating(course)) {
      return;
    }
    this.setJob(course, Date.now());
    this.toasts.show(
      'info',
      `Génération de ${count} flashcards lancée pour « ${course} »`,
      `Environ ${FLASHCARD_MINUTES[count]} min. Tu peux continuer à utiliser le tuteur.`,
    );

    this.api
      .generate(course, count)
      .pipe(finalize(() => this.setJob(course, null)))
      .subscribe({
        next: (deck) => {
          this._lastDeck.set(deck);
          const received = deck.cards.length;
          const cards = `${received} carte${received > 1 ? 's' : ''}`;
          const where = 'Ouvre l’onglet Flashcards pour réviser (paquet enregistré dans « Mes paquets »).';
          if (received < count) {
            this.toasts.show(
              'warning',
              `Flashcards « ${course} » prêtes : ${cards} au lieu de ${count}`,
              `Le cours est trop court pour en générer davantage. ${where}`,
            );
          } else {
            this.toasts.show('success', `Flashcards « ${course} » prêtes : ${cards}`, where);
          }
        },
        error: (err: unknown) => {
          this.toasts.show('error', `Échec des flashcards « ${course} »`, toMessage(err));
        },
      });
  }

  private setJob(course: string, startedAt: number | null): void {
    this._jobs.update((jobs) => {
      const next = new Map(jobs);
      if (startedAt === null) {
        next.delete(course);
      } else {
        next.set(course, startedAt);
      }
      return next;
    });
    this.syncTicker();
  }

  /** Le chronomètre ne tourne que s'il y a au moins une génération. */
  private syncTicker(): void {
    if (this.hasJobs() && this.ticker === undefined) {
      this._now.set(Date.now());
      this.ticker = setInterval(() => this._now.set(Date.now()), 1000);
    } else if (!this.hasJobs() && this.ticker !== undefined) {
      clearInterval(this.ticker);
      this.ticker = undefined;
    }
  }
}
