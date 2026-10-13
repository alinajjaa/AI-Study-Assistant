import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { TutorApiService } from '../../core/services/tutor-api.service';
import { FlashcardsPage } from './flashcards.page';

describe('FlashcardsPage — durée estimée', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: TutorApiService, useValue: { getCourses: () => of(['CNN']) } }],
    });
  });

  it('affiche 3, 5 et 8 min pour 10, 20 et 30 cartes', async () => {
    const fixture = TestBed.createComponent(FlashcardsPage);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const minutesFor = async (count: string): Promise<string | undefined> => {
      const segment = [...el.querySelectorAll<HTMLButtonElement>('.segment')].find((b) => b.textContent?.trim() === count);
      segment?.click();
      await fixture.whenStable();
      return /environ (\d+) min/.exec(el.querySelector('.estimate')?.textContent ?? '')?.[1];
    };

    expect(await minutesFor('10')).toBe('3');
    expect(await minutesFor('20')).toBe('5');
    expect(await minutesFor('30')).toBe('8');
  });
});
