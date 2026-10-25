import { Component, ElementRef, Injector, afterNextRender, computed, inject, input, output, signal } from '@angular/core';
import { Icon } from '../../../../shared/components/icon/icon';
import { courseInitial, courseTint } from '../../../../shared/utils/course-avatar';

/**
 * Choix du cours dans la zone de saisie : chip « Tous les cours ▾ » qui ouvre un menu (tous les cours, chaque
 * cours, « Importer un PDF »). Clavier : flèches, Début/Fin, Échap (rend le focus à la chip), Tab ferme le menu.
 */
@Component({
  selector: 'app-course-picker',
  imports: [Icon],
  templateUrl: './course-picker.html',
  styleUrl: './course-picker.css',
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(keydown.escape)': 'onEscape($event)',
  },
})
export class CoursePicker {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  readonly courses = input.required<string[]>();
  /** Cours sélectionné, null = tous les cours. */
  readonly selected = input<string | null>(null);
  readonly loading = input(false);

  readonly selectedChange = output<string | null>();
  readonly importRequested = output<void>();

  protected readonly open = signal(false);
  /** Ouvert par un clic ailleurs (« Examen ») : ce même clic, arrivé au document, ne doit pas le refermer. */
  private openingClick = false;
  protected readonly label = computed(() => (this.loading() && this.courses().length === 0 ? 'Chargement…' : (this.selected() ?? 'Tous les cours')));
  protected readonly initial = courseInitial;
  protected readonly tint = courseTint;

  /** Ouvre le menu et place le focus sur le cours sélectionné (« Examen » sans cours choisi). */
  openMenu(): void {
    if (!this.open()) {
      this.open.set(true);
      this.openingClick = true;
      setTimeout(() => (this.openingClick = false));
    }
    afterNextRender(
      () => {
        const items = this.items();
        (items.find((item) => item.getAttribute('aria-checked') === 'true') ?? items[0])?.focus();
      },
      { injector: this.injector },
    );
  }

  protected toggle(): void {
    if (this.open()) {
      this.close(false);
    } else {
      this.openMenu();
    }
  }

  protected choose(course: string | null): void {
    this.close(true);
    if (course !== this.selected()) {
      this.selectedChange.emit(course);
    }
  }

  protected importPdf(): void {
    this.close(true);
    this.importRequested.emit();
  }

  protected onMenuKeydown(event: KeyboardEvent): void {
    const items = this.items();
    const index = items.indexOf(document.activeElement as HTMLElement);
    let next: HTMLElement | undefined;
    if (event.key === 'ArrowDown') {
      next = items[(index + 1) % items.length];
    } else if (event.key === 'ArrowUp') {
      next = items[(index - 1 + items.length) % items.length];
    } else if (event.key === 'Home') {
      next = items[0];
    } else if (event.key === 'End') {
      next = items[items.length - 1];
    } else if (event.key === 'Tab') {
      this.close(false);
      return;
    }
    if (next) {
      event.preventDefault();
      next.focus();
    }
  }

  protected onEscape(event: Event): void {
    if (this.open()) {
      event.stopPropagation();
      this.close(true);
    }
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.openingClick && !this.host.nativeElement.contains(event.target as Node)) {
      this.close(false);
    }
  }

  private close(refocus: boolean): void {
    this.open.set(false);
    if (refocus) {
      this.host.nativeElement.querySelector<HTMLButtonElement>('.chip')?.focus();
    }
  }

  private items(): HTMLElement[] {
    return [...this.host.nativeElement.querySelectorAll<HTMLElement>('[role^="menuitem"]')];
  }
}
