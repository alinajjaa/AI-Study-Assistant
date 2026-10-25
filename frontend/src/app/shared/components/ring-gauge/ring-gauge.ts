import { Component, computed, input } from '@angular/core';

const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Jauge circulaire sobre pour un taux (0 à 1), aux couleurs de la palette ; « — » sans donnée. */
@Component({
  selector: 'app-ring-gauge',
  template: `
    <figure class="gauge">
      <svg viewBox="0 0 100 100" class="ring" aria-hidden="true" focusable="false">
        <circle class="ring__track" cx="50" cy="50" [attr.r]="radius" />
        @if (value() !== null) {
          <circle
            class="ring__value"
            cx="50"
            cy="50"
            [attr.r]="radius"
            [attr.stroke-dasharray]="circumference"
            [attr.stroke-dashoffset]="offset()"
          />
        }
      </svg>
      <span class="gauge__value tabular">{{ display() }}</span>
      <figcaption class="gauge__caption">
        <span class="gauge__label">{{ label() }}</span>
        @if (detail()) {
          <span class="gauge__detail">{{ detail() }}</span>
        }
      </figcaption>
    </figure>
  `,
  styles: `
    .gauge {
      position: relative;
      display: grid;
      justify-items: center;
      gap: var(--space-3);
      margin: 0;
      text-align: center;
    }
    .ring {
      width: 7.5rem;
      height: 7.5rem;
      transform: rotate(-90deg);
    }
    .ring__track {
      fill: none;
      stroke: var(--chart-track);
      stroke-width: 9;
    }
    .ring__value {
      fill: none;
      stroke: var(--chart-1);
      stroke-width: 9;
      stroke-linecap: round;
      transition: stroke-dashoffset var(--duration-slow) var(--ease);
    }
    .gauge__value {
      position: absolute;
      top: 3.75rem;
      left: 50%;
      transform: translate(-50%, -50%);
      font-family: var(--font-serif);
      font-size: var(--text-xl);
      font-weight: 600;
      color: var(--text);
    }
    .gauge__caption {
      display: grid;
      gap: 2px;
    }
    .gauge__label {
      font-weight: 600;
      font-size: var(--text-sm);
    }
    .gauge__detail {
      font-size: var(--text-xs);
      color: var(--text-muted);
    }
  `,
})
export class RingGauge {
  /** Taux entre 0 et 1, null sans donnée. */
  readonly value = input<number | null>(null);
  readonly label = input.required<string>();
  readonly detail = input('');

  protected readonly radius = RADIUS;
  protected readonly circumference = CIRCUMFERENCE;
  protected readonly offset = computed(() => CIRCUMFERENCE * (1 - Math.min(1, Math.max(0, this.value() ?? 0))));
  protected readonly display = computed(() => {
    const value = this.value();
    return value === null ? '—' : `${Math.round(value * 100)} %`;
  });
}
