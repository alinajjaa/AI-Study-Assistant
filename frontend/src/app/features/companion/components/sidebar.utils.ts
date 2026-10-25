/** Texte comparable pour la recherche : minuscules, sans accents. */
export function normalize(text: string): string {
  return text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
}

export function matches(text: string, query: string): boolean {
  const q = normalize(query);
  return q === '' || normalize(text).includes(q);
}
