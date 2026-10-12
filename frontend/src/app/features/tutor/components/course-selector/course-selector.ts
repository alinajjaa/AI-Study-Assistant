import { Component, input, output } from '@angular/core';
import { formatElapsed } from '../../../../core/utils/exam.utils';
import { Loader } from '../../../../shared/components/loader/loader';

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
  /** Générations d'examen en cours : cours → heure de début (ms). */
  readonly examJobs = input<ReadonlyMap<string, number>>(new Map());
  /** Heure courante (ms), pour le chronomètre. */
  readonly now = input(0);

  readonly selectedChange = output<string | null>();
  readonly deleteCourse = output<string>();
  readonly generateExam = output<string>();

  /** Temps écoulé « m:ss » si un examen est en cours pour ce cours, sinon null. */
  protected elapsed(course: string): string | null {
    const startedAt = this.examJobs().get(course);
    return startedAt === undefined ? null : formatElapsed((this.now() - startedAt) / 1000);
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
