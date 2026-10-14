import { TestBed } from '@angular/core/testing';
import { NEVER } from 'rxjs';
import { ExamOptions } from '../../../../core/models/exam.models';
import { ExamApiService } from '../../../../core/services/exam-api.service';
import { ExamJobsService } from '../../../../core/services/exam-jobs.service';
import { saveExamOptions } from '../../../../core/utils/exam-options.storage';
import { ToastService } from '../../../../shared/components/toast/toast.service';
import { ExamDialog } from './exam-dialog';

/** jsdom n'implémente pas toujours showModal/close : on simule l'attribut open. */
function stubDialog(): void {
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close ??= function (this: HTMLDialogElement) {
    this.removeAttribute('open');
    this.dispatchEvent(new Event('close'));
  };
}

/** « Durée estimée : environ X min » affiché dans la modale ouverte avec ces options. */
async function dialogMinutes(options: ExamOptions): Promise<string | undefined> {
  saveExamOptions(options);
  const fixture = TestBed.createComponent(ExamDialog);
  fixture.componentRef.setInput('course', 'CNN');
  await fixture.whenStable();
  const text = (fixture.nativeElement as HTMLElement).querySelector('.estimate')?.textContent ?? '';
  fixture.destroy();
  return /environ (\d+) min/.exec(text)?.[1];
}

/** « Environ X min » de la notification de lancement pour ces options. */
function toastMinutes(options: ExamOptions, course: string): string | undefined {
  TestBed.inject(ExamJobsService).start(course, options);
  const toast = TestBed.inject(ToastService).toasts().at(-1);
  return /Environ (\d+) min/.exec(toast?.message ?? '')?.[1];
}

describe('ExamDialog — durée estimée', () => {
  beforeAll(stubDialog);

  beforeEach(() => {
    localStorage.clear();
    // Génération jamais terminée : seul le toast de lancement nous intéresse.
    TestBed.configureTestingModule({
      providers: [{ provide: ExamApiService, useValue: { generateExam: () => NEVER } }],
    });
  });

  const cases: { options: ExamOptions; minutes: string }[] = [
    { options: { format: 'complet', numQuestions: 10, difficulty: 'moyen', includeAnswers: true }, minutes: '3' },
    { options: { format: 'qcm', numQuestions: 5, difficulty: 'facile', includeAnswers: true }, minutes: '1' },
    { options: { format: 'qcm', numQuestions: 10, difficulty: 'moyen', includeAnswers: false }, minutes: '2' },
    { options: { format: 'qcm', numQuestions: 20, difficulty: 'difficile', includeAnswers: true }, minutes: '3' },
  ];

  for (const { options, minutes } of cases) {
    it(`affiche ${minutes} min dans la modale et le toast (${options.format}, ${options.numQuestions} q., ${options.difficulty})`, async () => {
      expect(await dialogMinutes(options)).toBe(minutes);
      expect(toastMinutes(options, `cours-${options.format}-${options.numQuestions}`)).toBe(minutes);
    });
  }
});
