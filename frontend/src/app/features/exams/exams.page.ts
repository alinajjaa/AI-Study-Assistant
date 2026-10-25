import { Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { toMessage } from '../../core/interceptors/error.interceptor';
import { ExamRecord, difficultyLabel, examFormatLabel } from '../../core/models/exam.models';
import { ExamApiService } from '../../core/services/exam-api.service';
import { ExamJobsService } from '../../core/services/exam-jobs.service';
import { COMPLETE_EXAM_MINUTES, downloadBlob, filenameFromContentDisposition } from '../../core/utils/exam.utils';
import { ConfirmService } from '../../shared/components/confirm-dialog/confirm.service';
import { EmptyState } from '../../shared/components/empty-state/empty-state';
import { ErrorState } from '../../shared/components/error-state/error-state';
import { Loader } from '../../shared/components/loader/loader';
import { Skeleton } from '../../shared/components/skeleton/skeleton';
import { StepProgress } from '../../shared/components/step-progress/step-progress';
import { ToastService } from '../../shared/components/toast/toast.service';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** « Mes examens » : historique des examens générés, à retélécharger ou supprimer. */
@Component({
  selector: 'app-exams-page',
  imports: [Loader, RouterLink, EmptyState, ErrorState, Skeleton, StepProgress],
  templateUrl: './exams.page.html',
  styleUrl: './exams.page.css',
})
export class ExamsPage {
  private readonly api = inject(ExamApiService);
  private readonly toasts = inject(ToastService);
  private readonly confirm = inject(ConfirmService);
  protected readonly jobs = inject(ExamJobsService);

  protected readonly exams = signal<ExamRecord[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  /** Examens en cours de téléchargement ou de suppression. */
  protected readonly busy = signal<ReadonlySet<number>>(new Set());

  protected readonly formatLabel = examFormatLabel;
  /** Examens en préparation (indicateur de progression par étapes). */
  protected readonly running = computed(() => [...this.jobs.jobs()].map(([course, startedAt]) => ({ course, startedAt })));
  protected readonly examSteps: readonly string[] = ['Lecture du cours', 'QCM', 'Vrai / Faux', 'Questions rédigées', 'Mise en page du PDF'];
  protected readonly examEstimateS = COMPLETE_EXAM_MINUTES * 60;
  protected readonly difficultyLabel = difficultyLabel;

  constructor() {
    // Chargement initial, puis à chaque examen terminé pendant que la page est ouverte.
    effect(() => {
      this.jobs.completed();
      untracked(() => this.load());
    });
  }

  /** « Réessayer » après une erreur de chargement. */
  protected reload(): void {
    this.load();
  }

  protected date(exam: ExamRecord): string {
    return DATE_FORMAT.format(new Date(exam.created_at));
  }

  protected isBusy(id: number): boolean {
    return this.busy().has(id);
  }

  protected download(exam: ExamRecord): void {
    this.setBusy(exam.id, true);
    this.api
      .downloadExam(exam.id)
      .pipe(finalize(() => this.setBusy(exam.id, false)))
      .subscribe({
        next: (res) => {
          if (res.body) {
            downloadBlob(res.body, filenameFromContentDisposition(res.headers.get('Content-Disposition'), exam.course));
          }
        },
        error: (err: unknown) => this.toasts.show('error', 'Téléchargement impossible', toMessage(err)),
      });
  }

  protected remove(exam: ExamRecord): void {
    this.confirm
      .ask({
        title: `Supprimer l'examen « ${exam.course} » du ${this.date(exam)} ?`,
        message: 'Le PDF sera définitivement effacé.',
        confirmLabel: "Supprimer l'examen",
        danger: true,
      })
      .subscribe((ok) => {
        if (ok) {
          this.deleteExam(exam);
        }
      });
  }

  private deleteExam(exam: ExamRecord): void {
    this.setBusy(exam.id, true);
    this.api
      .deleteExam(exam.id)
      .pipe(finalize(() => this.setBusy(exam.id, false)))
      .subscribe({
        next: () => {
          this.exams.update((list) => list.filter((e) => e.id !== exam.id));
          this.toasts.show('success', 'Examen supprimé');
        },
        error: (err: unknown) => this.toasts.show('error', 'Suppression impossible', toMessage(err)),
      });
  }

  private load(): void {
    this.loading.set(true);
    this.api
      .listExams()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (exams) => {
          this.exams.set(exams);
          this.error.set(null);
        },
        error: (err: unknown) => this.error.set(toMessage(err)),
      });
  }

  private setBusy(id: number, busy: boolean): void {
    this.busy.update((set) => {
      const next = new Set(set);
      if (busy) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  }
}
