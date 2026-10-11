import { Component, ElementRef, afterRenderEffect, inject, input, output } from '@angular/core';
import { ChatMessage } from '../../../../core/models/tutor.models';
import { Loader } from '../../../../shared/components/loader/loader';
import { AnswerCard } from '../answer-card/answer-card';

@Component({
  selector: 'app-chat-thread',
  imports: [AnswerCard, Loader],
  templateUrl: './chat-thread.html',
  styleUrl: './chat-thread.css',
})
export class ChatThread {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly messages = input.required<ChatMessage[]>();
  /** Émis au clic sur une suggestion : la page pré-remplit le champ de saisie. */
  readonly suggestion = output<string>();

  protected readonly suggestions = [
    'Résume les idées principales de ce cours.',
    'Quelles sont les définitions importantes à retenir ?',
    'Explique-moi la notion la plus difficile avec un exemple.',
  ];

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
