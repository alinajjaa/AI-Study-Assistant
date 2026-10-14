import {
  Component,
  ElementRef,
  afterRenderEffect,
  computed,
  input,
  model,
  output,
  viewChild,
} from '@angular/core';

const MAX_ROWS = 6;

@Component({
  selector: 'app-question-input',
  templateUrl: './question-input.html',
  styleUrl: './question-input.css',
})
export class QuestionInput {
  private readonly textarea = viewChild.required<ElementRef<HTMLTextAreaElement>>('textarea');

  /** Une question est en cours de traitement. */
  readonly loading = input(false);
  /** Cours ciblé, pour l'indication sous le champ (null = tous les cours). */
  readonly course = input<string | null>(null);
  /** Texte saisi ; en model() pour que la page puisse le pré-remplir (suggestions). */
  readonly text = model('');
  /** Libellé (lu par les lecteurs d'écran) et texte indicatif du champ. */
  readonly label = input('Ta question');
  readonly placeholder = input('Pose ta question sur le cours…');
  /** Indication quand aucun cours n'est choisi (l'assistant cherche alors dans tous les cours). */
  readonly noCourseLabel = input('tous les cours');

  readonly ask = output<string>();

  protected readonly length = computed(() => this.text().trim().length);
  protected readonly canSend = computed(() => this.length() > 0 && !this.loading());

  constructor() {
    // Agrandit le champ avec son contenu, jusqu'à MAX_ROWS lignes.
    afterRenderEffect(() => {
      this.text();
      const el = this.textarea().nativeElement;
      const style = getComputedStyle(el);
      const lineHeight = parseFloat(style.lineHeight) || 24;
      const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
      const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
      const max = lineHeight * MAX_ROWS + padding + border;

      el.style.height = 'auto';
      const needed = el.scrollHeight + border;
      el.style.height = `${Math.min(needed, max)}px`;
      el.style.overflowY = needed > max ? 'auto' : 'hidden';
    });
  }

  focus(): void {
    const el = this.textarea().nativeElement;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }

  protected onInput(event: Event): void {
    this.text.set((event.target as HTMLTextAreaElement).value);
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      this.send();
    }
  }

  protected send(): void {
    if (!this.canSend()) {
      return;
    }
    this.ask.emit(this.text().trim());
    this.text.set('');
  }
}
