import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { ChatMessage } from '../../../../core/models/tutor.models';
import { ChatThread } from './chat-thread';

function message(question: string): ChatMessage {
  return {
    id: 1,
    question,
    course: 'CNN',
    status: 'done',
    error: null,
    response: { answer: 'Réponse [p.1].', sources: [{ course: 'CNN', page: 1, score: 0.9, excerpt: '…' }] },
  };
}

async function render(messages: ChatMessage[], course: string | null = 'CNN'): Promise<HTMLElement> {
  TestBed.configureTestingModule({ providers: [provideRouter([])] });
  const fixture = TestBed.createComponent(ChatThread);
  fixture.componentRef.setInput('messages', messages);
  fixture.componentRef.setInput('course', course);
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

describe('ChatThread — résumés', () => {
  it('remplace la suggestion de résumé par un lien qui lance le résumé du cours sélectionné', async () => {
    const el = await render([]);
    const link = el.querySelector<HTMLAnchorElement>('a.suggestion');
    expect(link?.textContent).toContain('Résumer ce cours');
    expect(link?.getAttribute('href')).toBe('/summaries?course=CNN&auto=course');
    const buttons = [...el.querySelectorAll('button.suggestion')].map((b) => b.textContent?.trim());
    expect(buttons).toEqual([
      'Quelles sont les définitions importantes à retenir ?',
      'Explique-moi la notion la plus difficile avec un exemple.',
    ]);
    expect(el.textContent).not.toContain('Résume les idées principales');
  });

  it('sans cours sélectionné, le lien ouvre simplement la page Résumés', async () => {
    const el = await render([], null);
    expect(el.querySelector('a.suggestion')?.getAttribute('href')).toBe('/summaries');
  });

  it('demande de résumé tapée : lien sous la réponse', async () => {
    const el = await render([message('Résume le cours stp')]);
    const link = el.querySelector<HTMLAnchorElement>('.summary-hint a');
    expect(link?.textContent).toContain('Pour un résumé complet du cours, ouvre Résumés');
    expect(link?.getAttribute('href')).toBe('/summaries?course=CNN');
  });

  it('question ordinaire : pas de lien', async () => {
    const el = await render([message('Qu’est-ce qu’un connecteur ?')]);
    expect(el.querySelector('.summary-hint')).toBeNull();
  });
});
