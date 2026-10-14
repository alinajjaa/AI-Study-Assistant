import { Component, computed, input, model } from '@angular/core';
import { Source } from '../../../../core/models/tutor.models';

/** Une page citée : on garde l'extrait le plus pertinent parmi ses chunks. */
interface PageSource {
  key: string;
  page: number;
  course: string;
  excerpt: string;
  percent: number;
}

@Component({
  selector: 'app-sources-list',
  templateUrl: './sources-list.html',
  styleUrl: './sources-list.css',
})
export class SourcesList {
  private static nextId = 0;
  protected readonly panelId = `excerpt-panel-${SourcesList.nextId++}`;

  readonly sources = input.required<Source[]>();
  /** Page dont l'extrait est déplié (partagée avec les puces [p.X] de la réponse). */
  readonly activePage = model<number | null>(null);

  /** Sources dédoublonnées par cours + page, triées par numéro de page. */
  protected readonly pages = computed<PageSource[]>(() => {
    const best = new Map<string, Source>();
    for (const source of this.sources()) {
      const key = `${source.course}|${source.page}`;
      const current = best.get(key);
      if (!current || source.score > current.score) {
        best.set(key, source);
      }
    }
    return [...best.entries()]
      .map(([key, s]) => ({
        key,
        page: s.page,
        course: s.course,
        excerpt: s.excerpt,
        percent: Math.round(Math.min(Math.max(s.score, 0), 1) * 100),
      }))
      .sort((a, b) => a.page - b.page || a.course.localeCompare(b.course));
  });

  /** Plusieurs cours cités (mode « Tous les cours ») : on affiche le cours dans chaque badge. */
  protected readonly multiCourse = computed(() => new Set(this.pages().map((p) => p.course)).size > 1);

  protected readonly openPages = computed(() => {
    const page = this.activePage();
    return page === null ? [] : this.pages().filter((p) => p.page === page);
  });

  protected toggle(page: number): void {
    this.activePage.update((current) => (current === page ? null : page));
  }

  protected close(): void {
    this.activePage.set(null);
  }
}
