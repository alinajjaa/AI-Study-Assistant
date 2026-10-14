import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { environment } from '../../../environments/environment';
import { ExamRecord } from '../../core/models/exam.models';
import { ExamsPage } from './exams.page';

const exam: ExamRecord = {
  id: 4,
  course: 'CNN_intro',
  format: 'qcm',
  difficulty: 'difficile',
  question_count: 10,
  include_answers: false,
  created_at: '2026-10-14T09:30:00Z',
};

describe('ExamsPage', () => {
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  async function render(exams: ExamRecord[]): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(ExamsPage);
    fixture.detectChanges();
    backend.expectOne(`${environment.apiUrl}/exams`).flush(exams);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('affiche cours, type, difficulté, nombre de questions et date', async () => {
    const el = await render([exam]);
    const row = el.querySelector('tbody tr')?.textContent ?? '';
    expect(row).toContain('CNN_intro');
    expect(row).toContain('QCM rapide');
    expect(row).toContain('sans corrigé');
    expect(row).toContain('Difficile');
    expect(row).toContain('10');
    expect(row).toContain('2026');
  });

  it('affiche un message quand il n’y a aucun examen', async () => {
    const el = await render([]);
    expect(el.textContent).toContain('Aucun examen pour l\'instant');
  });

  it('supprime après confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const el = await render([exam]);
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes('Supprimer'))?.click();
    const req = backend.expectOne(`${environment.apiUrl}/exams/4`);
    expect(req.request.method).toBe('DELETE');
    req.flush({ deleted: 4 });
    await new Promise((resolve) => setTimeout(resolve));
    expect(el.querySelector('tbody')).toBeNull();
  });

  it('retélécharge le PDF depuis /exams/{id}/pdf', async () => {
    const el = await render([exam]);
    [...el.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes('Télécharger'))?.click();
    const req = backend.expectOne(`${environment.apiUrl}/exams/4/pdf`);
    expect(req.request.method).toBe('GET');
    expect(req.request.responseType).toBe('blob');
    req.flush(null);
  });
});
