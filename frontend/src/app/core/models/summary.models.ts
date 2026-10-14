export type SummaryMode = 'course' | 'topic';

export interface SummarySection {
  title: string;
  /** Pages citées par les puces de la section. */
  pages: number[];
  /** Puces terminées par leur référence [p.X]. */
  bullets: string[];
}

export interface SummaryContent {
  /** false : le thème demandé n'est pas dans le cours (overview l'explique). */
  found: boolean;
  overview: string;
  sections: SummarySection[];
}

/** Réponse de POST /api/courses/{course}/summary et de GET /api/summaries/{id}. */
export interface Summary {
  id: number;
  course: string;
  mode: SummaryMode;
  topic: string | null;
  content: SummaryContent;
  created_at: string;
  /** Résumé du cours entier déjà enregistré, renvoyé sans regénérer. */
  cached: boolean;
}

/** Élément de « Mes résumés » (GET /api/summaries). */
export interface SummaryListItem {
  id: number;
  course: string;
  mode: SummaryMode;
  topic: string | null;
  found: boolean;
  section_count: number;
  created_at: string;
}

export interface SummaryRequest {
  mode: SummaryMode;
  topic?: string;
  regenerate?: boolean;
}

/** Durée indicative (LLM local) : une section de 6 passages ≈ 15 s. */
export const SUMMARY_MINUTES: Readonly<Record<SummaryMode, number>> = { course: 2, topic: 1 };
