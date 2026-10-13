import { EXAM_TOTAL_POINTS, ExamOptions, QuestionCount } from '../models/exam.models';

/** Durée de génération mesurée sur le backend (Ollama qwen2.5:7b), en minutes. */
export const COMPLETE_EXAM_MINUTES = 3;
export const QCM_EXAM_MINUTES: Readonly<Record<QuestionCount, number>> = { 5: 1, 10: 2, 20: 3 };

/**
 * Durée estimée de génération, seule source pour la modale et la notification de lancement.
 * La difficulté n'influe pas sur la durée.
 */
export function estimateExamMinutes(options: Pick<ExamOptions, 'format' | 'numQuestions'>): number {
  return options.format === 'complet' ? COMPLETE_EXAM_MINUTES : QCM_EXAM_MINUTES[options.numQuestions];
}

/** Barème du QCM rapide : 20 points répartis sur toutes les questions. */
export function pointsPerQuestion(numQuestions: number): number {
  return EXAM_TOTAL_POINTS / numQuestions;
}

/** Points au format français : « 20 », « 19,5 ». */
export function formatPoints(points: number): string {
  return points.toLocaleString('fr-FR', { maximumFractionDigits: 2 });
}

/** Libellé court d'un examen pour les notifications : « Examen complet », « QCM rapide (10 questions) ». */
export function describeExam(options: Pick<ExamOptions, 'format' | 'numQuestions'>): string {
  return options.format === 'complet' ? 'Examen complet' : `QCM rapide (${options.numQuestions} questions)`;
}

export interface ExamResultSummary {
  kind: 'success' | 'warning';
  title: string;
  message: string;
}

/**
 * Notification de fin de génération, à partir des en-têtes de la réponse.
 * `total` (X-Exam-Total) fait foi ; s'il est absent (null), on compare questions générées et attendues.
 */
export function summarizeExamResult(generated: number, expected: number, total: number | null): ExamResultSummary {
  const plural = generated > 1 ? 's' : '';
  if (total !== null) {
    if (total < EXAM_TOTAL_POINTS) {
      return {
        kind: 'warning',
        title: `Examen incomplet : noté sur ${formatPoints(total)} au lieu de ${EXAM_TOTAL_POINTS}`,
        message: `Certaines questions n'ont pas passé la vérification (${generated} sur ${expected} retenues).`,
      };
    }
    return {
      kind: 'success',
      title: `Examen téléchargé : ${generated} question${plural}, noté sur ${EXAM_TOTAL_POINTS}`,
      message: 'Le PDF est dans tes téléchargements.',
    };
  }
  if (generated < expected) {
    return {
      kind: 'warning',
      title: `Examen téléchargé : ${generated} question${plural}`,
      message: `Seulement ${generated} questions sur ${expected} ont pu être générées.`,
    };
  }
  return {
    kind: 'success',
    title: `Examen téléchargé : ${generated} question${plural}`,
    message: 'Le PDF est dans tes téléchargements.',
  };
}

/** Durée écoulée au format m:ss. */
export function formatElapsed(totalSeconds: number): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** Nom de fichier de repli : examen_<cours>.pdf, sans caractères interdits. */
export function fallbackExamFilename(course: string): string {
  const safe = course.replace(/[^\p{L}\p{N}_-]+/gu, '_').replace(/^_+|_+$/g, '') || 'cours';
  return `examen_${safe}.pdf`;
}

/**
 * Lit le nom de fichier d'un en-tête Content-Disposition.
 * Gère filename*=UTF-8''…, filename="…" et filename=… ; repli sur examen_<cours>.pdf.
 */
export function filenameFromContentDisposition(header: string | null, course: string): string {
  if (header) {
    const encoded = /filename\*\s*=\s*(?:[\w-]+)?'[^']*'([^;]+)/i.exec(header);
    if (encoded) {
      try {
        const name = decodeURIComponent(encoded[1].trim().replace(/^"|"$/g, ''));
        if (name) {
          return name;
        }
      } catch {
        // Encodage invalide : on tente la forme simple.
      }
    }
    const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(header);
    const name = (plain?.[1] ?? plain?.[2] ?? '').trim();
    if (name) {
      return name;
    }
  }
  return fallbackExamFilename(course);
}

/** Déclenche le téléchargement d'un Blob via un lien temporaire. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Laisse au navigateur le temps de démarrer le téléchargement avant de libérer l'URL.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
