import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Summary, SummaryListItem, SummaryRequest } from '../models/summary.models';

@Injectable({ providedIn: 'root' })
export class SummariesApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  /** Résumé du cours entier (renvoyé depuis le cache s'il existe) ou explication d'un thème. Pas de timeout. */
  create(course: string, request: SummaryRequest): Observable<Summary> {
    return this.http.post<Summary>(`${this.apiUrl}/courses/${encodeURIComponent(course)}/summary`, request);
  }

  list(course: string): Observable<SummaryListItem[]> {
    return this.http.get<SummaryListItem[]>(`${this.apiUrl}/summaries`, { params: { course } });
  }

  get(id: number): Observable<Summary> {
    return this.http.get<Summary>(`${this.apiUrl}/summaries/${id}`);
  }

  remove(id: number): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.apiUrl}/summaries/${id}`);
  }
}
