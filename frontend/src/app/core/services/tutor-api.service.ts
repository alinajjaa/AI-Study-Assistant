import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { DeleteResponse, UploadResponse } from '../models/tutor.models';

@Injectable({ providedIn: 'root' })
export class TutorApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = environment.apiUrl;

  upload(file: File, course?: string): Observable<UploadResponse> {
    const form = new FormData();
    form.append('file', file);
    if (course?.trim()) {
      form.append('course', course.trim());
    }
    return this.http.post<UploadResponse>(`${this.apiUrl}/upload`, form);
  }

  getCourses(): Observable<string[]> {
    return this.http.get<string[]>(`${this.apiUrl}/courses`);
  }

  deleteCourse(course: string): Observable<DeleteResponse> {
    return this.http.delete<DeleteResponse>(`${this.apiUrl}/courses/${encodeURIComponent(course)}`);
  }
}
