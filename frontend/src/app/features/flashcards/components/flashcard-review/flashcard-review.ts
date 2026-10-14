import {
  Component,
  ElementRef,
  Injector,
  OnInit,
  afterNextRender,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { Flashcard } from '../../../../core/models/flashcard.models';
import { CardAnswer, ReviewSession } from '../../review-session';

/** Champs où les raccourcis clavier ne doivent pas s'appliquer. */
function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
  );
}

@Component({
  selector: 'app-flashcard-review',
  templateUrl: './flashcard-review.html',
  styleUrl: './flashcard-review.css',
  host: { '(document:keydown)': 'onKeydown($event)' },
})
export class FlashcardReview implements OnInit {
  private readonly injector = inject(Injector);
  private readonly cardRef = viewChild<ElementRef<HTMLElement>>('card');
  private readonly endTitleRef = viewChild<ElementRef<HTMLElement>>('endTitle');

  /** Paquet complet (instantané pris au début de la révision). */
  readonly cards = input.required<readonly Flashcard[]>();
  readonly course = input.required<string>();
  readonly exit = output<void>();
  /** Émis à chaque « Je savais » / « À revoir » : la page enregistre la révision. */
  readonly answered = output<{ card: Flashcard; known: boolean }>();

  /** Session créée une fois, puis réinitialisée par « Recommencer » / « Revoir ». */
  protected readonly session = new ReviewSession([]);
  /** Tour en cours : tout le paquet ou seulement les cartes à revoir. */
  protected readonly round = signal<'all' | 'missed'>('all');

  protected readonly progressPercent = computed(() => {
    const total = this.session.total();
    const done = this.session.finished() ? total : this.session.index();
    return total === 0 ? 0 : Math.round((done / total) * 100);
  });

  /** Annonce lue par les lecteurs d'écran (aria-live) à chaque changement de face ou de carte. */
  protected readonly announcement = computed(() => {
    const s = this.session;
    if (s.finished()) {
      return `Révision terminée : ${s.knownCount()} sur ${s.total()} cartes sues.`;
    }
    const card = s.current();
    if (!card) {
      return '';
    }
    const where = `Carte ${s.position()} sur ${s.total()}.`;
    return s.flipped()
      ? `Verso. ${where} Réponse : ${card.back} Page ${card.page}.`
      : `Recto. ${where} ${card.concept}. Question : ${card.front}`;
  });

  ngOnInit(): void {
    this.restart('all');
  }

  protected flip(): void {
    this.session.flip();
    this.focusCard();
  }

  protected answer(answer: CardAnswer): void {
    const card = this.session.current();
    if (card && this.session.flipped()) {
      this.answered.emit({ card, known: answer === 'known' });
    }
    this.session.answer(answer);
    this.focusCard();
  }

  protected next(): void {
    this.session.next();
    this.focusCard();
  }

  protected previous(): void {
    this.session.previous();
    this.focusCard();
  }

  /** « Recommencer tout le paquet » ou « Revoir les cartes à revoir ». */
  protected restart(round: 'all' | 'missed'): void {
    const cards = round === 'all' ? this.cards() : this.session.toReview();
    this.round.set(round);
    this.session.reset(cards);
    this.focusCard();
  }

  protected onKeydown(event: KeyboardEvent): void {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || isTyping(event.target)) {
      return;
    }
    // Une modale ouverte (examen…) garde ses propres raccourcis.
    if (document.querySelector('dialog[open]')) {
      return;
    }
    const onButton = event.target instanceof HTMLButtonElement;
    switch (event.key) {
      case ' ':
        // Sur un bouton, Espace l'active nativement.
        if (!onButton && !this.session.finished()) {
          event.preventDefault();
          this.flip();
        }
        break;
      case '1':
        if (this.session.flipped()) {
          event.preventDefault();
          this.answer('review');
        }
        break;
      case '2':
        if (this.session.flipped()) {
          event.preventDefault();
          this.answer('known');
        }
        break;
      case 'ArrowRight':
        if (!this.session.finished()) {
          event.preventDefault();
          this.next();
        }
        break;
      case 'ArrowLeft':
        event.preventDefault();
        this.previous();
        break;
    }
  }

  /** Après chaque action, le focus revient sur la carte (ou sur le titre de l'écran de fin). */
  private focusCard(): void {
    afterNextRender(
      () => (this.session.finished() ? this.endTitleRef() : this.cardRef())?.nativeElement.focus({ preventScroll: true }),
      { injector: this.injector },
    );
  }
}
