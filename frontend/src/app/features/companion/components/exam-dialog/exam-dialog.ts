import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  afterRenderEffect,
  computed,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import {
  COMPLETE_EXAM_PARTS,
  DEFAULT_EXAM_OPTIONS,
  DIFFICULTIES,
  Difficulty,
  EXAM_FORMATS,
  EXAM_TOTAL_POINTS,
  ExamFormat,
  ExamOptions,
  QUESTION_COUNTS,
  QuestionCount,
} from '../../../../core/models/exam.models';
import { loadExamOptions, saveExamOptions } from '../../../../core/utils/exam-options.storage';
import { handleRadioKeydown } from '../../../../shared/utils/radio-group';
import { estimateExamMinutes, formatPoints, pointsPerQuestion } from '../../../../core/utils/exam.utils';

/** Éléments atteignables avec Tab (les radios non cochées ont tabindex=-1). */
function tabbables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>('button, input, [tabindex]')].filter(
    (el) => el.tabIndex >= 0 && !el.hasAttribute('disabled'),
  );
}

@Component({
  selector: 'app-exam-dialog',
  templateUrl: './exam-dialog.html',
  styleUrl: './exam-dialog.css',
})
export class ExamDialog {
  private readonly injector = inject(Injector);
  private readonly dialogRef = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private opener: HTMLElement | null = null;
  private pressStartedOnBackdrop = false;

  /** Cours pour lequel la modale est ouverte (null = fermée). */
  readonly course = input<string | null>(null);
  readonly generate = output<ExamOptions>();
  readonly closed = output<void>();

  protected readonly formats = EXAM_FORMATS;
  protected readonly parts = COMPLETE_EXAM_PARTS;
  protected readonly counts = QUESTION_COUNTS;
  protected readonly difficulties = DIFFICULTIES;
  protected readonly format = signal<ExamFormat>(DEFAULT_EXAM_OPTIONS.format);
  protected readonly numQuestions = signal<QuestionCount>(DEFAULT_EXAM_OPTIONS.numQuestions);
  protected readonly difficulty = signal<Difficulty>(DEFAULT_EXAM_OPTIONS.difficulty);
  protected readonly includeAnswers = signal(DEFAULT_EXAM_OPTIONS.includeAnswers);
  protected readonly minutes = computed(() =>
    estimateExamMinutes({ format: this.format(), numQuestions: this.numQuestions() }),
  );
  /** Barème du QCM rapide, en direct : « 10 questions × 2 pts = 20 pts ». */
  protected readonly scale = computed(() => {
    const n = this.numQuestions();
    return `${n} questions × ${formatPoints(pointsPerQuestion(n))} pts = ${EXAM_TOTAL_POINTS} pts`;
  });

  protected readonly setFormat = (option: (typeof EXAM_FORMATS)[number]): void => this.format.set(option.value);
  protected readonly setCount = (value: QuestionCount): void => this.numQuestions.set(value);
  protected readonly setDifficulty = (value: Difficulty): void => this.difficulty.set(value);
  protected readonly setLevel = (level: (typeof DIFFICULTIES)[number]): void => this.difficulty.set(level.value);

  constructor() {
    // Synchronise l'état ouvert/fermé du <dialog> natif avec l'input course.
    afterRenderEffect(() => {
      const course = this.course();
      const dialog = this.dialogRef().nativeElement;
      untracked(() => {
        if (course !== null && !dialog.open) {
          this.open(dialog);
        } else if (course === null && dialog.open) {
          dialog.close();
        }
      });
    });
  }

  protected onToggleAnswers(event: Event): void {
    this.includeAnswers.set((event.target as HTMLInputElement).checked);
  }

  protected submit(): void {
    const options: ExamOptions = {
      format: this.format(),
      numQuestions: this.numQuestions(),
      difficulty: this.difficulty(),
      includeAnswers: this.includeAnswers(),
    };
    saveExamOptions(options);
    this.generate.emit(options);
    this.dialogRef().nativeElement.close();
  }

  protected cancel(): void {
    this.dialogRef().nativeElement.close();
  }

  /** Événement natif "close" : Annuler, Générer, Échap ou clic sur le fond. */
  protected onClose(): void {
    this.closed.emit();
    this.restoreFocus();
  }

  /** Flèches, Début, Fin : déplace la sélection dans un groupe de boutons radio. */
  protected readonly onRadioKeydown = handleRadioKeydown;

  /** Piège le focus : Tab et Maj+Tab bouclent à l'intérieur de la modale. */
  protected onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') {
      return;
    }
    const items = tabbables(this.dialogRef().nativeElement);
    if (items.length === 0) {
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  /** Le clic sur le fond ne ferme que s'il a commencé ET fini sur le fond. */
  protected onMouseDown(event: MouseEvent): void {
    this.pressStartedOnBackdrop = event.target === this.dialogRef().nativeElement;
  }

  protected onMouseUp(event: MouseEvent): void {
    const endedOnBackdrop = event.target === this.dialogRef().nativeElement;
    if (this.pressStartedOnBackdrop && endedOnBackdrop) {
      this.cancel();
    }
    this.pressStartedOnBackdrop = false;
  }

  private open(dialog: HTMLDialogElement): void {
    this.opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const saved = loadExamOptions();
    this.format.set(saved.format);
    this.numQuestions.set(saved.numQuestions);
    this.difficulty.set(saved.difficulty);
    this.includeAnswers.set(saved.includeAnswers);
    dialog.showModal();
    // Focus initial sur le type d'examen sélectionné, une fois les tabindex à jour.
    afterNextRender(
      () => dialog.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]')?.focus(),
      { injector: this.injector },
    );
  }

  /** Rend le focus au bouton d'origine ; s'il a été désactivé, au nom du cours sur la même ligne. */
  private restoreFocus(): void {
    const opener = this.opener;
    this.opener = null;
    if (!opener) {
      return;
    }
    afterNextRender(
      () => {
        if (opener.isConnected && !opener.hasAttribute('disabled')) {
          opener.focus();
          return;
        }
        opener.closest('li')?.querySelector<HTMLElement>('button:not([disabled])')?.focus();
      },
      { injector: this.injector },
    );
  }
}
