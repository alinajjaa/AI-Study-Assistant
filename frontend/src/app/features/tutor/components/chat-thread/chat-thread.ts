import { Component, ElementRef, afterRenderEffect, inject, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ChatMessage } from '../../../../core/models/tutor.models';
import { isCourseSummaryRequest } from '../../../../core/utils/summary.utils';
import { Loader } from '../../../../shared/components/loader/loader';
import { AnswerCard } from '../answer-card/answer-card';

@Component({
  selector: 'app-chat-thread',
  imports: [AnswerCard, Loader, RouterLink],
  templateUrl: './chat-thread.html',
  styleUrl: './chat-thread.css',
})
export class ChatThread {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly messages = input.required<ChatMessage[]>();
  /** Cours sélectionné (null = tous les cours), pour le lien « Résumer ce cours ». */
  readonly course = input<string | null>(null);
  /** Émis au clic sur une suggestion : la page pré-remplit le champ de saisie. */
  readonly suggestion = output<string>();

  /** Un résumé du cours entier n'est pas demandé au tuteur (3 passages) : lien vers la page Résumés. */
  protected readonly suggestions = [
    'Quelles sont les définitions importantes à retenir ?',
    'Explique-moi la notion la plus difficile avec un exemple.',
  ];

  protected readonly isCourseSummaryRequest = isCourseSummaryRequest;

  /** Paramètres du lien vers Résumés ; auto=course lance le résumé du cours entier. */
  protected summaryLink(course: string | null, auto: boolean): Record<string, string> {
    if (course === null) {
      return {};
    }
    return auto ? { course, auto: 'course' } : { course };
  }

  constructor() {
    // Garde le dernier échange visible à chaque nouvelle question ou réponse.
    afterRenderEffect(() => {
      if (this.messages().length === 0) {
        return;
      }
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const last = this.host.nativeElement.querySelector('.message:last-child');
      last?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
    });
  }
}
