import { Component, ElementRef, afterRenderEffect, inject, input, output } from '@angular/core';
import { CompanionProgress, toolLabel } from '../../../../core/models/companion.models';
import { AskResponse, ChatMessage, isOffCourse } from '../../../../core/models/tutor.models';
import { formatElapsed } from '../../../../core/utils/exam.utils';
import { ErrorState } from '../../../../shared/components/error-state/error-state';
import { Loader } from '../../../../shared/components/loader/loader';
import { StepProgress } from '../../../../shared/components/step-progress/step-progress';
import { CompanionReply } from '../companion-reply/companion-reply';

interface LongTask {
  steps: readonly string[];
  /** Durée habituelle mesurée (qwen2.5-7b sur GPU), en secondes. */
  estimateS: number;
}

const LONG_TASKS: Readonly<Record<string, LongTask>> = {
  generate_quiz: {
    steps: ['Choix de l’outil', 'Rédaction des questions', 'Vérification des réponses', 'Mise en forme'],
    estimateS: 75,
  },
  generate_flashcards: {
    steps: ['Repérage des notions', 'Rédaction des cartes', 'Vérification', 'Enregistrement du paquet'],
    estimateS: 120,
  },
  summarize: {
    steps: ['Lecture des parties', 'Résumé de chaque partie', 'Vue d’ensemble'],
    estimateS: 60,
  },
};

/** Fil du Study Companion : demandes de l'étudiant et réponses riches de l'assistant. */
@Component({
  selector: 'app-companion-thread',
  imports: [CompanionReply, Loader, StepProgress, ErrorState],
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
  /** « Renvoyer la demande » après une erreur : même question, même cours. */
  readonly retry = output<{ question: string; course: string | null }>();

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

  /** Génération longue (quiz, flashcards, résumé) : étapes habituelles et durée mesurée, sinon null. */
  protected longTask(message: ChatMessage): LongTask | null {
    const tool = this.progress().get(message.id)?.tool;
    return tool ? (LONG_TASKS[tool] ?? null) : null;
  }

  protected startedAt(message: ChatMessage): number {
    return this.progress().get(message.id)?.startedAt ?? this.now();
  }
}
