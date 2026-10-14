import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { QuizPayload, QuizResultResponse } from '../../../../core/models/companion.models';
import { CompanionService } from '../../../../core/services/companion.service';
import { QuizCard } from './quiz-card';

const QUIZ: QuizPayload = {
  course: 'CNN',
  difficulty: 'facile',
  questions: [
    { question: 'Rôle du pooling ?', choices: ['Réduire la taille', 'Ajouter des poids', 'Normaliser', 'Mélanger'], answer: 'A', explanation: 'Le pooling réduit la taille des cartes.', page: 3, concept: 'Pooling' },
    { question: 'Que produit une convolution ?', choices: ['Un score', 'Des cartes d’activation', 'Une perte', 'Un gradient'], answer: 'B', explanation: 'Elle produit des cartes d’activation.', page: 4, concept: 'Convolution' },
  ],
  result: null,
};

async function render(quiz: QuizPayload = QUIZ) {
  const response$ = new Subject<QuizResultResponse>();
  const saveQuizResult = vi.fn(() => response$);
  TestBed.configureTestingModule({ providers: [{ provide: CompanionService, useValue: { saveQuizResult } }] });
  const fixture = TestBed.createComponent(QuizCard);
  fixture.componentRef.setInput('quiz', quiz);
  fixture.componentRef.setInput('messageId', 21);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const choices = (question: number) => [
    ...el.querySelectorAll('.question')[question].querySelectorAll<HTMLButtonElement>('button.choice'),
  ];
  return { fixture, el, choices, saveQuizResult, response$ };
}

describe('QuizCard', () => {
  it('affiche une question à la fois, corrige et explique après chaque réponse', async () => {
    const { fixture, el, choices } = await render();
    expect(el.querySelectorAll('.question')).toHaveLength(1);
    expect(el.textContent).toContain('2 questions · niveau facile');

    choices(0)[1].click(); // mauvaise réponse (B au lieu de A)
    await fixture.whenStable();
    const feedback = el.querySelector('.feedback');
    expect(feedback?.textContent).toContain('Pas tout à fait : la bonne réponse était A.');
    expect(feedback?.textContent).toContain('Le pooling réduit la taille des cartes.');
    expect(choices(0)[0].classList).toContain('choice--correct');
    expect(choices(0)[1].classList).toContain('choice--wrong');
    expect(choices(0).every((b) => b.disabled)).toBe(true);
    expect(el.querySelectorAll('.question')).toHaveLength(2); // question suivante affichée
    expect(el.querySelector('.quiz__count')?.textContent?.trim()).toBe('1/2');
  });

  it('enregistre le score à la dernière réponse', async () => {
    const { fixture, el, choices, saveQuizResult, response$ } = await render();
    choices(0)[0].click();
    await fixture.whenStable();
    choices(1)[1].click();
    await fixture.whenStable();

    expect(saveQuizResult).toHaveBeenCalledWith(21, ['A', 'B']);
    expect(el.querySelector('.score')?.textContent).toContain('Score : 2/2');
    expect(el.querySelector('.score')?.textContent).toContain('Enregistrement du score');

    // Le service met à jour la réponse affichée : le quiz devient « enregistré »
    const result = { answers: ['A', 'B'] as ('A' | 'B')[], correct: [true, true], score: 2, total: 2, submitted_at: '' };
    response$.next({ score: 2, total: 2, correct: [true, true], message: {} as never });
    fixture.componentRef.setInput('quiz', { ...QUIZ, result });
    await fixture.whenStable();
    expect(el.querySelector('.score')?.textContent).toContain('Score enregistré');
  });

  it('erreur d’enregistrement : message et bouton Réessayer', async () => {
    const { fixture, el, choices, saveQuizResult, response$ } = await render();
    choices(0)[0].click();
    await fixture.whenStable();
    choices(1)[0].click();
    await fixture.whenStable();
    response$.error(new Error('Backend injoignable'));
    await fixture.whenStable();
    expect(el.querySelector('.alert--error')?.textContent).toContain('Backend injoignable');
    expect(el.querySelector('.score')?.textContent).toContain('Score : 1/2');
    el.querySelector<HTMLButtonElement>('.score button')?.click();
    expect(saveQuizResult).toHaveBeenCalledTimes(2);
  });

  it('quiz déjà corrigé : réponses et score réaffichés, choix désactivés', async () => {
    const result = { answers: ['B', 'B'] as ('A' | 'B')[], correct: [false, true], score: 1, total: 2, submitted_at: '' };
    const { el, choices, saveQuizResult } = await render({ ...QUIZ, result });
    expect(el.querySelectorAll('.question')).toHaveLength(2);
    expect(choices(0)[1].classList).toContain('choice--wrong');
    expect(choices(1).every((b) => b.disabled)).toBe(true);
    expect(el.querySelector('.score')?.textContent).toContain('Score : 1/2');
    expect(el.querySelector('.score')?.textContent).toContain('Score enregistré');
    expect(saveQuizResult).not.toHaveBeenCalled();
  });
});
