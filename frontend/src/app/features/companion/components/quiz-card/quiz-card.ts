import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  linkedSignal,
  signal,
} from '@angular/core';
import { toMessage } from '../../../../core/interceptors/error.interceptor';
import { LETTERS, Letter, QuizPayload } from '../../../../core/models/companion.models';
import { CompanionService } from '../../../../core/services/companion.service';
import { Loader } from '../../../../shared/components/loader/loader';

const DIFFICULTY_LABELS: Readonly<Record<string, string>> = {
  facile: 'facile',
  moyen: 'moyen',
  difficile: 'difficile',
};

/**
 * Quiz interactif dans la discussion : une question à la fois, correction et explication après chaque réponse,
 * score final enregistré (POST /api/quiz-results) puis réaffiché à la réouverture de la conversation.
 */
@Component({
  selector: 'app-quiz-card',
  imports: [Loader],
  templateUrl: './quiz-card.html',
  styleUrl: './quiz-card.css',
})
export class QuizCard {
  private readonly companion = inject(CompanionService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly injector = inject(Injector);

  readonly quiz = input.required<QuizPayload>();
  /** Message « quiz » enregistré (null : score non enregistrable). */
  readonly messageId = input<number | null>(null);

  protected readonly letters = LETTERS;
  /** Réponse choisie pour chaque question (null = pas encore répondu). Quiz terminé : celles enregistrées. */
  protected readonly answers = linkedSignal<QuizPayload, (Letter | null)[]>({
    source: this.quiz,
    computation: (quiz, previous) =>
      quiz.result ? [...quiz.result.answers] : (previous?.value ?? quiz.questions.map(() => null)),
  });
  protected readonly saving = signal(false);
  protected readonly saveError = signal<string | null>(null);

  protected readonly total = computed(() => this.quiz().questions.length);
  protected readonly answered = computed(() => this.answers().filter((a) => a !== null).length);
  protected readonly score = computed(
    () => this.answers().filter((a, i) => a !== null && a === this.quiz().questions[i]?.answer).length,
  );
  protected readonly finished = computed(() => this.answered() === this.total());
  protected readonly saved = computed(() => this.quiz().result !== null);
  /** Questions affichées : celles déjà répondues et la suivante. */
  protected readonly visible = computed(() => Math.min(this.answered() + 1, this.total()));
  protected readonly difficulty = computed(() => DIFFICULTY_LABELS[this.quiz().difficulty] ?? this.quiz().difficulty);

  protected choose(index: number, letter: Letter): void {
    if (this.answers()[index] !== null || this.saved()) {
      return;
    }
    this.answers.update((list) => list.map((a, i) => (i === index ? letter : a)));
    if (this.finished()) {
      this.submit();
    } else {
      // Clavier : le focus passe au premier choix de la question suivante
      afterNextRender(
        () => this.host.nativeElement.querySelector<HTMLButtonElement>(`#${this.choiceId(index + 1, 0)}`)?.focus(),
        { injector: this.injector },
      );
    }
  }

  protected submit(): void {
    const id = this.messageId();
    const answers = this.answers();
    if (id === null || this.saving() || this.saved() || answers.some((a) => a === null)) {
      return;
    }
    this.saving.set(true);
    this.saveError.set(null);
    this.companion.saveQuizResult(id, answers as Letter[]).subscribe({
      next: () => this.saving.set(false),
      error: (err: unknown) => {
        this.saving.set(false);
        this.saveError.set(toMessage(err));
      },
    });
  }

  protected choiceState(index: number, letter: Letter): 'correct' | 'wrong' | 'idle' {
    const picked = this.answers()[index];
    if (picked === null) {
      return 'idle';
    }
    if (letter === this.quiz().questions[index].answer) {
      return 'correct';
    }
    return letter === picked ? 'wrong' : 'idle';
  }

  /** Identifiant unique d'un bouton de choix (plusieurs quiz peuvent être affichés dans le fil). */
  protected choiceId(question: number, choice: number): string {
    return `quiz-${this.messageId() ?? 'local'}-${question}-${choice}`;
  }
}
