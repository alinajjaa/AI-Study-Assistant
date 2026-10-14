import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CompanionExchange, CompanionJob, QuizPayload } from '../models/companion.models';
import { Conversation, StoredMessage, toChatMessages } from '../models/conversation.models';
import { TOKEN_KEY } from './auth.service';
import { CompanionService, POLL_MS } from './companion.service';
import { ConversationsService } from './conversations.service';

const api = environment.apiUrl;

function conversation(id: number): Conversation {
  return { id, title: 'Quiz', course: 'CNN', created_at: '2026-10-14T10:00:00Z', updated_at: '2026-10-14T10:00:00Z' };
}

function stored(id: number, role: 'user' | 'assistant', content: string, kind = 'text', payload: unknown = null): StoredMessage {
  return {
    id,
    role,
    content,
    course: 'CNN',
    sources: [],
    answered: true,
    kind: kind as StoredMessage['kind'],
    payload,
    created_at: '2026-10-14T10:00:00Z',
  };
}

const QUIZ: QuizPayload = {
  course: 'CNN',
  difficulty: 'moyen',
  questions: [
    { question: 'Rôle du pooling ?', choices: ['Réduire', 'Ajouter', 'Normaliser', 'Mélanger'], answer: 'A', explanation: 'Il réduit.', page: 1, concept: 'Pooling' },
  ],
  result: null,
};

function exchange(): CompanionExchange {
  return {
    conversation: conversation(5),
    user_message: stored(20, 'user', 'Un quiz stp'),
    assistant_messages: [stored(21, 'assistant', 'Voici ton quiz !', 'quiz', QUIZ)],
    tools: ['generate_quiz'],
    fallback: false,
  };
}

function job(status: CompanionJob['status'], extra: Partial<CompanionJob> = {}): CompanionJob {
  return { job_id: 'abc', status, tool: 'generate_quiz', elapsed_s: 1, exchange: null, error: null, ...extra };
}

describe('toChatMessages — Study Companion', () => {
  it('garde le type et les données de chaque réponse, et regroupe plusieurs réponses dans extra', () => {
    const [chat] = toChatMessages([
      stored(1, 'user', 'Résume et fais un quiz'),
      stored(2, 'assistant', 'Résumé prêt.', 'summary', { id: 3 }),
      stored(3, 'assistant', 'Quiz prêt.', 'quiz', QUIZ),
    ]);
    expect(chat.response).toMatchObject({ answer: 'Résumé prêt.', kind: 'summary', payload: { id: 3 }, messageId: 2 });
    expect(chat.extra).toEqual([expect.objectContaining({ kind: 'quiz', messageId: 3 })]);
  });

  it('un ancien message sans type reste une réponse du tuteur', () => {
    const old = { ...stored(2, 'assistant', 'Réponse [p.1].'), kind: undefined, payload: undefined };
    const [chat] = toChatMessages([stored(1, 'user', 'Q'), old]);
    expect(chat.response?.kind).toBe('answer');
  });
});

describe('CompanionService', () => {
  let service: CompanionService;
  let conversations: ConversationsService;
  let backend: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(TOKEN_KEY, 'jeton');
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CompanionService);
    conversations = TestBed.inject(ConversationsService);
    backend = TestBed.inject(HttpTestingController);
    TestBed.tick();
  });

  afterEach(() => {
    backend.verify();
    localStorage.clear();
    vi.useRealTimers();
  });

  function startInConversation5(message: string, course: string | null): Promise<void> {
    conversations.select(5);
    backend.expectOne(`${api}/conversations/5/messages`).flush([]);
    return firstValueFrom(service.send(message, course));
  }

  it('réponse directe : les messages enregistrés remplacent le message en attente', async () => {
    const sent = startInConversation5('Un quiz stp', 'CNN');
    expect(conversations.messages()[0].status).toBe('pending');
    expect(service.busy()).toBe(true);

    const req = backend.expectOne(`${api}/companion/messages`);
    expect(req.request.body).toEqual({ conversation_id: 5, course: 'CNN', message: 'Un quiz stp' });
    req.flush(job('done', { exchange: exchange() }));
    await sent;

    const [message] = conversations.messages();
    expect(message).toMatchObject({ id: 20, status: 'done', question: 'Un quiz stp' });
    expect(message.response).toMatchObject({ kind: 'quiz', messageId: 21, answer: 'Voici ton quiz !' });
    expect(service.busy()).toBe(false);
  });

  it('tâche de fond : consulte la tâche jusqu’à la fin et affiche l’outil en cours', async () => {
    vi.useFakeTimers();
    const sent = startInConversation5('Un quiz stp', 'CNN');
    const pendingId = conversations.messages()[0].id;
    backend.expectOne(`${api}/companion/messages`).flush(job('running', { tool: null }), { status: 202, statusText: 'Accepted' });
    expect(service.progress().get(pendingId)?.tool).toBeNull();

    vi.advanceTimersByTime(POLL_MS);
    backend.expectOne(`${api}/companion/jobs/abc`).flush(job('running'));
    expect(service.progress().get(pendingId)?.tool).toBe('generate_quiz');

    vi.advanceTimersByTime(POLL_MS);
    backend.expectOne(`${api}/companion/jobs/abc`).flush(job('done', { exchange: exchange() }));
    await sent;
    expect(conversations.messages()[0].status).toBe('done');
    expect(service.progress().size).toBe(0);
  });

  it('tâche en erreur : le message en attente affiche l’erreur', async () => {
    const sent = startInConversation5('Un quiz stp', 'CNN');
    backend.expectOne(`${api}/companion/messages`).flush(job('error', { error: 'Ollama est arrêté.' }));
    await expect(sent).rejects.toThrow('Ollama est arrêté.');
    expect(conversations.messages()[0]).toMatchObject({ status: 'error', error: 'Ollama est arrêté.' });
  });

  it('score du quiz : enregistré puis reporté dans la réponse affichée', async () => {
    const sent = startInConversation5('Un quiz stp', 'CNN');
    backend.expectOne(`${api}/companion/messages`).flush(job('done', { exchange: exchange() }));
    await sent;

    const saved = firstValueFrom(service.saveQuizResult(21, ['A']));
    const req = backend.expectOne(`${api}/quiz-results`);
    expect(req.request.body).toEqual({ message_id: 21, answers: ['A'] });
    const result = { answers: ['A'], correct: [true], score: 1, total: 1, submitted_at: '2026-10-14T10:05:00Z' };
    req.flush({ score: 1, total: 1, correct: [true], message: stored(21, 'assistant', 'Voici ton quiz !', 'quiz', { ...QUIZ, result }) });
    await saved;
    expect((conversations.messages()[0].response?.payload as QuizPayload).result?.score).toBe(1);
  });
});
