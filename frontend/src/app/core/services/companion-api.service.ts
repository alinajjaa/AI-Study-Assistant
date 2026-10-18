import { HttpClient, HttpEventType } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CompanionJob, CompanionStreamEvent, Letter, QuizResultResponse } from '../models/companion.models';
import { parseSse } from '../utils/sse.utils';

const STREAM_EVENTS = new Set(['start', 'tool', 'token', 'final', 'error']);

@Injectable({ providedIn: 'root' })
export class CompanionApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  /** Réponse directe (status « done ») ou tâche de fond (status « running », à consulter avec job()). */
  send(conversationId: number, course: string | null, message: string): Observable<CompanionJob> {
    return this.http.post<CompanionJob>(`${this.apiUrl}/companion/messages`, {
      conversation_id: conversationId,
      course,
      message,
    });
  }

  /**
   * Même demande en Server-Sent Events : début (job_id), outil en cours, fragments de la réponse du tuteur,
   * puis réponse finale validée (ou erreur). Passe par HttpClient : jeton et gestion des erreurs inchangés.
   */
  stream(conversationId: number, course: string | null, message: string): Observable<CompanionStreamEvent> {
    return new Observable<CompanionStreamEvent>((subscriber) => {
      let consumed = 0;
      const emit = (text: string) => {
        const { events, consumed: used } = parseSse(text.slice(consumed));
        consumed += used;
        for (const event of events) {
          if (STREAM_EVENTS.has(event.event)) {
            subscriber.next(event as CompanionStreamEvent);
          }
        }
      };
      const subscription = this.http
        .post(
          `${this.apiUrl}/companion/messages/stream`,
          { conversation_id: conversationId, course, message },
          { observe: 'events', reportProgress: true, responseType: 'text' },
        )
        .subscribe({
          next: (event) => {
            if (event.type === HttpEventType.DownloadProgress && event.partialText !== undefined) {
              emit(event.partialText);
            } else if (event.type === HttpEventType.Response) {
              emit(event.body ?? '');
              subscriber.complete();
            }
          },
          error: (err: unknown) => subscriber.error(err),
        });
      return () => subscription.unsubscribe();
    });
  }

  job(jobId: string): Observable<CompanionJob> {
    return this.http.get<CompanionJob>(`${this.apiUrl}/companion/jobs/${encodeURIComponent(jobId)}`);
  }

  saveQuizResult(messageId: number, answers: readonly Letter[]): Observable<QuizResultResponse> {
    return this.http.post<QuizResultResponse>(`${this.apiUrl}/quiz-results`, { message_id: messageId, answers });
  }
}
