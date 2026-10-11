import { Component, input } from '@angular/core';

/** Indicateur de chargement réutilisable : spinner, ou trois points pour « le tuteur réfléchit ». */
@Component({
  selector: 'app-loader',
  template: `
    @if (variant() === 'dots') {
      <span class="dots" aria-hidden="true"><span></span><span></span><span></span></span>
    } @else {
      <span class="spinner" [class.spinner--sm]="size() === 'sm'" aria-hidden="true"></span>
    }
    @if (label()) {
      <span class="label">{{ label() }}</span>
    } @else {
      <span class="sr-only">Chargement</span>
    }
  `,
  styleUrl: './loader.css',
  host: { role: 'status' },
})
export class Loader {
  readonly label = input('');
  readonly size = input<'sm' | 'md'>('md');
  readonly variant = input<'spinner' | 'dots'>('spinner');
}
