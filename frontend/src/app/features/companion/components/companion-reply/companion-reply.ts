import { Component, computed, input, output } from '@angular/core';
import { marked } from 'marked';
import {
  FlashcardsPayload,
  ProgressPayload,
  QuizPayload,
  SummaryPayload,
  TextPayload,
} from '../../../../core/models/companion.models';
import { AskResponse } from '../../../../core/models/tutor.models';
import { SummaryView } from '../../../summaries/components/summary-view/summary-view';
import { AnswerCard } from '../answer-card/answer-card';
import { FlashcardsCard } from '../flashcards-card/flashcards-card';
import { ProgressCard } from '../progress-card/progress-card';
import { QuizCard } from '../quiz-card/quiz-card';

/** Une réponse de l'assistant, affichée selon son type : texte, réponse sourcée, résumé, quiz, flashcards, progrès. */
@Component({
  selector: 'app-companion-reply',
  imports: [AnswerCard, SummaryView, QuizCard, FlashcardsCard, ProgressCard],
  templateUrl: './companion-reply.html',
  styleUrl: './companion-reply.css',
})
export class CompanionReply {
  readonly response = input.required<AskResponse>();
  /** L'étudiant choisit le cours demandé par l'assistant. */
  readonly chooseCourse = output<string>();

  protected readonly kind = computed(() => this.response().kind ?? 'answer');
  /** Texte de l'assistant (markdown), nettoyé ensuite par la sanitization d'Angular ([innerHTML]). */
  protected readonly html = computed(() =>
    marked.parse(this.response().answer, { async: false, gfm: true, breaks: true }),
  );
  protected readonly courseChoices = computed(
    () => (this.response().payload as TextPayload | null)?.course_choices ?? [],
  );

  protected quiz(): QuizPayload {
    return this.response().payload as QuizPayload;
  }

  protected summary(): SummaryPayload {
    return this.response().payload as SummaryPayload;
  }

  protected deck(): FlashcardsPayload {
    return this.response().payload as FlashcardsPayload;
  }

  protected progress(): ProgressPayload {
    return this.response().payload as ProgressPayload;
  }
}
