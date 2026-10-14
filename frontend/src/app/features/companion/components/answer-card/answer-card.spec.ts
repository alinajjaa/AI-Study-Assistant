import { TestBed } from '@angular/core/testing';
import { AskResponse } from '../../../../core/models/tutor.models';
import { AnswerCard } from './answer-card';

const response: AskResponse = {
  answer: '**TCP** est fiable [p.3, p.5].\n\n- point un [p.9]\n<script>alert(1)</script>',
  sources: [
    { course: 'Réseaux', page: 5, score: 0.71, excerpt: 'Extrait cinq' },
    { course: 'Réseaux', page: 3, score: 0.82, excerpt: 'Extrait trois' },
    { course: 'Réseaux', page: 3, score: 0.6, excerpt: 'Doublon trois' },
  ],
};

async function render(value: AskResponse) {
  const fixture = TestBed.createComponent(AnswerCard);
  fixture.componentRef.setInput('response', value);
  await fixture.whenStable();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}

describe('AnswerCard', () => {
  it('rend le Markdown et transforme les [p.X] en puces, sans script', async () => {
    const { el } = await render(response);
    const md = el.querySelector('.markdown');
    expect(md?.querySelector('strong')?.textContent).toBe('TCP');
    expect(md?.querySelector('script')).toBeNull();

    const refs = [...el.querySelectorAll<HTMLAnchorElement>('a.page-ref')];
    expect(refs.map((a) => a.getAttribute('href'))).toEqual(['#p-3', '#p-5']);
    // p.9 n'est pas dans les sources : puce non cliquable
    expect(el.querySelector('span.page-ref--missing')?.textContent).toBe('p.9');
  });

  it('ouvre l\'extrait au clic sur une puce sans changer l\'URL', async () => {
    const { fixture, el } = await render(response);
    const ref = el.querySelector<HTMLAnchorElement>('a.page-ref');
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    ref?.dispatchEvent(event);
    await fixture.whenStable();

    expect(event.defaultPrevented).toBe(true);
    expect(el.querySelector('.excerpt')?.textContent).toContain('Extrait trois');
    expect(el.querySelector('.score')?.textContent).toContain('82 %');
  });

  it('dédoublonne et trie les badges de sources', async () => {
    const { el } = await render(response);
    const badges = [...el.querySelectorAll('.badge')].map((b) => b.textContent?.trim());
    expect(badges).toEqual(['p.3', 'p.5']);
  });

  it('affiche le style hors cours sans badges', async () => {
    const { el } = await render({ answer: 'Pas dans le cours.', sources: [] });
    expect(el.querySelector('.answer--off')).not.toBeNull();
    expect(el.querySelector('.badge')).toBeNull();
  });

  it('bug c : NOT_FOUND « Hors du cours » — ni texte supplémentaire, ni sources, même si le modèle en a ajouté', async () => {
    const { el } = await render({
      answer: 'Cette information n’est pas présente dans le cours. Mais en général, **Kubernetes** orchestre [p.4].',
      sources: [{ course: 'Docker', page: 4, score: 0.4, excerpt: 'Extrait' }],
      kind: 'answer',
      answered: false,
    });
    expect(el.querySelector('.tag--off')?.textContent).toContain('Hors du cours');
    expect(el.querySelector('.off-note')?.textContent).toBe('Cette information ne figure pas dans le cours interrogé.');
    expect(el.querySelector('.markdown')).toBeNull();
    expect(el.querySelector('app-sources-list')).toBeNull();
    expect(el.querySelector('.page-ref')).toBeNull();
    expect(el.textContent).not.toContain('Kubernetes');
    expect(el.querySelector('.copy')).toBeNull();
  });
});
