/** Extrait du cours utilisé pour construire une réponse. */
export interface Source {
  course: string;
  page: number;
  score: number;
  excerpt: string;
}

export interface AskResponse {
  answer: string;
  /** Vide quand l'information n'est pas dans le cours. */
  sources: Source[];
}

export interface UploadResponse {
  course: string;
  chunks: number;
}

export interface DeleteResponse {
  deleted: string;
}

export type ChatMessageStatus = 'pending' | 'done' | 'error';

/** Un échange question/réponse de la session. */
export interface ChatMessage {
  id: number;
  question: string;
  /** Cours interrogé (null = tous les cours). */
  course: string | null;
  status: ChatMessageStatus;
  response: AskResponse | null;
  error: string | null;
}
