import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom, of, throwError } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Conversation, StoredMessage, toChatMessages } from '../models/conversation.models';
import { AuthService, TOKEN_KEY } from './auth.service';
import { ConversationsService } from './conversations.service';

const url = `${environment.apiUrl}/conversations`;

function conversation(id: number, updated: string, title = `Conversation ${id}`): Conversation {
  return { id, title, course: 'CNN', created_at: updated, updated_at: updated };
}

function message(id: number, role: 'user' | 'assistant', content: string): StoredMessage {
  return {
    id,
    role,
    content,
    course: 'CNN',
    sources: role === 'assistant' ? [{ course: 'CNN', page: 3, score: 0.9, excerpt: 'Le pooling…' }] : [],
    answered: true,
    created_at: '2026-10-14T10:00:00Z',
  };
}

describe('toChatMessages', () => {
  it('regroupe question et réponse en un échange', () => {
    const chat = toChatMessages([message(1, 'user', 'Pooling ?'), message(2, 'assistant', 'Il réduit…')]);
    expect(chat).toHaveLength(1);
    expect(chat[0]).toMatchObject({ id: 1, question: 'Pooling ?', course: 'CNN', status: 'done' });
    expect(chat[0].response?.answer).toBe('Il réduit…');
    expect(chat[0].response?.sources[0].page).toBe(3);
  });

  it('signale une question sans réponse enregistrée', () => {
    expect(toChatMessages([message(1, 'user', 'Pooling ?')])[0].status).toBe('error');
  });
});

describe('ConversationsService', () => {
  let service: ConversationsService;
  let backend: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(TOKEN_KEY, 'jeton');
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ConversationsService);
    backend = TestBed.inject(HttpTestingController);
    TestBed.tick(); // effet initial (réinitialisation liée au compte)
  });

  afterEach(() => {
    backend.verify();
    localStorage.clear();
  });

  it('charge la liste et rouvre la dernière conversation après un rechargement', async () => {
    localStorage.setItem('ai-study-assistant.conversation', '7');
    const loaded = firstValueFrom(service.load());
    backend.expectOne(url).flush([conversation(7, '2026-10-14T10:00:00Z'), conversation(3, '2026-10-13T10:00:00Z')]);
    await loaded;

    expect(service.activeId()).toBe(7);
    backend.expectOne(`${url}/7/messages`).flush([message(1, 'user', 'Pooling ?'), message(2, 'assistant', 'Il réduit…')]);
    expect(service.messages()).toHaveLength(1);
    expect(service.messages()[0].response?.answer).toBe('Il réduit…');
  });

  it('ignore une conversation mémorisée qui n’est pas dans la liste (autre compte)', async () => {
    localStorage.setItem('ai-study-assistant.conversation', '99');
    const loaded = firstValueFrom(service.load());
    backend.expectOne(url).flush([conversation(7, '2026-10-14T10:00:00Z')]);
    await loaded;
    expect(service.activeId()).toBeNull();
    expect(localStorage.getItem('ai-study-assistant.conversation')).toBeNull();
  });

  it('recharge les messages depuis le backend au changement de conversation', () => {
    service.select(3);
    expect(service.loadingMessages()).toBe(true);
    backend.expectOne(`${url}/3/messages`).flush([message(10, 'user', 'Q'), message(11, 'assistant', 'R')]);
    expect(service.loadingMessages()).toBe(false);
    expect(service.messages()[0].question).toBe('Q');
  });

  it('première demande : crée la conversation (avec le cours sélectionné) puis enregistre l’échange', async () => {
    const request = vi.fn((conversationId: number) =>
      of({
        conversation: conversation(conversationId, '2026-10-14T10:01:00Z', 'Qu’est-ce que le pooling ?'),
        messages: [message(20, 'user', 'Qu’est-ce que le pooling ?'), message(21, 'assistant', 'Il réduit [p.3].')],
      }),
    );
    const asked = firstValueFrom(service.send('Qu’est-ce que le pooling ?', 'CNN', request));
    expect(service.asking()).toBe(true);
    expect(service.messages()[0]).toMatchObject({ status: 'pending', course: 'CNN' });

    const create = backend.expectOne(url);
    expect(create.request.method).toBe('POST');
    expect(create.request.body).toEqual({ course: 'CNN' });
    create.flush(conversation(5, '2026-10-14T10:00:00Z', 'Nouvelle conversation'));
    await asked;

    expect(request).toHaveBeenCalledWith(5, expect.any(Number));
    expect(service.activeId()).toBe(5);
    expect(service.asking()).toBe(false);
    expect(service.messages()).toEqual([expect.objectContaining({ id: 20, status: 'done' })]);
    expect(service.conversations()[0].title).toBe('Qu’est-ce que le pooling ?');
  });

  it('marque la demande en erreur si l’agent échoue', async () => {
    service.select(5);
    backend.expectOne(`${url}/5/messages`).flush([]);
    const asked = firstValueFrom(service.send('Pooling ?', null, () => throwError(() => new Error('LLM'))));
    await expect(asked).rejects.toBeTruthy();
    expect(service.messages()[0].status).toBe('error');
  });

  it('renommer met la liste à jour ; supprimer la conversation ouverte en démarre une nouvelle', async () => {
    const loaded = firstValueFrom(service.load());
    backend.expectOne(url).flush([conversation(1, '2026-10-14T10:00:00Z'), conversation(2, '2026-10-13T10:00:00Z')]);
    await loaded;
    service.select(1);
    backend.expectOne(`${url}/1/messages`).flush([]);

    const renamed = firstValueFrom(service.rename(2, 'Révisions'));
    const patch = backend.expectOne(`${url}/2`);
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.body).toEqual({ title: 'Révisions' });
    patch.flush({ ...conversation(2, '2026-10-13T10:00:00Z'), title: 'Révisions' });
    await renamed;
    expect(service.conversations().find((c) => c.id === 2)?.title).toBe('Révisions');

    const removed = firstValueFrom(service.remove(1));
    const del = backend.expectOne(`${url}/1`);
    expect(del.request.method).toBe('DELETE');
    del.flush({ deleted: 1 });
    await removed;
    expect(service.conversations().map((c) => c.id)).toEqual([2]);
    expect(service.activeId()).toBeNull();
  });

  it('vide tout à la déconnexion', async () => {
    const loaded = firstValueFrom(service.load());
    backend.expectOne(url).flush([conversation(1, '2026-10-14T10:00:00Z')]);
    await loaded;
    TestBed.inject(AuthService).clearSession();
    TestBed.tick();
    expect(service.conversations()).toEqual([]);
    expect(service.messages()).toEqual([]);
  });
});
