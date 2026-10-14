import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { Observable, finalize, map, of, switchMap, tap } from 'rxjs';
import { toMessage } from '../interceptors/error.interceptor';
import { Conversation, toChatMessages } from '../models/conversation.models';
import { ChatMessage } from '../models/tutor.models';
import { AuthService } from './auth.service';
import { ConversationsApiService } from './conversations-api.service';

const ACTIVE_KEY = 'ai-study-assistant.conversation';

function readActiveId(): number | null {
  try {
    const value = Number(localStorage.getItem(ACTIVE_KEY));
    return Number.isInteger(value) && value > 0 ? value : null;
  } catch {
    return null;
  }
}

function writeActiveId(id: number | null): void {
  try {
    if (id === null) {
      localStorage.removeItem(ACTIVE_KEY);
    } else {
      localStorage.setItem(ACTIVE_KEY, String(id));
    }
  } catch {
    // Stockage indisponible : la conversation ouverte ne sera pas retrouvée après un rechargement.
  }
}

/**
 * Conversations du tuteur : liste, conversation ouverte et ses messages (rechargés depuis le backend).
 * Les questions continuent si l'on change de page ; l'état est vidé quand l'étudiant change.
 */
@Injectable({ providedIn: 'root' })
export class ConversationsService {
  private readonly api = inject(ConversationsApiService);
  private readonly auth = inject(AuthService);
  private nextPendingId = -1;

  private readonly _conversations = signal<Conversation[]>([]);
  private readonly _activeId = signal<number | null>(null);
  private readonly _messages = signal<ChatMessage[]>([]);
  private readonly _loadingList = signal(false);
  private readonly _loadingMessages = signal(false);

  readonly conversations = this._conversations.asReadonly();
  /** null = nouvelle conversation (créée à la première question). */
  readonly activeId = this._activeId.asReadonly();
  readonly messages = this._messages.asReadonly();
  readonly loadingList = this._loadingList.asReadonly();
  readonly loadingMessages = this._loadingMessages.asReadonly();
  readonly active = computed(() => this._conversations().find((c) => c.id === this._activeId()) ?? null);
  readonly asking = computed(() => this._messages().some((m) => m.status === 'pending'));

  constructor() {
    // Déconnexion ou changement de compte : rien ne reste de l'étudiant précédent.
    effect(() => {
      this.auth.token();
      untracked(() => this.reset());
    });
  }

  /** Charge la liste et rouvre la dernière conversation (après un rechargement de la page). */
  load(): Observable<Conversation[]> {
    this._loadingList.set(true);
    return this.api.list().pipe(
      tap((list) => {
        this._conversations.set(list);
        const wanted = this._activeId() ?? readActiveId();
        if (wanted !== null && list.some((c) => c.id === wanted)) {
          if (wanted !== this._activeId() || this._messages().length === 0) {
            this.select(wanted);
          }
        } else if (!this.asking()) {
          this.startNew();
        }
      }),
      finalize(() => this._loadingList.set(false)),
    );
  }

  select(id: number): void {
    this._activeId.set(id);
    writeActiveId(id);
    this._messages.set([]);
    this._loadingMessages.set(true);
    this.api
      .messages(id)
      .pipe(finalize(() => this._loadingMessages.set(false)))
      .subscribe({
        next: (messages) => {
          if (this._activeId() === id) {
            this._messages.set(toChatMessages(messages));
          }
        },
        error: () => {
          // Conversation supprimée entre-temps (ou d'un autre compte) : on repart d'une conversation vide.
          if (this._activeId() === id) {
            this.startNew();
          }
        },
      });
  }

  startNew(): void {
    this._activeId.set(null);
    writeActiveId(null);
    this._messages.set([]);
    this._loadingMessages.set(false);
  }

  /**
   * Pose une question dans la conversation ouverte (créée si besoin).
   * Le message apparaît tout de suite en attente ; l'erreur éventuelle est aussi renvoyée à l'appelant.
   */
  ask(question: string, course: string | null): Observable<void> {
    const pendingId = this.nextPendingId--;
    this._messages.update((list) => [
      ...list,
      { id: pendingId, question, course, status: 'pending', response: null, error: null },
    ]);

    const activeId = this._activeId();
    const conversationId$ =
      activeId !== null
        ? of(activeId)
        : this.api.create(course).pipe(
            map((conversation) => {
              this.upsert(conversation);
              // L'étudiant n'a pas ouvert une autre conversation entre-temps : la nouvelle devient l'active
              if (this._activeId() === null) {
                this._activeId.set(conversation.id);
                writeActiveId(conversation.id);
              }
              return conversation.id;
            }),
          );

    let conversationId: number | null = activeId;
    return conversationId$.pipe(
      switchMap((id) => {
        conversationId = id;
        return this.api.ask(id, question, course);
      }),
      tap((exchange) => {
        this.upsert(exchange.conversation);
        if (this._activeId() === exchange.conversation.id) {
          const [message] = toChatMessages([exchange.user_message, exchange.assistant_message]);
          this.replaceMessage(pendingId, message);
        }
      }),
      map(() => undefined),
      tap({
        error: (err: unknown) => {
          if (this._activeId() === conversationId || conversationId === null) {
            this.replaceMessage(pendingId, { status: 'error', error: toMessage(err) });
          }
        },
      }),
    );
  }

  rename(id: number, title: string): Observable<Conversation> {
    return this.api.rename(id, title).pipe(tap((conversation) => this.upsert(conversation)));
  }

  remove(id: number): Observable<void> {
    return this.api.remove(id).pipe(
      tap(() => {
        this._conversations.update((list) => list.filter((c) => c.id !== id));
        if (this._activeId() === id) {
          this.startNew();
        }
      }),
      map(() => undefined),
    );
  }

  reset(): void {
    this._conversations.set([]);
    this._activeId.set(null);
    this._messages.set([]);
    this._loadingMessages.set(false);
  }

  /** Ajoute ou met à jour une conversation, la plus récente en tête. */
  private upsert(conversation: Conversation): void {
    this._conversations.update((list) =>
      [conversation, ...list.filter((c) => c.id !== conversation.id)].sort((a, b) =>
        b.updated_at.localeCompare(a.updated_at),
      ),
    );
  }

  private replaceMessage(id: number, patch: Partial<ChatMessage>): void {
    this._messages.update((list) => list.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }
}
