import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { ExamOptions } from '../../core/models/exam.models';
import { UploadResponse } from '../../core/models/tutor.models';
import { ConversationsService } from '../../core/services/conversations.service';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { FlashcardJobsService } from '../../core/services/flashcard-jobs.service';
import { SummaryJobsService } from '../../core/services/summary-jobs.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { formatElapsed } from '../../core/utils/exam.utils';
import { ConfirmService } from '../../shared/components/confirm-dialog/confirm.service';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ErrorState } from '../../shared/components/error-state/error-state';
import { Icon } from '../../shared/components/icon/icon';
import { Skeleton } from '../../shared/components/skeleton/skeleton';
import { ToastService } from '../../shared/components/toast/toast.service';
import { courseInitial, courseTint } from '../../shared/utils/course-avatar';
import { ExamDialog } from '../companion/components/exam-dialog/exam-dialog';
import { UploadPanel } from '../companion/components/upload-panel/upload-panel';

/**
 * Mes cours : un cours par carte (Discuter, Examen, Flashcards, Résumé, Supprimer) et l'import d'un PDF
 * (bouton ou glisser-déposer sur la page). Mêmes services que l'Assistant.
 */
@Component({
  selector: 'app-courses-page',
  imports: [RouterLink, UploadPanel, ExamDialog, EmptyState, ErrorState, Icon, Skeleton],
  templateUrl: './courses.page.html',
  styleUrl: './courses.page.css',
})
export class CoursesPage {
  private readonly api = inject(TutorApiService);
  private readonly confirm = inject(ConfirmService);
  private readonly toasts = inject(ToastService);
  private readonly conversations = inject(ConversationsService);
  protected readonly examJobs = inject(ExamJobsService);
  private readonly flashcardJobs = inject(FlashcardJobsService);
  private readonly summaryJobs = inject(SummaryJobsService);

  protected readonly courses = signal<string[]>([]);
  protected readonly loading = signal(false);
  protected readonly deleting = signal<string | null>(null);
  protected readonly error = signal<string | null>(null);
  /** Cours pour lequel la modale d'examen est ouverte (null = fermée). */
  protected readonly examCourse = signal<string | null>(null);
  protected readonly initial = courseInitial;
  protected readonly tint = courseTint;

  /** Générations en arrière-plan par cours (examen, flashcards, résumé) : statut et chronomètre des cartes. */
  private readonly backgroundJobs = computed(() => {
    const byCourse = new Map<string, { startedAt: number; kinds: string[] }>();
    const add = (course: string, startedAt: number, kind: string) => {
      const job = byCourse.get(course);
      if (job === undefined) {
        byCourse.set(course, { startedAt, kinds: [kind] });
      } else if (!job.kinds.includes(kind)) {
        job.startedAt = Math.min(job.startedAt, startedAt);
        job.kinds.push(kind);
      }
    };
    for (const [course, startedAt] of this.examJobs.jobs()) {
      add(course, startedAt, 'Examen');
    }
    for (const [course, startedAt] of this.flashcardJobs.jobs()) {
      add(course, startedAt, 'Flashcards');
    }
    for (const [key, startedAt] of this.summaryJobs.jobs()) {
      add(key.slice(key.indexOf(':') + 1), startedAt, 'Résumé');
    }
    return byCourse;
  });
  private readonly now = computed(() => Math.max(this.examJobs.now(), this.flashcardJobs.now(), this.summaryJobs.now()));

  constructor() {
    this.loadCourses();
  }

  /** « Examen + Flashcards en cours… 1:23 » si une génération est en cours pour ce cours, sinon null. */
  protected job(course: string): { label: string; time: string } | null {
    const job = this.backgroundJobs().get(course);
    if (job === undefined) {
      return null;
    }
    return { label: `${job.kinds.join(' + ')} en cours…`, time: formatElapsed((this.now() - job.startedAt) / 1000) };
  }

  protected examRunning(course: string): boolean {
    return this.examJobs.isGenerating(course);
  }

  /** « Discuter » : nouvelle conversation dans l'Assistant, sur ce cours (/companion?course=…). */
  protected discuss(): void {
    this.conversations.startNew();
  }

  protected openExam(course: string): void {
    if (!this.examRunning(course)) {
      this.examCourse.set(course);
    }
  }

  /** La modale se ferme aussitôt ; la génération continue en arrière-plan (PDF téléchargé à la fin). */
  protected onGenerateExam(options: ExamOptions): void {
    const course = this.examCourse();
    this.examCourse.set(null);
    if (course !== null) {
      this.examJobs.start(course, options);
    }
  }

  protected onExamDialogClosed(): void {
    this.examCourse.set(null);
  }

  protected onUploaded(res: UploadResponse): void {
    this.toasts.show('success', 'Cours importé', `« ${res.course} » est prêt.`);
    this.loadCourses();
  }

  protected onDelete(course: string): void {
    this.confirm
      .ask({
        title: `Supprimer le cours « ${course} » ?`,
        message: 'Tous ses extraits indexés seront définitivement effacés.',
        confirmLabel: 'Supprimer le cours',
        danger: true,
      })
      .subscribe((ok) => {
        if (ok) {
          this.deleteCourse(course);
        }
      });
  }

  private deleteCourse(course: string): void {
    this.deleting.set(course);
    this.api
      .deleteCourse(course)
      .pipe(finalize(() => this.deleting.set(null)))
      .subscribe({
        next: () => {
          this.loadCourses();
          this.toasts.show('success', 'Cours supprimé', `« ${course} » et ses extraits ont été effacés.`);
        },
        error: (err: unknown) => this.toasts.show('error', 'Suppression impossible', toMessage(err)),
      });
  }

  protected loadCourses(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api
      .getCourses()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (courses) => this.courses.set(courses),
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }
}
