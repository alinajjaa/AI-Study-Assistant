import { Level } from './auth.models';
import { Conversation, StoredMessage } from './conversation.models';
import { LevelSuggestion, ProfileStats, WeakPoint } from './profile.models';
import { Summary } from './summary.models';

export type Letter = 'A' | 'B' | 'C' | 'D';
export const LETTERS: readonly Letter[] = ['A', 'B', 'C', 'D'];

/** Outils de l'agent (phase6_agent/tools.py). */
export type CompanionTool = 'ask_course' | 'summarize' | 'generate_quiz' | 'generate_flashcards' | 'get_progress';

/** « L'assistant … » pendant l'exécution de l'outil. */
export const TOOL_LABELS: Readonly<Record<CompanionTool, string>> = {
  ask_course: 'cherche la réponse dans ton cours',
  summarize: 'prépare le résumé',
  generate_quiz: 'génère ton quiz',
  generate_flashcards: 'prépare tes flashcards',
  get_progress: 'regarde tes progrès',
};

export function toolLabel(tool: string | null): string | null {
  return tool !== null && tool in TOOL_LABELS ? TOOL_LABELS[tool as CompanionTool] : null;
}

/**
 * Actions rapides sous la zone de saisie : elles envoient une demande pré-remplie à l'agent, sur le cours
 * sélectionné. « Examen » (message null) n'est pas un outil de l'agent : il ouvre la modale d'examen existante.
 */
export interface QuickAction {
  label: string;
  message: string | null;
  icon: 'summary' | 'quiz' | 'cards' | 'exam';
}

export const QUICK_ACTIONS: readonly QuickAction[] = [
  { label: 'Flashcards', message: 'Prépare-moi des flashcards pour réviser.', icon: 'cards' },
  { label: 'Résumé', message: 'Résume le cours.', icon: 'summary' },
  { label: 'Examen', message: null, icon: 'exam' },
  { label: 'Quiz', message: 'Fais-moi un quiz de 5 questions.', icon: 'quiz' },
];

// ---------------------------------------------------------------------------
// Payloads des messages (Message.payload)
// ---------------------------------------------------------------------------

export interface QuizQuestion {
  question: string;
  choices: string[];
  answer: Letter;
  explanation: string;
  page: number;
  /** Notion testée (points faibles du profil). */
  concept: string;
}

export interface QuizResultState {
  answers: Letter[];
  correct: boolean[];
  score: number;
  total: number;
  submitted_at: string;
}

export interface QuizPayload {
  course: string;
  difficulty: string;
  questions: QuizQuestion[];
  /** null tant que le quiz n'a pas été terminé. */
  result: QuizResultState | null;
}

export interface FlashcardsPayload {
  deck_id: number;
  course: string;
  card_count: number;
  concepts: string[];
}

export interface QuizStats {
  answers: number;
  /** Entre 0 et 1, null sans réponse. */
  correct_rate: number | null;
}

export interface ProgressPayload {
  level: Level;
  stats: ProfileStats;
  quiz: QuizStats;
  weak_points: WeakPoint[];
  level_suggestion: LevelSuggestion | null;
}

/** Réponse texte ; course_choices : l'assistant demande sur quel cours travailler. */
export interface TextPayload {
  course_choices?: string[];
}

export type SummaryPayload = Summary;

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

/** Messages enregistrés pour une demande : celle de l'étudiant et 1 à 3 réponses (une par outil). */
export interface CompanionExchange {
  conversation: Conversation;
  user_message: StoredMessage;
  assistant_messages: StoredMessage[];
  tools: string[];
  fallback: boolean;
}

/** Réponse de POST /api/companion/messages et de GET /api/companion/jobs/{id}. */
export interface CompanionJob {
  job_id: string;
  status: 'running' | 'done' | 'error';
  tool: string | null;
  elapsed_s: number;
  exchange: CompanionExchange | null;
  error: string | null;
}

/** Réponse de POST /api/quiz-results. */
export interface QuizResultResponse {
  score: number;
  total: number;
  correct: boolean[];
  message: StoredMessage;
}

/** Suivi d'une demande en cours (indicateur « L'assistant travaille… »). */
export interface CompanionProgress {
  tool: string | null;
  startedAt: number;
}
