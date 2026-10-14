import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { marked } from 'marked';
import { AskResponse, isOffCourse } from '../../../../core/models/tutor.models';
import { SourcesList } from '../sources-list/sources-list';

/** Références de pages citées par le LLM : [p.3], [p. 3], [p.3, p.5], [p.3, 5]… */
const PAGE_REF_GROUP = /\[\s*(p\.\s*\d+(?:\s*[,;]\s*(?:p\.\s*)?\d+)*)\s*\]/g;

type CopyState = 'idle' | 'copied' | 'failed';

/**
 * Markdown → HTML, puis remplacement des [p.X] par des puces.
 * Le HTML produit passe ensuite par la sanitization d'Angular ([innerHTML]) :
 * on n'utilise donc que des éléments/attributs qu'elle conserve (a, span, class, href, title).
 */
function renderAnswer(markdown: string, citedPages: ReadonlySet<number>): string {
  const html = marked.parse(markdown, { async: false, gfm: true, breaks: true });
  return html.replace(PAGE_REF_GROUP, (_match, group: string) =>
    (group.match(/\d+/g) ?? [])
      .map((n) =>
        citedPages.has(Number(n))
          ? `<a class="page-ref" href="#p-${n}" title="Voir l'extrait de la page ${n}">p.${n}</a>`
          : `<span class="page-ref page-ref--missing" title="Page non fournie dans les sources">p.${n}</span>`,
      )
      .join(' '),
  );
}

@Component({
  selector: 'app-answer-card',
  imports: [SourcesList],
  templateUrl: './answer-card.html',
  styleUrl: './answer-card.css',
})
export class AnswerCard {
  private copyTimer: ReturnType<typeof setTimeout> | undefined;

  readonly response = input.required<AskResponse>();

  /** L'information n'est pas dans le cours : seule la mention « Hors du cours » est affichée. */
  protected readonly offCourse = computed(() => isOffCourse(this.response()));
  protected readonly html = computed(() => {
    const { answer, sources } = this.response();
    return renderAnswer(answer, new Set(sources.map((s) => s.page)));
  });
  /** Page ouverte dans sources-list (via un badge ou une puce [p.X]). */
  protected readonly activePage = signal<number | null>(null);
  protected readonly copyState = signal<CopyState>('idle');
  protected readonly copyLabel = computed(() => {
    switch (this.copyState()) {
      case 'copied':
        return 'Copié';
      case 'failed':
        return 'Échec de la copie';
      default:
        return 'Copier la réponse';
    }
  });

  constructor() {
    inject(DestroyRef).onDestroy(() => clearTimeout(this.copyTimer));
  }

  /** Délégation de clic : les puces [p.X] sont du HTML injecté, sans liaison Angular. */
  protected onContentClick(event: MouseEvent): void {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }
    const ref = target.closest('a.page-ref');
    if (!ref) {
      return;
    }
    // Empêche "#p-3" de modifier l'URL ou de déclencher le routeur.
    event.preventDefault();
    const page = Number(ref.getAttribute('href')?.replace('#p-', ''));
    if (Number.isInteger(page)) {
      this.activePage.set(page);
    }
  }

  protected async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.response().answer);
      this.copyState.set('copied');
    } catch {
      this.copyState.set('failed');
    }
    clearTimeout(this.copyTimer);
    this.copyTimer = setTimeout(() => this.copyState.set('idle'), 2000);
  }
}
