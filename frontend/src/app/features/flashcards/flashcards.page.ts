import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import {
  CARD_COUNTS,
  CardCount,
  DEFAULT_CARD_COUNT,
  DeckSummary,
  FLASHCARD_MINUTES,
  Flashcard,
  FlashcardDeck,
} from '../../core/models/flashcard.models';
import { FlashcardJobsService } from '../../core/services/flashcard-jobs.service';
import { FlashcardsApiService } from '../../core/services/flashcards-api.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { formatElapsed } from '../../core/utils/exam.utils';
import { CourseSelector } from '../../shared/components/course-selector/course-selector';
import { Loader } from '../../shared/components/loader/loader';
import { ToastService } from '../../shared/components/toast/toast.service';
import { handleRadioKeydown } from '../../shared/utils/radio-group';
import { FlashcardReview } from './components/flashcard-review/flashcard-review';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
});

@Component({
  selector: 'app-flashcards-page',
  imports: [CourseSelector, FlashcardReview, Loader, RouterLink],
  templateUrl: './flashcards.page.html',
  styleUrl: './flashcards.page.css',
})
export class FlashcardsPage {
  private readonly api = inject(TutorApiService);
  private readonly flashcards = inject(FlashcardsApiService);
  private readonly toasts = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  protected readonly jobs = inject(FlashcardJobsService);
  /** Une seule alerte si l'enregistrement des révisions échoue pendant la session. */
  private reviewErrorShown = false;

  protected readonly counts = CARD_COUNTS;
  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly count = signal<CardCount>(DEFAULT_CARD_COUNT);
  /** « Mes paquets » du cours sélectionné, le plus récent en premier. */
  protected readonly decks = signal<DeckSummary[]>([]);
  protected readonly decksLoading = signal(false);
  /** Paquet en cours d'ouverture (chargement des cartes). */
  protected readonly opening = signal<number | null>(null);
  /** Paquet en cours de révision (instantané : une régénération ne coupe pas la révision). */
  protected readonly reviewDeck = signal<FlashcardDeck | null>(null);
  protected readonly reviewCards = computed<readonly Flashcard[] | null>(() => this.reviewDeck()?.cards ?? null);

  protected readonly generating = computed(() => {
    const course = this.selectedCourse();
    return course !== null && this.jobs.jobs().has(course);
  });
  protected readonly elapsed = computed(() => {
    const course = this.selectedCourse();
    const startedAt = course === null ? undefined : this.jobs.jobs().get(course);
    return startedAt === undefined ? '' : formatElapsed((this.jobs.now() - startedAt) / 1000);
  });
  protected readonly minutes = computed(() => FLASHCARD_MINUTES[this.count()]);

  protected readonly setCount = (value: CardCount): void => this.count.set(value);
  protected readonly onRadioKeydown = handleRadioKeydown;

  constructor() {
    this.loadCourses();
    // Un paquet vient d'être généré pour le cours affiché : il apparaît dans « Mes paquets ».
    effect(() => {
      const deck = this.jobs.lastDeck();
      if (deck && deck.course === untracked(this.selectedCourse)) {
        untracked(() => this.loadDecks(deck.course));
      }
    });
  }

  protected deckDate(deck: DeckSummary): string {
    return DATE_FORMAT.format(new Date(deck.created_at));
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
    this.reviewDeck.set(null);
    this.loadDecks(course);
  }

  protected generate(): void {
    const course = this.selectedCourse();
    if (course !== null) {
      this.jobs.start(course, this.count());
    }
  }

  protected startReview(deck: DeckSummary): void {
    this.opening.set(deck.id);
    this.flashcards
      .getDeck(deck.id)
      .pipe(finalize(() => this.opening.set(null)))
      .subscribe({
        next: (full) => this.reviewDeck.set(full),
        error: (err: unknown) => this.toasts.show('error', 'Impossible d’ouvrir le paquet', toMessage(err)),
      });
  }

  protected stopReview(): void {
    this.reviewDeck.set(null);
  }

  /** Chaque « Je savais » / « À revoir » est enregistré pour le profil (points faibles, statistiques). */
  protected onAnswered(event: { card: Flashcard; known: boolean }): void {
    const deck = this.reviewDeck();
    if (!deck) {
      return;
    }
    this.flashcards.review(deck.id, event.card.concept, event.known).subscribe({
      error: (err: unknown) => {
        if (!this.reviewErrorShown) {
          this.reviewErrorShown = true;
          this.toasts.show('warning', 'Révision non enregistrée', toMessage(err));
        }
      },
    });
  }

  protected deleteDeck(deck: DeckSummary): void {
    const ok = confirm(
      `Supprimer le paquet du ${this.deckDate(deck)} (${deck.card_count} cartes) ?\n` +
        'Tes révisions passées restent dans ton profil.',
    );
    if (!ok) {
      return;
    }
    this.flashcards.deleteDeck(deck.id).subscribe({
      next: () => this.decks.update((list) => list.filter((d) => d.id !== deck.id)),
      error: (err: unknown) => this.toasts.show('error', 'Suppression impossible', toMessage(err)),
    });
  }

  private loadCourses(): void {
    this.coursesLoading.set(true);
    this.api
      .getCourses()
      .pipe(finalize(() => this.coursesLoading.set(false)))
      .subscribe({
        next: (courses) => {
          this.courses.set(courses);
          // « Réviser » depuis le profil : /flashcards?course=…
          const wanted = this.route.snapshot.queryParamMap.get('course') ?? this.selectedCourse();
          const course = wanted !== null && courses.includes(wanted) ? wanted : (courses[0] ?? null);
          this.selectedCourse.set(course);
          this.loadDecks(course);
        },
        error: (err: unknown) => this.toasts.show('error', 'Impossible de charger les cours', toMessage(err)),
      });
  }

  private loadDecks(course: string | null): void {
    this.decks.set([]);
    if (course === null) {
      return;
    }
    this.decksLoading.set(true);
    this.flashcards
      .listDecks(course)
      .pipe(finalize(() => this.decksLoading.set(false)))
      .subscribe({
        next: (decks) => {
          if (this.selectedCourse() === course) {
            this.decks.set(decks);
          }
        },
        error: (err: unknown) => this.toasts.show('error', 'Impossible de charger tes paquets', toMessage(err)),
      });
  }
}
