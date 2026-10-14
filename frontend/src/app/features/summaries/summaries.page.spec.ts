import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { Summary, SummaryListItem } from '../../core/models/summary.models';
import { SummariesApiService } from '../../core/services/summaries-api.service';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { SummariesPage } from './summaries.page';

const summary: Summary = {
  id: 4,
  course: 'CNN',
  mode: 'course',
  topic: null,
  created_at: '2026-10-14T10:00:00Z',
  cached: false,
  content: {
    found: true,
    overview: 'Ce cours présente les CNN.',
    sections: [
      { title: 'Convolution', pages: [2, 3], bullets: ['La convolution applique des filtres [p.2].'] },
      { title: 'Pooling', pages: [5], bullets: ['Le pooling réduit la taille [p.5].'] },
    ],
  },
};
const item: SummaryListItem = {
  id: 4, course: 'CNN', mode: 'course', topic: null, found: true, section_count: 2, created_at: '2026-10-14T10:00:00Z',
};

function setup(query: Record<string, string> = {}) {
  const api = {
    create: vi.fn(() => of(summary)),
    list: vi.fn(() => of([item])),
    get: vi.fn(() => of(summary)),
    remove: vi.fn(() => of({ deleted: 4 })),
  };
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      { provide: TutorApiService, useValue: { getCourses: () => of(['Autre', 'CNN']) } },
      { provide: SummariesApiService, useValue: api },
      { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap(query) } } },
    ],
  });
  return api;
}

async function render() {
  const fixture = TestBed.createComponent(SummariesPage);
  await fixture.whenStable();
  const el = fixture.nativeElement as HTMLElement;
  const button = (label: string) =>
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes(label));
  return { fixture, el, button };
}

describe('SummariesPage', () => {
  it('« Résumer tout le cours » puis affichage en sections repliables avec les pages', async () => {
    const api = setup({ course: 'CNN' });
    const { fixture, el, button } = await render();
    expect(api.list).toHaveBeenCalledWith('CNN');

    button('Résumer tout le cours')?.click();
    await fixture.whenStable();
    expect(api.create).toHaveBeenCalledWith('CNN', { mode: 'course', regenerate: false });
    expect(el.querySelector('.overview')?.textContent).toContain('Ce cours présente les CNN.');
    const sections = el.querySelectorAll('details.section');
    expect(sections).toHaveLength(2);
    expect((sections[0] as HTMLDetailsElement).open).toBe(true);
    expect((sections[1] as HTMLDetailsElement).open).toBe(false);
    expect(sections[0].querySelector('.section__pages')?.textContent).toContain('p. 2, 3');
    expect(sections[0].querySelector('.page-ref')?.textContent).toBe('p.2');
  });

  it('lancé depuis le tuteur : ?course=CNN&auto=course démarre le résumé du cours', async () => {
    const api = setup({ course: 'CNN', auto: 'course' });
    await render();
    expect(api.create).toHaveBeenCalledWith('CNN', { mode: 'course', regenerate: false });
  });

  it('expliquer un thème envoie le texte saisi', async () => {
    const api = setup({ course: 'CNN' });
    const { fixture, el, button } = await render();
    const input = el.querySelector<HTMLInputElement>('#topic')!;
    input.value = ' les connecteurs ';
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
    button('Expliquer')?.click();
    expect(api.create).toHaveBeenCalledWith('CNN', { mode: 'topic', topic: 'les connecteurs' });
  });

  it('« Mes résumés » : ouvrir, régénérer et supprimer', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const api = setup({ course: 'CNN' });
    const { fixture, el, button } = await render();
    expect(el.querySelector('.summary-list')?.textContent).toContain('Cours entier');

    button('Ouvrir')?.click();
    await fixture.whenStable();
    expect(api.get).toHaveBeenCalledWith(4);
    button('Régénérer')?.click();
    expect(api.create).toHaveBeenCalledWith('CNN', { mode: 'course', regenerate: true });
    await fixture.whenStable();

    el.querySelector<HTMLButtonElement>('.summary-item .icon-btn--danger')?.click();
    await fixture.whenStable();
    expect(api.remove).toHaveBeenCalledWith(4);
    expect(el.querySelector('app-summary-view')).toBeNull();
  });
});
