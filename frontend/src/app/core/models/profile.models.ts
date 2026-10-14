import { Level } from './auth.models';

export interface ProfileStats {
  courses: number;
  questions: number;
  exams: number;
  cards_reviewed: number;
  /** Entre 0 et 1, null sans révision. */
  known_rate: number | null;
}

/** Concept souvent marqué « À revoir » (au moins 2 révisions). */
export interface WeakPoint {
  course: string;
  concept: string;
  reviews: number;
  /** Entre 0 et 1. */
  to_review_rate: number;
}

/** Suggestion d'ajustement du niveau (jamais appliquée automatiquement). */
export interface LevelSuggestion {
  level: Level;
  direction: 'up' | 'down';
  reviews: number;
  known_rate: number;
}

/** Réponses aux quiz du Study Companion. */
export interface ProfileQuizStats {
  answers: number;
  /** Entre 0 et 1, null sans réponse. */
  correct_rate: number | null;
}

/** Réponse de GET /api/profile. */
export interface Profile {
  email: string;
  level: Level;
  stats: ProfileStats;
  /** Absent avec un backend antérieur au Study Companion. */
  quiz?: ProfileQuizStats;
  weak_points: WeakPoint[];
  level_suggestion: LevelSuggestion | null;
}

/** 0.756 → « 76 % ». */
export function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)} %`;
}
