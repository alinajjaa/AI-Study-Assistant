import { Injectable, computed, inject, signal } from '@angular/core';
import { EMPTY, Observable, expand, filter, finalize, map, switchMap, take, tap, timer } from 'rxjs';
import { CompanionJob, CompanionProgress, Letter, QuizResultResponse } from '../models/companion.models';
import { CompanionApiService } from './companion-api.service';
import { ConversationsService, SavedExchange } from './conversations.service';

/** Intervalle de consultation d'une tâche de fond (quiz, flashcards, résumé : 1 à 3 minutes). */
export const POLL_MS = 2000;

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

  private run(conversationId: number, pendingId: number, course: string | null, message: string): Observable<SavedExchange> {
    this.setProgress(pendingId, { tool: null, startedAt: Date.now() });
    return this.api.send(conversationId, course, message).pipe(
      expand((job) =>
        job.status === 'running' ? timer(POLL_MS).pipe(switchMap(() => this.api.job(job.job_id))) : EMPTY,
      ),
      tap((job) => this.updateTool(pendingId, job)),
      filter((job) => job.status !== 'running'),
      take(1),
      map((job) => {
        if (job.status === 'error' || job.exchange === null) {
          throw new Error(job.error ?? "L'assistant n'a pas pu répondre. Réessaie.");
        }
        return {
          conversation: job.exchange.conversation,
          messages: [job.exchange.user_message, ...job.exchange.assistant_messages],
        };
      }),
      finalize(() => this.setProgress(pendingId, null)),
    );
  }

  private updateTool(pendingId: number, job: CompanionJob): void {
    const current = this._progress().get(pendingId);
    if (current && current.tool !== job.tool) {
      this.setProgress(pendingId, { ...current, tool: job.tool });
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
