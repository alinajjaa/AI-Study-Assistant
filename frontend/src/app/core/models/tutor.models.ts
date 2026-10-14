/** Extrait du cours utilisé pour construire une réponse. */
export interface Source {
  course: string;
  page: number;
  score: number;
  excerpt: string;
}

/** Type d'affichage d'un message de l'assistant (Study Companion). */
export type MessageKind = 'text' | 'answer' | 'quiz' | 'summary' | 'flashcards' | 'progress';

export interface AskResponse {
  answer: string;
  /** Vide quand l'information n'est pas dans le cours. */
  sources: Source[];
  /** Absent pour les réponses du tuteur antérieures au Study Companion (= answer). */
  kind?: MessageKind;
  /** Données de l'affichage riche (quiz, résumé, paquet de flashcards, progression…). */
  payload?: unknown;
  /** Identifiant du message enregistré (pour enregistrer le score d'un quiz). */
  messageId?: number;
  /** false : l'information n'est pas dans le cours (réponse NOT_FOUND du tuteur). */
  answered?: boolean;
}

/** Réponse sourcée « Hors du cours » : rien d'autre que la mention n'est affiché (ni texte, ni sources). */
export function isOffCourse(response: AskResponse): boolean {
  return (response.kind ?? 'answer') === 'answer' && (response.answered === false || response.sources.length === 0);
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
  /** Réponses supplémentaires du même échange (l'assistant a utilisé plusieurs outils). */
  extra?: AskResponse[];
}
