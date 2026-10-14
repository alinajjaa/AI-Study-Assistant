export type ExamFormat = 'complet' | 'qcm';

export type Difficulty = 'facile' | 'moyen' | 'difficile';

/** Nombre de QCM du format « qcm » (4, 2 ou 1 point par question). */
export type QuestionCount = 5 | 10 | 20;

/** Options choisies dans la modale de génération d'examen. */
export interface ExamOptions {
  format: ExamFormat;
  /** Utilisé uniquement pour le format « qcm ». */
  numQuestions: QuestionCount;
  difficulty: Difficulty;
  includeAnswers: boolean;
}

/** Un examen est toujours noté sur 20. */
export const EXAM_TOTAL_POINTS = 20;

export const EXAM_FORMATS: readonly { value: ExamFormat; label: string; description: string }[] = [
  {
    value: 'complet',
    label: 'Examen complet',
    description: '4 parties · QCM, Vrai/Faux, réponses courtes, réflexion · noté sur 20',
  },
  { value: 'qcm', label: 'QCM rapide', description: 'Uniquement des QCM · noté sur 20' },
];

/** Structure fixe de l'examen complet (15 questions, 20 points). */
export const COMPLETE_EXAM_PARTS: readonly { part: string; count: number; kind: string; points: number }[] = [
  { part: 'A', count: 8, kind: 'QCM', points: 8 },
  { part: 'B', count: 4, kind: 'Vrai/Faux', points: 4 },
  { part: 'C', count: 2, kind: 'réponses courtes', points: 4 },
  { part: 'D', count: 1, kind: 'réflexion', points: 4 },
];

export const QUESTION_COUNTS: readonly QuestionCount[] = [5, 10, 20];

export const DIFFICULTIES: readonly { value: Difficulty; label: string }[] = [
  { value: 'facile', label: 'Facile' },
  { value: 'moyen', label: 'Moyen' },
  { value: 'difficile', label: 'Difficile' },
];

export const DEFAULT_EXAM_OPTIONS: ExamOptions = {
  format: 'complet',
  numQuestions: 10,
  difficulty: 'moyen',
  includeAnswers: true,
};

/** Examen enregistré dans l'historique (GET /api/exams). */
export interface ExamRecord {
  id: number;
  course: string;
  format: ExamFormat;
  difficulty: Difficulty;
  question_count: number;
  include_answers: boolean;
  created_at: string;
}

export function examFormatLabel(format: ExamFormat): string {
  return EXAM_FORMATS.find((f) => f.value === format)?.label ?? format;
}

export function difficultyLabel(difficulty: Difficulty): string {
  return DIFFICULTIES.find((d) => d.value === difficulty)?.label ?? difficulty;
}
