import { DEFAULT_EXAM_OPTIONS, ExamOptions } from '../models/exam.models';
import { EXAM_OPTIONS_STORAGE_KEY, loadExamOptions, saveExamOptions } from './exam-options.storage';

describe('exam-options.storage', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it('renvoie les valeurs par défaut sans choix mémorisés', () => {
    expect(loadExamOptions()).toEqual(DEFAULT_EXAM_OPTIONS);
    expect(DEFAULT_EXAM_OPTIONS).toEqual({
      format: 'complet',
      numQuestions: 10,
      difficulty: 'moyen',
      includeAnswers: true,
    });
  });

  it('relit les choix enregistrés, format compris', () => {
    const options: ExamOptions = { format: 'qcm', numQuestions: 20, difficulty: 'difficile', includeAnswers: false };
    saveExamOptions(options);
    expect(loadExamOptions()).toEqual(options);
  });

  it("remplace une ancienne valeur invalide (numQuestions = 15, sans format) par la valeur par défaut", () => {
    localStorage.setItem(
      EXAM_OPTIONS_STORAGE_KEY,
      JSON.stringify({ numQuestions: 15, difficulty: 'facile', includeAnswers: false }),
    );
    expect(loadExamOptions()).toEqual({
      format: 'complet',
      numQuestions: 10,
      difficulty: 'facile',
      includeAnswers: false,
    });
  });

  it('ignore un format ou des types inconnus', () => {
    localStorage.setItem(
      EXAM_OPTIONS_STORAGE_KEY,
      JSON.stringify({ format: 'oral', numQuestions: '5', difficulty: 'extrême', includeAnswers: 'oui' }),
    );
    expect(loadExamOptions()).toEqual(DEFAULT_EXAM_OPTIONS);
  });

  it('résiste à un JSON corrompu', () => {
    localStorage.setItem(EXAM_OPTIONS_STORAGE_KEY, '{pas du json');
    expect(loadExamOptions()).toEqual(DEFAULT_EXAM_OPTIONS);
  });

  it('résiste à un stockage indisponible', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(() => saveExamOptions(DEFAULT_EXAM_OPTIONS)).not.toThrow();
    expect(loadExamOptions()).toEqual(DEFAULT_EXAM_OPTIONS);
  });
});
