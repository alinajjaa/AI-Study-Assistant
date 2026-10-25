import { TestBed } from '@angular/core/testing';
import { ConfirmService } from './confirm.service';

describe('ConfirmService', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sans boîte de dialogue montée : repli synchrone sur window.confirm', () => {
    const service = TestBed.inject(ConfirmService);
    const spy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    let answer: boolean | null = null;
    service.ask({ title: 'Supprimer ?', message: 'Définitif.' }).subscribe((ok) => (answer = ok));
    expect(answer).toBe(true);
    expect(spy).toHaveBeenCalledWith('Supprimer ?\nDéfinitif.');
  });

  it('avec la boîte : la question attend la réponse de l’étudiant', () => {
    const service = TestBed.inject(ConfirmService);
    service.attach();
    const answers: boolean[] = [];
    service.ask({ title: 'Supprimer ?', message: 'Définitif.', danger: true }).subscribe((ok) => answers.push(ok));
    expect(service.request()?.title).toBe('Supprimer ?');
    expect(answers).toEqual([]);
    service.answer(true);
    expect(answers).toEqual([true]);
    expect(service.request()).toBeNull();
  });

  it('une nouvelle question annule la précédente', () => {
    const service = TestBed.inject(ConfirmService);
    service.attach();
    const first: boolean[] = [];
    service.ask({ title: 'A', message: '' }).subscribe((ok) => first.push(ok));
    service.ask({ title: 'B', message: '' }).subscribe();
    expect(first).toEqual([false]);
    expect(service.request()?.title).toBe('B');
  });
});
