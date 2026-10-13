import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import {
  CARD_COUNTS,
  CardCount,
  DEFAULT_CARD_COUNT,
  FLASHCARD_MINUTES,
  Flashcard,
} from '../../core/models/flashcard.models';
import { FlashcardJobsService } from '../../core/services/flashcard-jobs.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { formatElapsed } from '../../core/utils/exam.utils';
import { CourseSelector } from '../../shared/components/course-selector/course-selector';
import { ToastService } from '../../shared/components/toast/toast.service';
import { handleRadioKeydown } from '../../shared/utils/radio-group';
import { FlashcardReview } from './components/flashcard-review/flashcard-review';

@Component({
  selector: 'app-flashcards-page',
  imports: [CourseSelector, FlashcardReview, RouterLink],
  templateUrl: './flashcards.page.html',
  styleUrl: './flashcards.page.css',
})
export class FlashcardsPage {
  private readonly api = inject(TutorApiService);
  private readonly toasts = inject(ToastService);
  protected readonly jobs = inject(FlashcardJobsService);

  protected readonly counts = CARD_COUNTS;
  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly count = signal<CardCount>(DEFAULT_CARD_COUNT);
  /** Cartes en cours de révision (instantané : une régénération ne coupe pas la révision). */
  protected readonly reviewCards = signal<readonly Flashcard[] | null>(null);

  protected readonly deck = computed(() => {
    const course = this.selectedCourse();
    return course === null ? null : this.jobs.deck(course);
  });
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
  protected readonly deckDate = computed(() => {
    const createdAt = this.deck()?.createdAt;
    return createdAt
      ? new Date(createdAt).toLocaleString('fr-FR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
      : null;
  });

  protected readonly setCount = (value: CardCount): void => this.count.set(value);
  protected readonly onRadioKeydown = handleRadioKeydown;

  constructor() {
    this.loadCourses();
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
    this.reviewCards.set(null);
  }

  protected generate(): void {
    const course = this.selectedCourse();
    if (course !== null) {
      this.jobs.start(course, this.count());
    }
  }

  protected startReview(): void {
    this.reviewCards.set(this.deck()?.cards ?? null);
  }

  protected stopReview(): void {
    this.reviewCards.set(null);
  }

  private loadCourses(): void {
    this.coursesLoading.set(true);
    this.api
      .getCourses()
      .pipe(finalize(() => this.coursesLoading.set(false)))
      .subscribe({
        next: (courses) => {
          this.courses.set(courses);
          const selected = this.selectedCourse();
          if (selected === null || !courses.includes(selected)) {
            this.selectedCourse.set(courses[0] ?? null);
          }
        },
        error: (err: unknown) => this.toasts.show('error', 'Impossible de charger les cours', toMessage(err)),
      });
  }
}
