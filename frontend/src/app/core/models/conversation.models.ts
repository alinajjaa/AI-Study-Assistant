import { AskResponse, ChatMessage, MessageKind, Source } from './tutor.models';

export interface Conversation {
  id: number;
  title: string;
  /** Cours de la dernière question (null = tous les cours). */
  course: string | null;
  created_at: string;
  updated_at: string;
}

/** Message enregistré par le backend. */
export interface StoredMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  course: string | null;
  sources: Source[];
  /** false si l'information n'est pas dans le cours. */
  answered: boolean;
  /** Absent avec un ancien backend : text (question) ou answer (réponse du tuteur). */
  kind?: MessageKind;
  payload?: unknown;
  created_at: string;
}

export const DEFAULT_CONVERSATION_TITLE = 'Nouvelle conversation';

function toResponse(message: StoredMessage): AskResponse {
  return {
    answer: message.content,
    sources: message.sources,
    kind: message.kind ?? 'answer',
    payload: message.payload ?? null,
    messageId: message.id,
    answered: message.answered,
  };
}

/**
 * Messages du backend (question, réponse(s), question…) → échanges affichés par le fil de discussion.
 * Le Study Companion peut enregistrer plusieurs réponses pour une demande (une par outil) : elles vont dans extra.
 */
export function toChatMessages(messages: readonly StoredMessage[]): ChatMessage[] {
  const result: ChatMessage[] = [];
  for (const message of messages) {
    if (message.role === 'user') {
      result.push({
        id: message.id,
        question: message.content,
        course: message.course,
        status: 'error',
        response: null,
        error: 'Réponse non enregistrée.',
      });
      continue;
    }
    const last = result.at(-1);
    if (last && last.response === null) {
      last.status = 'done';
      last.error = null;
      last.response = toResponse(message);
    } else if (last) {
      last.extra = [...(last.extra ?? []), toResponse(message)];
    }
  }
  return result;
}
