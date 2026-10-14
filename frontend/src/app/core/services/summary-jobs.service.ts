import { Injectable, computed, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';
import { ToastService } from '../../shared/components/toast/toast.service';
import { toMessage } from '../interceptors/error.interceptor';
import { SUMMARY_MINUTES, Summary, SummaryRequest } from '../models/summary.models';
import { SummariesApiService } from './summaries-api.service';

/** Clé d'une génération : un résumé du cours entier et un thème peuvent tourner en même temps. */
export function summaryJobKey(course: string, mode: SummaryRequest['mode']): string {
  return `${mode}:${course}`;
}

/**
 * Résumés générés en arrière-plan, comme les examens : ils continuent si l'on change de page,
 * et une notification annonce la fin.
 */
@Injectable({ providedIn: 'root' })
export class SummaryJobsService {
  private readonly api = inject(SummariesApiService);
  private readonly toasts = inject(ToastService);
  private ticker: ReturnType<typeof setInterval> | undefined;

  private readonly _jobs = signal<ReadonlyMap<string, number>>(new Map());
  private readonly _now = signal(Date.now());
  private readonly _lastSummary = signal<Summary | null>(null);

  /** summaryJobKey → heure de début (ms). */
  readonly jobs = this._jobs.asReadonly();
  readonly now = this._now.asReadonly();
  readonly hasJobs = computed(() => this._jobs().size > 0);
  /** Dernier résumé reçu : la page Résumés l'affiche s'il concerne le cours ouvert. */
  readonly lastSummary = this._lastSummary.asReadonly();

  isRunning(course: string, mode: SummaryRequest['mode']): boolean {
    return this._jobs().has(summaryJobKey(course, mode));
  }

  start(course: string, request: SummaryRequest): void {
    const key = summaryJobKey(course, request.mode);
    if (this._jobs().has(key)) {
      return;
    }
    this.setJob(key, Date.now());
    const what = request.mode === 'course' ? `Résumé du cours « ${course} »` : `Explication « ${request.topic} »`;

    this.api
      .create(course, request)
      .pipe(finalize(() => this.setJob(key, null)))
      .subscribe({
        next: (summary) => {
          this._lastSummary.set(summary);
          if (summary.cached) {
            return; // résumé déjà enregistré : affiché tout de suite, pas de notification
          }
          if (!summary.content.found) {
            this.toasts.show('warning', `${what} : thème absent du cours`, summary.content.overview);
          } else {
            const n = summary.content.sections.length;
            this.toasts.show('success', `${what} prêt`, `${n} section${n > 1 ? 's' : ''}. Ouvre l’onglet Résumés.`);
          }
        },
        error: (err: unknown) => this.toasts.show('error', `Échec : ${what}`, toMessage(err)),
      });

    // Un résumé déjà en cache revient en une fraction de seconde : on n'annonce la génération qu'ensuite
    setTimeout(() => {
      if (this._jobs().has(key)) {
        this.toasts.show(
          'info',
          `${what} en cours`,
          `Environ ${SUMMARY_MINUTES[request.mode]} min. Tu peux continuer à utiliser l’application.`,
        );
      }
    }, 800);
  }

  private setJob(key: string, startedAt: number | null): void {
    this._jobs.update((jobs) => {
      const next = new Map(jobs);
      if (startedAt === null) {
        next.delete(key);
      } else {
        next.set(key, startedAt);
      }
      return next;
    });
    if (this.hasJobs() && this.ticker === undefined) {
      this._now.set(Date.now());
      this.ticker = setInterval(() => this._now.set(Date.now()), 1000);
    } else if (!this.hasJobs() && this.ticker !== undefined) {
      clearInterval(this.ticker);
      this.ticker = undefined;
    }
  }
}
