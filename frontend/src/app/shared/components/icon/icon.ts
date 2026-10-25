import { Component, computed, input } from '@angular/core';

/** Tracés (viewBox 24, trait 1,8) des icônes de l'interface. Décoratives : toujours accompagnées d'un texte. */
const ICONS = {
  chat: ['M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9a1.5 1.5 0 0 1-1.5 1.5H9l-5 4z', 'M8 9h8M8 12h5'],
  cards: ['M4 7.5A1.5 1.5 0 0 1 5.5 6h10A1.5 1.5 0 0 1 17 7.5v11a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 4 18.5z', 'M8 3h10.5A1.5 1.5 0 0 1 20 4.5V16'],
  summary: ['M6 3h9l4 4v14H6z', 'M14 3v5h5', 'M9 12h7M9 15.5h7M9 9h3'],
  exam: ['M9 4H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2h-2', 'M9 3h6v3H9z', 'm9 14 2 2 4-4.5'],
  chart: ['M4 20h16', 'M7 16v-5', 'M12 16V6', 'M17 16v-8'],
  book: ['M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z', 'M4 20.5A2.5 2.5 0 0 0 6.5 23H20', 'M8 7h8M8 11h5'],
  upload: ['M12 15V4', 'm7 9 5-5 5 5', 'M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3'],
  check: ['m5 12.5 4.5 4.5L19 7'],
  alert: ['M12 3.5 2.5 20h19z', 'M12 10v4.5', 'M12 17.5h.01'],
  error: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M12 7.5v5.5', 'M12 16.5h.01'],
  retry: ['M20 11a8 8 0 1 0-2.3 5.7', 'M20 4v7h-7'],
  sun: ['M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z', 'M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4'],
  moon: ['M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z'],
  logout: ['M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3', 'M10 17l-5-5 5-5', 'M5 12h11'],
  shield: ['M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z', 'm9 12 2 2 4-4'],
  clock: ['M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z', 'M12 8v4.5l3 1.8'],
  spark: ['M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4z', 'M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z'],
  trash: ['M4 7h16', 'M10 11v6M14 11v6', 'm6 7 1 13h10l1-13', 'M9 7V4h6v3'],
  copy: ['M9 9h11v11H9z', 'M5 15V6a2 2 0 0 1 2-2h9'],
  close: ['M6 6l12 12M18 6 6 18'],
  arrow: ['M5 12h14', 'm13 6 6 6-6 6'],
  sidebar: ['M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z', 'M9.5 4v16'],
  plus: ['M12 5v14M5 12h14'],
  chevron: ['m6 9 6 6 6-6'],
  quiz: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14', 'M12 17h.01'],
  search: ['M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z', 'm20 20-3.5-3.5'],
  courses: ['M4 6.5 12 3l8 3.5-8 3.5z', 'm4 11.5 8 3.5 8-3.5', 'm4 16.5 8 3.5 8-3.5'],
} as const;

export type IconName = keyof typeof ICONS;

@Component({
  selector: 'app-icon',
  template: `
    <svg
      [attr.width]="size()"
      [attr.height]="size()"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      [attr.stroke-width]="stroke()"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      @for (d of paths(); track $index) {
        <path [attr.d]="d" />
      }
    </svg>
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-shrink: 0;
      line-height: 0;
    }
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
  readonly size = input(18);
  readonly stroke = input(1.8);
  protected readonly paths = computed(() => ICONS[this.name()]);
}
