import { Component, computed, input } from '@angular/core';
import { formatElapsed } from '../../../core/utils/exam.utils';
import { Icon } from '../icon/icon';

/**
 * Progression d'une longue génération (examen, flashcards, résumé), à la place d'un simple spinner.
 *
 * Le backend ne publie pas d'avancement réel : les étapes sont celles du générateur, et l'étape affichée est
 * estimée d'après le temps écoulé et la durée habituelle mesurée. L'interface le dit (« étape estimée »), ne
 * dépasse jamais 95 % et passe à « Finalisation » si la génération est plus longue que d'habitude.
 */
@Component({
  selector: 'app-step-progress',
  imports: [Icon],
  template: `
    <div class="progress" [class.progress--compact]="compact()">
      <div class="head">
        <p class="title">
          <span class="pulse" aria-hidden="true"></span>
          {{ title() }}
        </p>
        <p class="time tabular">
          <app-icon name="clock" [size]="14" />
          @if (showElapsed()) {
            {{ elapsedLabel() }} ·
          }
          {{ remainingLabel() }}
        </p>
      </div>
      <div
        class="bar"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        [attr.aria-valuenow]="percent()"
        [attr.aria-valuetext]="valueText()"
        [attr.aria-label]="title()"
      >
        <span class="bar__fill" [style.width.%]="percent()"></span>
      </div>
      @if (!compact()) {
        <ol class="steps">
          @for (step of steps(); track step; let i = $index) {
            <li class="step" [class.step--done]="i < current()" [class.step--now]="i === current()">
              <span class="step__mark" aria-hidden="true">
                @if (i < current()) {
                  <app-icon name="check" [size]="12" [stroke]="2.4" />
                } @else {
                  {{ i + 1 }}
                }
              </span>
              <span class="step__label">{{ step }}</span>
              @if (i === current()) {
                <span class="sr-only">(étape estimée en cours)</span>
              }
            </li>
          }
        </ol>
      } @else {
        <p class="current">Étape estimée : {{ steps()[current()] }}</p>
      }
      @if (note()) {
        <p class="note">{{ note() }}</p>
      }
    </div>
  `,
  styles: `
    .progress {
      display: grid;
      gap: var(--space-3);
      padding: var(--space-4);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
    }
    .progress--compact {
      gap: var(--space-2);
      padding: var(--space-3);
      box-shadow: none;
      background: var(--surface-alt);
      border-color: transparent;
    }
    .head {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-1) var(--space-3);
    }
    .title {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      margin: 0;
      font-weight: 600;
      font-size: var(--text-sm);
      color: var(--text);
    }
    .pulse {
      width: 0.5rem;
      height: 0.5rem;
      border-radius: 50%;
      background: var(--accent);
      animation: pulse 1.6s ease-in-out infinite;
    }
    @keyframes pulse {
      50% {
        opacity: 0.35;
      }
    }
    .time {
      display: inline-flex;
      align-items: center;
      gap: var(--space-1);
      margin: 0;
      font-size: var(--text-xs);
      color: var(--text-muted);
    }
    .bar {
      height: 6px;
      border-radius: var(--radius-pill);
      background: var(--chart-track);
      overflow: hidden;
    }
    .bar__fill {
      display: block;
      height: 100%;
      border-radius: inherit;
      background: var(--accent);
      transition: width var(--duration-slow) var(--ease);
    }
    .steps {
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
      gap: var(--space-2);
      margin: 0;
      padding: 0;
    }
    .step {
      display: flex;
      align-items: center;
      gap: var(--space-2);
      font-size: var(--text-xs);
      color: var(--text-muted);
      min-width: 0;
    }
    .step__mark {
      display: grid;
      place-items: center;
      flex: none;
      width: 1.35rem;
      height: 1.35rem;
      border-radius: 50%;
      border: 1px solid var(--border-strong);
      font-size: 0.68rem;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .step--done {
      color: var(--text);
    }
    .step--done .step__mark {
      border-color: var(--success);
      background: var(--success);
      color: var(--surface);
    }
    .step--now {
      color: var(--accent);
      font-weight: 600;
    }
    .step--now .step__mark {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--accent);
    }
    .current,
    .note {
      margin: 0;
      font-size: var(--text-xs);
      color: var(--text-muted);
    }
  `,
})
export class StepProgress {
  readonly title = input.required<string>();
  readonly steps = input.required<readonly string[]>();
  /** Début de la génération (ms) et heure courante (ms), fournie par le service qui suit la tâche. */
  readonly startedAt = input.required<number>();
  readonly now = input.required<number>();
  /** Durée habituelle, en secondes. */
  readonly estimateS = input.required<number>();
  readonly compact = input(false);
  readonly note = input('');
  /** Le titre affiche déjà le chronomètre (fil de l'Assistant) : on ne le répète pas. */
  readonly showElapsed = input(true);

  private readonly elapsed = computed(() => Math.max(0, (this.now() - this.startedAt()) / 1000));
  private readonly ratio = computed(() => this.elapsed() / Math.max(1, this.estimateS()));

  protected readonly percent = computed(() => Math.round(Math.min(0.95, this.ratio()) * 100));
  protected readonly current = computed(() =>
    Math.min(this.steps().length - 1, Math.floor(Math.min(this.ratio(), 0.999) * this.steps().length)),
  );
  protected readonly elapsedLabel = computed(() => `${formatElapsed(this.elapsed())} écoulé`);
  protected readonly remainingLabel = computed(() => {
    const left = this.estimateS() - this.elapsed();
    if (left <= 0) {
      return 'finalisation, encore quelques instants';
    }
    if (left < 60) {
      return "moins d'une minute restante";
    }
    const minutes = Math.round(left / 60);
    return `environ ${minutes} min restante${minutes > 1 ? 's' : ''}`;
  });
  protected readonly valueText = computed(
    () => `Étape estimée ${this.current() + 1} sur ${this.steps().length} : ${this.steps()[this.current()]}`,
  );
}
