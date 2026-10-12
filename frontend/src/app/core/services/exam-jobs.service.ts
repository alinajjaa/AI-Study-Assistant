import { Injectable, computed, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { ToastService } from '../../shared/components/toast/toast.service';
import { toMessage } from '../interceptors/error.interceptor';
import { COMPLETE_EXAM_PARTS, ExamOptions } from '../models/exam.models';
import {
  describeExam,
  downloadBlob,
  estimateExamMinutes,
  filenameFromContentDisposition,
  summarizeExamResult,
} from '../utils/exam.utils';
import { ExamApiService } from './exam-api.service';

const COMPLETE_QUESTION_COUNT = COMPLETE_EXAM_PARTS.reduce((sum, part) => sum + part.count, 0);

function readNumber(value: string | null): number | null {
  const parsed = value === null ? Number.NaN : Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function readInt(value: string | null): number | null {
  const parsed = readNumber(value);
  return parsed === null ? null : Math.round(parsed);
}

/**
 * Générations d'examen en cours, indépendantes des composants :
 * elles continuent si l'on change de cours ou de page.
 */
@Injectable({ providedIn: 'root' })
export class ExamJobsService {
  private readonly api = inject(ExamApiService);
  private readonly toasts = inject(ToastService);
  private ticker: ReturnType<typeof setInterval> | undefined;

  private readonly _jobs = signal<ReadonlyMap<string, number>>(new Map());
  private readonly _now = signal(Date.now());

  /** Cours → heure de début (ms). */
  readonly jobs = this._jobs.asReadonly();
  /** Heure courante, rafraîchie chaque seconde tant qu'une génération tourne. */
  readonly now = this._now.asReadonly();
  readonly hasJobs = computed(() => this._jobs().size > 0);

  isGenerating(course: string): boolean {
    return this._jobs().has(course);
  }

  start(course: string, options: ExamOptions): void {
    if (this.isGenerating(course)) {
      return;
    }
    this.setJob(course, Date.now());
    this.toasts.show(
      'info',
      `${describeExam(options)} lancé pour « ${course} »`,
      `Environ ${estimateExamMinutes(options)} min. Tu peux continuer à utiliser le tuteur.`,
    );

    this.api
      .generateExam(course, options)
      .pipe(finalize(() => this.setJob(course, null)))
      .subscribe({
        next: (res) => {
          const blob = res.body;
          if (!blob) {
            this.toasts.show('error', `Échec de l'examen « ${course} »`, 'Le PDF reçu est vide.');
            return;
          }
          const filename = filenameFromContentDisposition(res.headers.get('Content-Disposition'), course);
          downloadBlob(blob, filename);

          const expected =
            readInt(res.headers.get('X-Questions-Expected')) ??
            (options.format === 'complet' ? COMPLETE_QUESTION_COUNT : options.numQuestions);
          const generated = readInt(res.headers.get('X-Questions-Generated')) ?? expected;
          const total = readNumber(res.headers.get('X-Exam-Total'));
          const summary = summarizeExamResult(generated, expected, total);
          this.toasts.show(summary.kind, summary.title, summary.message);
        },
        error: (err: unknown) => {
          this.toasts.show('error', `Échec de l'examen « ${course} »`, toMessage(err));
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
