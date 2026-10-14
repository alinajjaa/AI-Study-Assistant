import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Conversation, StoredMessage } from '../models/conversation.models';

@Injectable({ providedIn: 'root' })
export class ConversationsApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${environment.apiUrl}/conversations`;

  list(): Observable<Conversation[]> {
    return this.http.get<Conversation[]>(this.url);
  }

  create(course: string | null): Observable<Conversation> {
    return this.http.post<Conversation>(this.url, { course });
  }

  rename(id: number, title: string): Observable<Conversation> {
    return this.http.patch<Conversation>(`${this.url}/${id}`, { title });
  }

  remove(id: number): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.url}/${id}`);
  }

  messages(id: number): Observable<StoredMessage[]> {
    return this.http.get<StoredMessage[]>(`${this.url}/${id}/messages`);
  }
}
