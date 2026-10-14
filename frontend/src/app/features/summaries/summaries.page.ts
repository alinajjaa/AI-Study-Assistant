import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { Summary, SummaryListItem, SummaryMode } from '../../core/models/summary.models';
import { SummariesApiService } from '../../core/services/summaries-api.service';
import { SummaryJobsService, summaryJobKey } from '../../core/services/summary-jobs.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { formatElapsed } from '../../core/utils/exam.utils';
import { CourseSelector } from '../../shared/components/course-selector/course-selector';
import { Loader } from '../../shared/components/loader/loader';
import { ToastService } from '../../shared/components/toast/toast.service';
import { SummaryView } from './components/summary-view/summary-view';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

/** « Résumés » : résumé du cours entier (lit tout le cours) ou explication d'un thème. */
@Component({
  selector: 'app-summaries-page',
  imports: [CourseSelector, Loader, RouterLink, SummaryView],
  templateUrl: './summaries.page.html',
  styleUrl: './summaries.page.css',
})
export class SummariesPage {
  private readonly courseApi = inject(TutorApiService);
  private readonly api = inject(SummariesApiService);
  private readonly toasts = inject(ToastService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  protected readonly jobs = inject(SummaryJobsService);

  protected readonly courses = signal<string[]>([]);
  protected readonly coursesLoading = signal(false);
  protected readonly selectedCourse = signal<string | null>(null);
  protected readonly topic = signal('');
  /** « Mes résumés » du cours sélectionné. */
  protected readonly summaries = signal<SummaryListItem[]>([]);
  protected readonly listLoading = signal(false);
  /** Résumé affiché. */
  protected readonly current = signal<Summary | null>(null);
  protected readonly opening = signal<number | null>(null);

  /** Générations en cours affichées dans la liste des cours (badge + chronomètre), par cours. */
  protected readonly courseJobs = computed(() => {
    const byCourse = new Map<string, number>();
    for (const [key, startedAt] of this.jobs.jobs()) {
      byCourse.set(key.slice(key.indexOf(':') + 1), startedAt);
    }
    return byCourse;
  });
  protected readonly courseRunning = computed(() => this.running('course'));
  protected readonly topicRunning = computed(() => this.running('topic'));
  protected readonly elapsed = computed(() => {
    const course = this.selectedCourse();
    const startedAt = course === null ? undefined : this.courseJobs().get(course);
    return startedAt === undefined ? '' : formatElapsed((this.jobs.now() - startedAt) / 1000);
  });
  protected readonly canExplain = computed(() => this.topic().trim().length >= 2 && !this.topicRunning());

  constructor() {
    this.loadCourses();
    // Un résumé vient d'arriver pour le cours affiché : on l'ouvre et on met la liste à jour.
    effect(() => {
      const summary = this.jobs.lastSummary();
      if (summary && summary.course === untracked(this.selectedCourse)) {
        untracked(() => {
          this.current.set(summary);
          if (summary.mode === 'topic') {
            this.topic.set('');
          }
          this.loadSummaries(summary.course);
        });
      }
    });
  }

  protected itemLabel(item: SummaryListItem): string {
    return item.mode === 'course' ? 'Cours entier' : `« ${item.topic} »`;
  }

  protected itemDate(item: SummaryListItem): string {
    return DATE_FORMAT.format(new Date(item.created_at));
  }

  protected onSelectCourse(course: string | null): void {
    this.selectedCourse.set(course);
    this.current.set(null);
    this.loadSummaries(course);
  }

  protected onTopicInput(event: Event): void {
    this.topic.set((event.target as HTMLInputElement).value);
  }

  protected summarizeCourse(regenerate = false): void {
    const course = this.selectedCourse();
    if (course !== null) {
      this.jobs.start(course, { mode: 'course', regenerate });
    }
  }

  protected explain(event?: Event): void {
    event?.preventDefault();
    const course = this.selectedCourse();
    if (course !== null && this.canExplain()) {
      this.jobs.start(course, { mode: 'topic', topic: this.topic().trim() });
    }
  }

  /** « Régénérer » : le cours entier sans le cache, ou le même thème une nouvelle fois. */
  protected onRegenerate(summary: Summary): void {
    if (summary.mode === 'course') {
      this.jobs.start(summary.course, { mode: 'course', regenerate: true });
    } else if (summary.topic) {
      this.jobs.start(summary.course, { mode: 'topic', topic: summary.topic });
    }
  }

  protected isRegenerating(summary: Summary): boolean {
    return this.jobs.isRunning(summary.course, summary.mode);
  }

  protected open(item: SummaryListItem): void {
    this.opening.set(item.id);
    this.api
      .get(item.id)
      .pipe(finalize(() => this.opening.set(null)))
      .subscribe({
        next: (summary) => this.current.set(summary),
        error: (err: unknown) => this.toasts.show('error', 'Impossible d’ouvrir le résumé', toMessage(err)),
      });
  }

  protected remove(item: SummaryListItem): void {
    if (!confirm(`Supprimer le résumé ${this.itemLabel(item)} du ${this.itemDate(item)} ?`)) {
      return;
    }
    this.api.remove(item.id).subscribe({
      next: () => {
        this.summaries.update((list) => list.filter((s) => s.id !== item.id));
        if (this.current()?.id === item.id) {
          this.current.set(null);
        }
      },
      error: (err: unknown) => this.toasts.show('error', 'Suppression impossible', toMessage(err)),
    });
  }

  private running(mode: SummaryMode): boolean {
    const course = this.selectedCourse();
    return course !== null && this.jobs.jobs().has(summaryJobKey(course, mode));
  }

  private loadCourses(): void {
    this.coursesLoading.set(true);
    this.courseApi
      .getCourses()
      .pipe(finalize(() => this.coursesLoading.set(false)))
      .subscribe({
        next: (courses) => {
          this.courses.set(courses);
          // Depuis le tuteur : /summaries?course=…&auto=course lance le résumé du cours entier
          const params = this.route.snapshot.queryParamMap;
          const wanted = params.get('course') ?? this.selectedCourse();
          const course = wanted !== null && courses.includes(wanted) ? wanted : (courses[0] ?? null);
          this.selectedCourse.set(course);
          this.loadSummaries(course);
          if (params.get('auto') === 'course' && course !== null && course === wanted) {
            this.summarizeCourse();
            void this.router.navigate([], { queryParams: { course }, replaceUrl: true });
          }
        },
        error: (err: unknown) => this.toasts.show('error', 'Impossible de charger les cours', toMessage(err)),
      });
  }

  private loadSummaries(course: string | null): void {
    this.summaries.set([]);
    if (course === null) {
      return;
    }
    this.listLoading.set(true);
    this.api
      .list(course)
      .pipe(finalize(() => this.listLoading.set(false)))
      .subscribe({
        next: (list) => {
          if (this.selectedCourse() === course) {
            this.summaries.set(list);
          }
        },
        error: (err: unknown) => this.toasts.show('error', 'Impossible de charger tes résumés', toMessage(err)),
      });
  }
}
