import { formatPages, isCourseSummaryRequest, splitPageRefs } from './summary.utils';

describe('splitPageRefs', () => {
  it('sépare le texte et les références de pages', () => {
    expect(splitPageRefs('Le pooling réduit la taille [p.3].')).toEqual([
      { kind: 'text', text: 'Le pooling réduit la taille ' },
      { kind: 'pages', pages: [3] },
      { kind: 'text', text: '.' },
    ]);
  });

  it('lit plusieurs pages dans une même référence', () => {
    expect(splitPageRefs('Voir [p.3, 5] et [p. 8 ; p.9]').filter((p) => p.kind === 'pages')).toEqual([
      { kind: 'pages', pages: [3, 5] },
      { kind: 'pages', pages: [8, 9] },
    ]);
  });

  it('renvoie le texte seul sans référence', () => {
    expect(splitPageRefs('Sans page')).toEqual([{ kind: 'text', text: 'Sans page' }]);
  });
});

describe('formatPages', () => {
  it('affiche un intervalle pour des pages consécutives, sinon une liste', () => {
    expect(formatPages([5, 3, 4])).toBe('p. 3–5');
    expect(formatPages([3, 9])).toBe('p. 3, 9');
    expect(formatPages([7])).toBe('p. 7');
    expect(formatPages([])).toBe('');
  });
});

describe('isCourseSummaryRequest', () => {
  it.each([
    'résume le cours',
    'Résumé du cours stp',
    'peux-tu me faire un résumé de ce chapitre ?',
    'Resume tout le cours en quelques lignes',
  ])('reconnaît « %s »', (question) => {
    expect(isCourseSummaryRequest(question)).toBe(true);
  });

  it.each([
    'Qu’est-ce qu’un connecteur ?',
    'Résume la notion de pooling',
    'Quelles sont les définitions importantes à retenir ?',
  ])('ignore « %s »', (question) => {
    expect(isCourseSummaryRequest(question)).toBe(false);
  });
});
