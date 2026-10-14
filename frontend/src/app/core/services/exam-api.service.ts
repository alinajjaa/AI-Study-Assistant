import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ExamOptions, ExamRecord } from '../models/exam.models';

@Injectable({ providedIn: 'root' })
export class ExamApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  /**
   * Génère un examen PDF noté sur 20. Réponse complète pour lire les en-têtes
   * Content-Disposition, X-Questions-Generated, X-Questions-Expected et X-Exam-Total.
   * Pas de timeout : la génération peut prendre plusieurs minutes.
   */
  generateExam(course: string, options: ExamOptions): Observable<HttpResponse<Blob>> {
    return this.http.post(
      `${this.apiUrl}/courses/${encodeURIComponent(course)}/exam`,
      {
        format: options.format,
        num_questions: options.numQuestions,
        difficulty: options.difficulty,
        include_answers: options.includeAnswers,
      },
      { observe: 'response', responseType: 'blob' },
    );
  }

  /** Historique des examens de l'étudiant, le plus récent en premier. */
  listExams(): Observable<ExamRecord[]> {
    return this.http.get<ExamRecord[]>(`${this.apiUrl}/exams`);
  }

  /** Retéléchargement d'un examen de l'historique (réponse complète pour lire Content-Disposition). */
  downloadExam(id: number): Observable<HttpResponse<Blob>> {
    return this.http.get(`${this.apiUrl}/exams/${id}/pdf`, { observe: 'response', responseType: 'blob' });
  }

  deleteExam(id: number): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.apiUrl}/exams/${id}`);
  }
}
