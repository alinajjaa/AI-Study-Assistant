import { HttpClient, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ExamOptions } from '../models/exam.models';

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
}
