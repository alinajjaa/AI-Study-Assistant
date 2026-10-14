import { Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { levelLabel } from '../../../../core/models/auth.models';
import { ProgressPayload } from '../../../../core/models/companion.models';
import { WeakPoint, formatPercent } from '../../../../core/models/profile.models';

/** Carte de progression : niveau, statistiques (flashcards et quiz), points faibles. */
@Component({
  selector: 'app-progress-card',
  imports: [RouterLink],
  templateUrl: './progress-card.html',
  styleUrl: './progress-card.css',
})
export class ProgressCard {
  readonly progress = input.required<ProgressPayload>();

  protected readonly percent = formatPercent;
  protected readonly level = computed(() => levelLabel(this.progress().level));
  protected readonly suggestion = computed(() => {
    const s = this.progress().level_suggestion;
    return s ? `${s.direction === 'up' ? 'Tu pourrais passer' : 'Tu pourrais revenir'} au niveau ${levelLabel(s.level).toLowerCase()}.` : null;
  });

  protected rate(rate: number | null): string {
    return rate === null ? '—' : formatPercent(rate);
  }

  protected weakLabel(point: WeakPoint): string {
    return `${formatPercent(point.to_review_rate)} à revoir sur ${point.reviews} essai${point.reviews > 1 ? 's' : ''}`;
  }
}
