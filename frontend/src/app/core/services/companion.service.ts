import { Injectable, computed, inject, signal } from '@angular/core';
import {
  EMPTY,
  Observable,
  catchError,
  expand,
  filter,
  finalize,
  map,
  switchMap,
  take,
  tap,
  throwError,
  throwIfEmpty,
  timer,
} from 'rxjs';
import {
  CompanionJob,
  CompanionProgress,
  CompanionStreamEvent,
  Letter,
  QuizResultResponse,
} from '../models/companion.models';
import { CompanionApiService } from './companion-api.service';
import { ConversationsService, SavedExchange } from './conversations.service';

/** Intervalle de consultation d'une tâche de fond (quiz, flashcards, résumé : 1 à 3 minutes). */
export const POLL_MS = 2000;

/** Erreur renvoyée par l'assistant lui-même (événement « error ») : jamais de nouvel essai. */
class AssistantError extends Error {}

/**
 * Study Companion : envoie les demandes à l'agent dans les conversations existantes (ConversationsService)
 * et suit les tâches longues jusqu'à leur fin, même si l'on change de page.
 */
@Injectable({ providedIn: 'root' })
export class CompanionService {
  private readonly api = inject(CompanionApiService);
  private readonly conversations = inject(ConversationsService);
  private ticker: ReturnType<typeof setInterval> | undefined;

  private readonly _progress = signal<ReadonlyMap<number, CompanionProgress>>(new Map());
  private readonly _now = signal(Date.now());

  /** Message en attente (id négatif) → outil en cours et heure de début. */
  readonly progress = this._progress.asReadonly();
  /** Heure courante, rafraîchie chaque seconde tant qu'une demande est en cours (chronomètre). */
  readonly now = this._now.asReadonly();
  readonly busy = computed(() => this._progress().size > 0);

  send(message: string, course: string | null): Observable<void> {
    return this.conversations.send(message, course, (conversationId, pendingId) =>
      this.run(conversationId, pendingId, course, message),
    );
  }

  saveQuizResult(messageId: number, answers: readonly Letter[]): Observable<QuizResultResponse> {
    return this.api
      .saveQuizResult(messageId, answers)
      .pipe(tap((res) => this.conversations.updateResponse(messageId, res.message.payload)));
  }

  /**
   * Flux SSE : outil en cours et réponse du tuteur affichés au fur et à mesure, puis la réponse finale validée.
   * Si le flux est coupé après son début, la tâche continue côté serveur : on la consulte jusqu'à sa fin.
   */
  private run(conversationId: number, pendingId: number, course: string | null, message: string): Observable<SavedExchange> {
    this.setProgress(pendingId, { tool: null, startedAt: Date.now() });
    let jobId: string | null = null;
    return this.api.stream(conversationId, course, message).pipe(
      tap((event) => {
        if (event.event === 'start') {
          jobId = event.data.job_id;
        }
        this.onStreamEvent(pendingId, event);
      }),
      filter((event) => event.event === 'final' || event.event === 'error'),
      take(1),
      throwIfEmpty(() => new Error('Flux interrompu.')),
      map((event) => {
        if (event.event === 'error') {
          throw new AssistantError(event.data.detail);
        }
        return this.toExchange(event.data as CompanionJob);
      }),
      catchError((err: unknown) =>
        jobId !== null && !(err instanceof AssistantError) ? this.poll(jobId, pendingId) : throwError(() => err),
      ),
      finalize(() => this.setProgress(pendingId, null)),
    );
  }

  /** Consultation de la tâche jusqu'à sa fin (flux coupé). */
  private poll(jobId: string, pendingId: number): Observable<SavedExchange> {
    return this.api.job(jobId).pipe(
      expand((job) => (job.status === 'running' ? timer(POLL_MS).pipe(switchMap(() => this.api.job(jobId))) : EMPTY)),
      tap((job) => this.patchProgress(pendingId, { tool: job.tool })),
      filter((job) => job.status !== 'running'),
      take(1),
      map((job) => this.toExchange(job)),
    );
  }

  private toExchange(job: CompanionJob): SavedExchange {
    if (job.status === 'error' || job.exchange === null) {
      throw new AssistantError(job.error ?? "L'assistant n'a pas pu répondre. Réessaie.");
    }
    return {
      conversation: job.exchange.conversation,
      messages: [job.exchange.user_message, ...job.exchange.assistant_messages],
    };
  }

  private onStreamEvent(pendingId: number, event: CompanionStreamEvent): void {
    if (event.event === 'tool') {
      this.patchProgress(pendingId, { tool: event.data.tool });
    } else if (event.event === 'token') {
      const draft = (this._progress().get(pendingId)?.draft ?? '') + event.data.text;
      this.patchProgress(pendingId, { draft });
    }
  }

  private patchProgress(pendingId: number, patch: Partial<CompanionProgress>): void {
    const current = this._progress().get(pendingId);
    if (current && Object.entries(patch).some(([key, value]) => current[key as keyof CompanionProgress] !== value)) {
      this.setProgress(pendingId, { ...current, ...patch });
    }
  }

  private setProgress(pendingId: number, progress: CompanionProgress | null): void {
    this._progress.update((map) => {
      const next = new Map(map);
      if (progress === null) {
        next.delete(pendingId);
      } else {
        next.set(pendingId, progress);
      }
      return next;
    });
    if (this.busy() && this.ticker === undefined) {
      this._now.set(Date.now());
      this.ticker = setInterval(() => this._now.set(Date.now()), 1000);
    } else if (!this.busy() && this.ticker !== undefined) {
      clearInterval(this.ticker);
      this.ticker = undefined;
    }
  }
}
