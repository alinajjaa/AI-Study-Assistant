import { Component, computed, input, output } from '@angular/core';
import { Summary } from '../../../../core/models/summary.models';
import { BulletPart, formatPages, splitPageRefs } from '../../../../core/utils/summary.utils';

const DATE_FORMAT = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });

/** Un résumé : vue d'ensemble, puis sections repliables avec leurs références de pages. */
@Component({
  selector: 'app-summary-view',
  templateUrl: './summary-view.html',
  styleUrl: './summary-view.css',
})
export class SummaryView {
  readonly summary = input.required<Summary>();
  /** Une régénération est en cours pour ce cours (bouton désactivé). */
  readonly regenerating = input(false);
  readonly regenerate = output<void>();

  protected readonly title = computed(() => {
    const s = this.summary();
    return s.mode === 'course' ? `Résumé du cours « ${s.course} »` : `Explication : « ${s.topic} »`;
  });
  protected readonly date = computed(() => DATE_FORMAT.format(new Date(this.summary().created_at)));

  protected readonly formatPages = formatPages;

  protected parts(bullet: string): BulletPart[] {
    return splitPageRefs(bullet);
  }
}
