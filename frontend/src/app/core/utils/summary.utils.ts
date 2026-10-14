/** Morceau d'une puce : du texte, ou une référence de pages [p.X] affichée en pastille. */
export type BulletPart = { kind: 'text'; text: string } | { kind: 'pages'; pages: number[] };

/** Références [p.3], [p. 3], [p.3, 5], [p.3 ; p.5]. */
const PAGE_REF = /\[\s*p\.\s*\d+(?:\s*[,;]\s*(?:p\.\s*)?\d+)*\s*\]/gi;

/** Découpe une puce en texte et références de pages, dans l'ordre. */
export function splitPageRefs(text: string): BulletPart[] {
  const parts: BulletPart[] = [];
  let last = 0;
  for (const match of text.matchAll(PAGE_REF)) {
    const index = match.index ?? 0;
    if (index > last) {
      parts.push({ kind: 'text', text: text.slice(last, index) });
    }
    parts.push({ kind: 'pages', pages: (match[0].match(/\d+/g) ?? []).map(Number) });
    last = index + match[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: 'text', text: text.slice(last) });
  }
  return parts;
}

/** « p. 3 », « p. 3–8 » ou « p. 3, 5, 9 » pour l'en-tête d'une section. */
export function formatPages(pages: readonly number[]): string {
  if (pages.length === 0) {
    return '';
  }
  const sorted = [...new Set(pages)].sort((a, b) => a - b);
  const contiguous = sorted.every((p, i) => i === 0 || p === sorted[i - 1] + 1);
  if (sorted.length > 2 && contiguous) {
    return `p. ${sorted[0]}–${sorted.at(-1)}`;
  }
  return `p. ${sorted.join(', ')}`;
}
