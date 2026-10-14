import { Component, input, output } from '@angular/core';
import { formatElapsed } from '../../../core/utils/exam.utils';
import { Loader } from '../loader/loader';

/** Liste « Mes cours », partagée par l'Assistant, les flashcards et les résumés. */
@Component({
  selector: 'app-course-selector',
  imports: [Loader],
  templateUrl: './course-selector.html',
  styleUrl: './course-selector.css',
})
export class CourseSelector {
  readonly courses = input.required<string[]>();
  /** Cours sélectionné, null = tous les cours. */
  readonly selected = input<string | null>(null);
  readonly loading = input(false);
  readonly deleting = input(false);
  /** Affiche l'entrée « Tous les cours » en tête de liste. */
  readonly allowAll = input(true);
  /** Affiche les actions par cours (générer un examen, supprimer). */
  readonly actions = input(true);
  /** Générations en cours : cours → heure de début (ms). */
  readonly jobs = input<ReadonlyMap<string, number>>(new Map());
  /** Libellé du badge de génération, suivi du chronomètre. */
  readonly jobLabel = input('Examen en cours…');
  /** Libellé par cours, prioritaire sur jobLabel (« Examen + Flashcards en cours… »). */
  readonly jobLabels = input<ReadonlyMap<string, string>>(new Map());
  /** Examens en cours, si jobs contient aussi d'autres générations (null = jobs). */
  readonly examJobs = input<ReadonlyMap<string, number> | null>(null);
  /** Heure courante (ms), pour le chronomètre. */
  readonly now = input(0);

  readonly selectedChange = output<string | null>();
  readonly deleteCourse = output<string>();
  readonly generateExam = output<string>();

  /** Temps écoulé « m:ss » si une génération est en cours pour ce cours, sinon null. */
  protected elapsed(course: string): string | null {
    const startedAt = this.jobs().get(course);
    return startedAt === undefined ? null : formatElapsed((this.now() - startedAt) / 1000);
  }

  protected label(course: string): string {
    return this.jobLabels().get(course) ?? this.jobLabel();
  }

  /** Un examen est déjà en cours pour ce cours : le bouton « Générer un examen » est désactivé. */
  protected examRunning(course: string): boolean {
    return (this.examJobs() ?? this.jobs()).has(course);
  }

  protected select(course: string | null): void {
    if (course !== this.selected()) {
      this.selectedChange.emit(course);
    }
  }

  protected onDelete(course: string): void {
    const ok = confirm(
      `Supprimer le cours « ${course} » ?\nTous ses extraits indexés seront définitivement effacés.`,
    );
    if (ok) {
      this.deleteCourse.emit(course);
    }
  }
}
