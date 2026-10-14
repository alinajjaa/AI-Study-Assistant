import { Component, ElementRef, afterRenderEffect, inject, input, output } from '@angular/core';
import { CompanionProgress, toolLabel } from '../../../../core/models/companion.models';
import { AskResponse, ChatMessage, isOffCourse } from '../../../../core/models/tutor.models';
import { formatElapsed } from '../../../../core/utils/exam.utils';
import { Loader } from '../../../../shared/components/loader/loader';
import { CompanionReply } from '../companion-reply/companion-reply';

/** Fil du Study Companion : demandes de l'étudiant et réponses riches de l'assistant. */
@Component({
  selector: 'app-companion-thread',
  imports: [CompanionReply, Loader],
  templateUrl: './companion-thread.html',
  styleUrl: './companion-thread.css',
})
export class CompanionThread {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  readonly messages = input.required<ChatMessage[]>();
  /** Message en attente → outil en cours (indicateur « L'assistant travaille… »). */
  readonly progress = input<ReadonlyMap<number, CompanionProgress>>(new Map());
  /** Heure courante (ms), pour le chronomètre. */
  readonly now = input(0);
  /** L'étudiant a choisi le cours demandé : la page le sélectionne et renvoie la demande. */
  readonly chooseCourse = output<{ course: string; question: string }>();

  constructor() {
    // Garde le dernier échange visible à chaque nouvelle demande ou réponse.
    afterRenderEffect(() => {
      if (this.messages().length === 0) {
        return;
      }
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const last = this.host.nativeElement.querySelector('.message:last-child .student');
      last?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    });
  }

  /** « L'assistant génère ton quiz… 0:42 » */
  protected working(message: ChatMessage): string {
    const progress = this.progress().get(message.id);
    const action = toolLabel(progress?.tool ?? null);
    const text = action ? `L'assistant ${action}…` : "L'assistant travaille…";
    return progress ? `${text} ${formatElapsed(Math.max(0, (this.now() - progress.startedAt) / 1000))}` : text;
  }

  /** Réponse « Hors du cours » : aucun contenu supplémentaire n'est affiché sous la mention. */
  protected extras(message: ChatMessage): AskResponse[] {
    return message.response && isOffCourse(message.response) ? [] : (message.extra ?? []);
  }

  /** Les générations longues peuvent prendre quelques minutes : on le dit pendant l'attente. */
  protected isLong(message: ChatMessage): boolean {
    const tool = this.progress().get(message.id)?.tool;
    return tool === 'generate_quiz' || tool === 'generate_flashcards' || tool === 'summarize';
  }
}
