import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { ToastService } from '../../shared/components/toast/toast.service';
import { Summary } from '../models/summary.models';
import { SummariesApiService } from './summaries-api.service';
import { SummaryJobsService } from './summary-jobs.service';

function summary(patch: Partial<Summary> = {}): Summary {
  return {
    id: 1,
    course: 'CNN',
    mode: 'course',
    topic: null,
    created_at: '2026-10-14T10:00:00Z',
    cached: false,
    content: { found: true, overview: 'Vue', sections: [{ title: 'A', pages: [1], bullets: ['x [p.1]'] }] },
    ...patch,
  };
}

describe('SummaryJobsService', () => {
  let response: Subject<Summary>;
  let create: ReturnType<typeof vi.fn>;
  let jobs: SummaryJobsService;
  let toasts: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    response = new Subject<Summary>();
    create = vi.fn(() => response);
    TestBed.configureTestingModule({ providers: [{ provide: SummariesApiService, useValue: { create } }] });
    jobs = TestBed.inject(SummaryJobsService);
    toasts = TestBed.inject(ToastService);
  });

  afterEach(() => vi.useRealTimers());

  it('génère en arrière-plan et annonce la fin', () => {
    jobs.start('CNN', { mode: 'course' });
    expect(create).toHaveBeenCalledWith('CNN', { mode: 'course' });
    expect(jobs.isRunning('CNN', 'course')).toBe(true);
    vi.advanceTimersByTime(1000);
    expect(toasts.toasts().at(-1)).toMatchObject({ kind: 'info', title: 'Résumé du cours « CNN » en cours' });

    response.next(summary());
    response.complete();
    expect(jobs.isRunning('CNN', 'course')).toBe(false);
    expect(jobs.lastSummary()?.id).toBe(1);
    expect(toasts.toasts().at(-1)).toMatchObject({ kind: 'success', title: 'Résumé du cours « CNN » prêt' });
  });

  it('résumé en cache : affiché sans notification', () => {
    jobs.start('CNN', { mode: 'course' });
    response.next(summary({ cached: true }));
    response.complete();
    vi.advanceTimersByTime(1000);
    expect(toasts.toasts()).toHaveLength(0);
    expect(jobs.lastSummary()?.cached).toBe(true);
  });

  it('thème absent du cours : avertissement', () => {
    jobs.start('CNN', { mode: 'topic', topic: 'Docker' });
    response.next(summary({ mode: 'topic', topic: 'Docker', content: { found: false, overview: 'Absent.', sections: [] } }));
    expect(toasts.toasts().at(-1)).toMatchObject({ kind: 'warning', message: 'Absent.' });
  });

  it('refuse une deuxième génération identique et affiche les erreurs', () => {
    jobs.start('CNN', { mode: 'course' });
    jobs.start('CNN', { mode: 'course' });
    expect(create).toHaveBeenCalledTimes(1);
    response.error(new Error('Le modèle a renvoyé une réponse vide. Réessaie.'));
    expect(toasts.toasts().at(-1)).toMatchObject({ kind: 'error', message: 'Le modèle a renvoyé une réponse vide. Réessaie.' });
    expect(jobs.hasJobs()).toBe(false);
  });
});
