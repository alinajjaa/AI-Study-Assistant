import { Component, inject, input, output } from '@angular/core';
import { formatElapsed } from '../../../core/utils/exam.utils';
import { ConfirmService } from '../confirm-dialog/confirm.service';
import { RouterLink } from '@angular/router';
import { EmptyState } from '../empty-state/empty-state';
import { Icon } from '../icon/icon';
import { Loader } from '../loader/loader';
import { Skeleton } from '../skeleton/skeleton';

/** Liste « Mes cours », partagée par l'Assistant, les flashcards et les résumés. */
@Component({
  selector: 'app-course-selector',
  imports: [Loader, EmptyState, Icon, RouterLink, Skeleton],
  templateUrl: './course-selector.html',
  styleUrl: './course-selector.css',
})
export class CourseSelector {
  private readonly confirm = inject(ConfirmService);

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
  /**
   * Aucun cours : « import » affiche un bouton qui ouvre le choix du PDF (Assistant, émet importRequested) ;
   * « link » renvoie vers l'Assistant (pages Flashcards et Résumés).
   */
  readonly emptyAction = input<'import' | 'link'>('link');

  readonly selectedChange = output<string | null>();
  readonly deleteCourse = output<string>();
  readonly generateExam = output<string>();
  readonly importRequested = output<void>();

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
    this.confirm
      .ask({
        title: `Supprimer le cours « ${course} » ?`,
        message: 'Tous ses extraits indexés seront définitivement effacés.',
        confirmLabel: 'Supprimer le cours',
        danger: true,
      })
      .subscribe((ok) => {
        if (ok) {
          this.deleteCourse.emit(course);
        }
      });
  }
}
