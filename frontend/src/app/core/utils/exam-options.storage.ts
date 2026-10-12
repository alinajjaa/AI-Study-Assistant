import {
  DEFAULT_EXAM_OPTIONS,
  DIFFICULTIES,
  EXAM_FORMATS,
  ExamOptions,
  QUESTION_COUNTS,
} from '../models/exam.models';

export const EXAM_OPTIONS_STORAGE_KEY = 'ai-study-assistant.exam-options';

/**
 * Relit les derniers choix de la modale d'examen.
 * Toute valeur absente ou invalide (ancienne version, JSON corrompu, numQuestions = 15…)
 * reprend sa valeur par défaut, sans erreur.
 */
export function loadExamOptions(): ExamOptions {
  try {
    const raw = localStorage.getItem(EXAM_OPTIONS_STORAGE_KEY);
    const saved: unknown = raw ? JSON.parse(raw) : null;
    if (typeof saved !== 'object' || saved === null) {
      return DEFAULT_EXAM_OPTIONS;
    }
    const format = 'format' in saved ? saved.format : null;
    const count = 'numQuestions' in saved ? saved.numQuestions : null;
    const difficulty = 'difficulty' in saved ? saved.difficulty : null;
    const includeAnswers = 'includeAnswers' in saved ? saved.includeAnswers : null;
    return {
      format: EXAM_FORMATS.find((f) => f.value === format)?.value ?? DEFAULT_EXAM_OPTIONS.format,
      numQuestions: QUESTION_COUNTS.find((n) => n === count) ?? DEFAULT_EXAM_OPTIONS.numQuestions,
      difficulty: DIFFICULTIES.find((d) => d.value === difficulty)?.value ?? DEFAULT_EXAM_OPTIONS.difficulty,
      includeAnswers: typeof includeAnswers === 'boolean' ? includeAnswers : DEFAULT_EXAM_OPTIONS.includeAnswers,
    };
  } catch {
    return DEFAULT_EXAM_OPTIONS;
  }
}

export function saveExamOptions(options: ExamOptions): void {
  try {
    localStorage.setItem(EXAM_OPTIONS_STORAGE_KEY, JSON.stringify(options));
  } catch {
    // Stockage indisponible (navigation privée, quota…) : on ne mémorise simplement pas.
  }
}
