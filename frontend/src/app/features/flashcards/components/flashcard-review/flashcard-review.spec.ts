import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Flashcard } from '../../../../core/models/flashcard.models';
import { FlashcardReview } from './flashcard-review';

const cards: Flashcard[] = [
  { concept: 'Convolution', front: "Qu'est-ce qu'une convolution ?", back: 'Un filtre glissant.', page: 3 },
  { concept: 'Pooling', front: 'À quoi sert le pooling ?', back: 'À réduire la taille.', page: 7 },
];

async function press(fixture: ComponentFixture<FlashcardReview>, key: string): Promise<void> {
  document.body.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
  await fixture.whenStable();
}

describe('FlashcardReview', () => {
  let fixture: ComponentFixture<FlashcardReview>;
  let el: HTMLElement;

  beforeEach(async () => {
    fixture = TestBed.createComponent(FlashcardReview);
    fixture.componentRef.setInput('cards', cards);
    fixture.componentRef.setInput('course', 'CNN');
    await fixture.whenStable();
    el = fixture.nativeElement as HTMLElement;
  });

  const live = () => el.querySelector('[aria-live="polite"]')?.textContent?.trim() ?? '';

  it('affiche le recto, la progression et l’annonce aria-live', () => {
    expect(el.querySelector('.question')?.textContent).toContain("Qu'est-ce qu'une convolution ?");
    expect(el.querySelector('.progress-label')?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 / 2');
    expect(live()).toContain('Recto. Carte 1 sur 2.');
    expect(el.querySelector('.face--back')?.getAttribute('aria-hidden')).toBe('true');
  });

  it('Espace retourne la carte et annonce le verso avec la page', async () => {
    await press(fixture, ' ');
    expect(el.querySelector('.card--flipped')).not.toBeNull();
    expect(live()).toContain('Verso.');
    expect(live()).toContain('Page 3');
    expect(el.textContent).toContain('Je savais');
  });

  it('1 / 2 notent la carte uniquement après retournement, puis écran de fin avec score', async () => {
    await press(fixture, '2');
    expect(el.querySelector('.progress-label')?.textContent).toContain('1 / 2');

    await press(fixture, ' ');
    await press(fixture, '2'); // Je savais
    await press(fixture, ' ');
    await press(fixture, '1'); // À revoir

    expect(el.querySelector('.score')?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 / 2 cartes sues');
    const buttons = [...el.querySelectorAll('.end button')].map((b) => b.textContent?.trim());
    expect(buttons).toEqual(['Revoir les cartes à revoir (1)', 'Recommencer tout le paquet']);
  });

  it('« Revoir les cartes à revoir » relance uniquement ces cartes', async () => {
    await press(fixture, ' ');
    await press(fixture, '1'); // carte 1 à revoir
    await press(fixture, ' ');
    await press(fixture, '2'); // carte 2 sue

    el.querySelector<HTMLButtonElement>('.end button')?.click();
    await fixture.whenStable();

    expect(el.querySelector('.progress-label')?.textContent?.replace(/\s+/g, ' ').trim()).toBe('1 / 1');
    expect(el.querySelector('.question')?.textContent).toContain('convolution');
    expect(el.querySelector('.title')?.textContent).toContain('Cartes à revoir');
  });

  it('les flèches naviguent entre les cartes', async () => {
    await press(fixture, 'ArrowRight');
    expect(el.querySelector('.question')?.textContent).toContain('pooling');
    await press(fixture, 'ArrowLeft');
    expect(el.querySelector('.question')?.textContent).toContain('convolution');
  });
});
