import { ChatMessage, Source } from './tutor.models';

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
  created_at: string;
}

/** Réponse de POST /api/conversations/{id}/messages. */
export interface Exchange {
  conversation: Conversation;
  user_message: StoredMessage;
  assistant_message: StoredMessage;
}

export const DEFAULT_CONVERSATION_TITLE = 'Nouvelle conversation';

/** Messages du backend (question, réponse, question…) → échanges affichés par le fil de discussion. */
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
      last.response = { answer: message.content, sources: message.sources };
    }
  }
  return result;
}
