import { Component, input, output } from '@angular/core';
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

  readonly selectedChange = output<string | null>();
  readonly deleteCourse = output<string>();

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
