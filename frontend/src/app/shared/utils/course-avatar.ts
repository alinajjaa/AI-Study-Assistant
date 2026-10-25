const AVATAR_TINTS = 6;

/** Initiale affichée dans l'avatar d'un cours. */
export function courseInitial(course: string): string {
  return course.trim().charAt(0).toUpperCase() || '?';
}

/** Teinte stable (0 à 5) dérivée du nom du cours : classe course-avatar--N (styles.css). */
export function courseTint(course: string): number {
  let hash = 0;
  for (const char of course) {
    hash = (hash * 31 + char.codePointAt(0)!) | 0;
  }
  return Math.abs(hash) % AVATAR_TINTS;
}
