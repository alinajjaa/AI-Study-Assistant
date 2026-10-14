import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CompanionProgress, FlashcardsPayload, ProgressPayload } from '../../../../core/models/companion.models';
import { ChatMessage } from '../../../../core/models/tutor.models';
import { CompanionService } from '../../../../core/services/companion.service';
import { CompanionThread } from './companion-thread';

function message(response: ChatMessage['response'], extra?: ChatMessage['extra']): ChatMessage {
  return { id: 1, question: 'Ma demande', course: 'CNN', status: 'done', response, error: null, extra };
}

const DECK: FlashcardsPayload = { deck_id: 7, course: 'CNN', card_count: 10, concepts: ['Pooling', 'Convolution'] };
const PROGRESS: ProgressPayload = {
  level: 'intermediaire',
  stats: { courses: 2, questions: 5, exams: 1, cards_reviewed: 12, known_rate: 0.75 },
  quiz: { answers: 4, correct_rate: 0.5 },
  weak_points: [{ course: 'CNN', concept: 'Pooling', reviews: 3, to_review_rate: 0.67 }],
  level_suggestion: null,
};

async function render(messages: ChatMessage[], progress = new Map<number, CompanionProgress>(), now = 0) {
  TestBed.configureTestingModule({
    providers: [provideRouter([]), { provide: CompanionService, useValue: { saveQuizResult: vi.fn() } }],
  });
  const fixture = TestBed.createComponent(CompanionThread);
  fixture.componentRef.setInput('messages', messages);
  fixture.componentRef.setInput('progress', progress);
  fixture.componentRef.setInput('now', now);
  await fixture.whenStable();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('CompanionThread', () => {
  it('fil vide : invitation à demander', async () => {
    const { el } = await render([]);
    expect(el.textContent).toContain('Que veux-tu faire aujourd');
  });

  it('demande longue en cours : « L’assistant génère ton quiz… » avec chronomètre', async () => {
    const pending: ChatMessage = { id: -1, question: 'Un quiz', course: 'CNN', status: 'pending', response: null, error: null };
    const { el } = await render([pending], new Map([[-1, { tool: 'generate_quiz', startedAt: 0 }]]), 42_000);
    expect(el.querySelector('.working')?.textContent).toContain('L\'assistant génère ton quiz… 0:42');
    expect(el.querySelector('.working')?.textContent).toContain('1 à 3 minutes');
  });

  it('réponse sourcée : carte du tuteur avec les pages', async () => {
    const { el } = await render([
      message({ answer: 'Le pooling réduit [p.3].', kind: 'answer', sources: [{ course: 'CNN', page: 3, score: 0.9, excerpt: '…' }] }),
    ]);
    expect(el.querySelector('app-answer-card')).not.toBeNull();
    expect(el.querySelector('.page-ref')?.textContent).toBe('p.3');
  });

  it('flashcards et progression : cartes dédiées, plusieurs réponses pour une demande', async () => {
    const { el } = await render([
      message(
        { answer: 'Ton paquet est prêt !', kind: 'flashcards', payload: DECK, sources: [], messageId: 2 },
        [{ answer: 'Voici tes progrès.', kind: 'progress', payload: PROGRESS, sources: [], messageId: 3 }],
      ),
    ]);
    expect(el.querySelector('.deck__title')?.textContent).toContain('Paquet de 10 flashcards prêt');
    expect(el.querySelector('.deck__action')?.getAttribute('href')).toBe('/flashcards?course=CNN&deck=7');
    const progress = el.querySelector('app-progress-card')?.textContent ?? '';
    expect(progress).toContain('Niveau Intermédiaire');
    expect(progress).toContain('Quiz réussis');
    expect(progress).toContain('50 %');
    expect(progress).toContain('Pooling');
  });

  it('résumé : réutilise la vue des résumés, sans bouton Régénérer', async () => {
    const summary = {
      id: 4, course: 'CNN', mode: 'course', topic: null, created_at: '2026-10-14T10:00:00Z', cached: true,
      content: { found: true, overview: 'Vue d’ensemble du cours.', sections: [{ title: 'Pooling', pages: [3], bullets: ['Réduit la taille [p.3]'] }] },
    };
    const { el } = await render([message({ answer: 'Voici le résumé.', kind: 'summary', payload: summary, sources: [] })]);
    expect(el.querySelector('app-summary-view')?.textContent).toContain('Résumé du cours « CNN »');
    expect(el.querySelector('.section__title')?.textContent).toBe('Pooling');
    expect([...el.querySelectorAll('button')].some((b) => b.textContent?.includes('Régénérer'))).toBe(false);
  });

  it('« quel cours ? » : un bouton par cours renvoie la demande avec ce cours', async () => {
    const { fixture, el } = await render([
      message({ answer: 'Sur quel cours veux-tu travailler ?', kind: 'text', payload: { course_choices: ['CNN', 'Docker'] }, sources: [] }),
    ]);
    const chosen: unknown[] = [];
    fixture.componentInstance.chooseCourse.subscribe((e) => chosen.push(e));
    const buttons = [...el.querySelectorAll<HTMLButtonElement>('.choices button')];
    expect(buttons.map((b) => b.textContent?.trim())).toEqual(['CNN', 'Docker']);
    buttons[1].click();
    expect(chosen).toEqual([{ course: 'Docker', question: 'Ma demande' }]);
  });

  it('bug c : sous une réponse « Hors du cours », aucun contenu supplémentaire ni sources', async () => {
    const { el } = await render([
      message(
        { answer: 'Cette information n’est pas présente dans le cours. Voici quand même…', kind: 'answer', sources: [], answered: false },
        [{ answer: 'Voici tes progrès.', kind: 'progress', payload: PROGRESS, sources: [], messageId: 3 }],
      ),
    ]);
    expect(el.querySelectorAll('app-companion-reply')).toHaveLength(1);
    expect(el.querySelector('.tag--off')?.textContent).toContain('Hors du cours');
    expect(el.querySelector('app-progress-card')).toBeNull();
    expect(el.querySelector('app-sources-list')).toBeNull();
    expect(el.textContent).not.toContain('Voici quand même');
  });

  it('bug a : le message affiche le cours de la demande (« Toi · <cours> »), « Tous les cours » sinon', async () => {
    const pending: ChatMessage = { id: -1, question: 'Un quiz', course: null, status: 'pending', response: null, error: null };
    const { el } = await render([message({ answer: 'R', kind: 'text', sources: [] }), pending]);
    const metas = [...el.querySelectorAll('.student .meta')].map((m) => m.textContent);
    expect(metas).toEqual(['Toi · CNN', 'Toi · Tous les cours']);
  });
});
