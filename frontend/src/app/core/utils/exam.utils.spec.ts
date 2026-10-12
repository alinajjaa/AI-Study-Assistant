import {
  estimateExamMinutes,
  fallbackExamFilename,
  filenameFromContentDisposition,
  formatElapsed,
  describeExam,
  formatPoints,
  pointsPerQuestion,
  summarizeExamResult,
} from './exam.utils';

describe('filenameFromContentDisposition', () => {
  it('lit un nom entre guillemets (format du backend)', () => {
    expect(
      filenameFromContentDisposition('attachment; filename="examen_CNN_intro_complet_moyen.pdf"', 'CNN_intro'),
    ).toBe('examen_CNN_intro_complet_moyen.pdf');
  });

  it('lit un nom sans guillemets', () => {
    expect(filenameFromContentDisposition('attachment; filename=examen.pdf', 'X')).toBe('examen.pdf');
  });

  it("privilégie filename* encodé en UTF-8", () => {
    const header = `attachment; filename="examen.pdf"; filename*=UTF-8''examen_r%C3%A9seaux.pdf`;
    expect(filenameFromContentDisposition(header, 'X')).toBe('examen_réseaux.pdf');
  });

  it('se replie sur examen_<cours>.pdf si l\'en-tête est absent ou sans nom', () => {
    expect(filenameFromContentDisposition(null, 'Réseaux avancés')).toBe('examen_Réseaux_avancés.pdf');
    expect(filenameFromContentDisposition('attachment', 'CNN_intro')).toBe('examen_CNN_intro.pdf');
    expect(filenameFromContentDisposition('attachment; filename=""', 'CNN')).toBe('examen_CNN.pdf');
  });

  it('nettoie les caractères interdits du nom de repli', () => {
    expect(fallbackExamFilename('a/b:c*?')).toBe('examen_a_b_c.pdf');
    expect(fallbackExamFilename('///')).toBe('examen_cours.pdf');
  });
});

describe('estimateExamMinutes', () => {
  it("annonce environ 3 min pour l'examen complet, quel que soit numQuestions", () => {
    expect(estimateExamMinutes({ format: 'complet', numQuestions: 5 })).toBe(3);
    expect(estimateExamMinutes({ format: 'complet', numQuestions: 20 })).toBe(3);
  });

  it('compte ~15 s par question pour le QCM rapide, arrondi à la minute', () => {
    expect(estimateExamMinutes({ format: 'qcm', numQuestions: 5 })).toBe(1); // 75 s
    expect(estimateExamMinutes({ format: 'qcm', numQuestions: 10 })).toBe(3); // 150 s
    expect(estimateExamMinutes({ format: 'qcm', numQuestions: 20 })).toBe(5); // 300 s
  });

  it('annonce au moins 1 minute', () => {
    expect(estimateExamMinutes({ format: 'qcm', numQuestions: 1 })).toBe(1); // 15 s
  });
});

describe('barème', () => {
  it('répartit 20 points sur les questions du QCM rapide', () => {
    expect(pointsPerQuestion(5)).toBe(4);
    expect(pointsPerQuestion(10)).toBe(2);
    expect(pointsPerQuestion(20)).toBe(1);
  });

  it('formate les points à la française', () => {
    expect(formatPoints(20)).toBe('20');
    expect(formatPoints(19.5)).toBe('19,5');
  });
});

describe('summarizeExamResult', () => {
  it('succès quand X-Exam-Total vaut 20', () => {
    expect(summarizeExamResult(15, 15, 20)).toEqual({
      kind: 'success',
      title: 'Examen téléchargé : 15 questions, noté sur 20',
      message: 'Le PDF est dans tes téléchargements.',
    });
  });

  it('avertissement quand X-Exam-Total est inférieur à 20', () => {
    const summary = summarizeExamResult(13, 15, 17.5);
    expect(summary.kind).toBe('warning');
    expect(summary.title).toBe('Examen incomplet : noté sur 17,5 au lieu de 20');
    expect(summary.message).toContain("n'ont pas passé la vérification");
  });

  it('sans X-Exam-Total, compare questions générées et attendues', () => {
    expect(summarizeExamResult(8, 10, null)).toMatchObject({
      kind: 'warning',
      message: 'Seulement 8 questions sur 10 ont pu être générées.',
    });
    expect(summarizeExamResult(10, 10, null).kind).toBe('success');
  });
});

describe('describeExam', () => {
  it('nomme le type choisi', () => {
    expect(describeExam({ format: 'complet', numQuestions: 10 })).toBe('Examen complet');
    expect(describeExam({ format: 'qcm', numQuestions: 20 })).toBe('QCM rapide (20 questions)');
  });
});

describe('formatElapsed', () => {
  it('formate en m:ss', () => {
    expect(formatElapsed(0)).toBe('0:00');
    expect(formatElapsed(7.9)).toBe('0:07');
    expect(formatElapsed(125)).toBe('2:05');
  });
});
