import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CompanionJob, Letter, QuizResultResponse } from '../models/companion.models';

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

  job(jobId: string): Observable<CompanionJob> {
    return this.http.get<CompanionJob>(`${this.apiUrl}/companion/jobs/${encodeURIComponent(jobId)}`);
  }

  saveQuizResult(messageId: number, answers: readonly Letter[]): Observable<QuizResultResponse> {
    return this.http.post<QuizResultResponse>(`${this.apiUrl}/quiz-results`, { message_id: messageId, answers });
  }
}
