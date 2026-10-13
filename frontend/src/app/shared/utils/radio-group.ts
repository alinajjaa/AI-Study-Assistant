/**
 * Navigation clavier d'un groupe de boutons segmentés (role="radiogroup") :
 * flèches, Début et Fin déplacent la sélection et le focus.
 */
export function handleRadioKeydown<T>(
  event: KeyboardEvent,
  values: readonly T[],
  current: T,
  select: (value: T) => void,
): void {
  const index = values.indexOf(current);
  const last = values.length - 1;
  const targets: Record<string, number> = {
    ArrowRight: index === last ? 0 : index + 1,
    ArrowDown: index === last ? 0 : index + 1,
    ArrowLeft: index === 0 ? last : index - 1,
    ArrowUp: index === 0 ? last : index - 1,
    Home: 0,
    End: last,
  };
  const next = targets[event.key];
  if (next === undefined) {
    return;
  }
  event.preventDefault();
  select(values[next]);
  const group = (event.currentTarget as HTMLElement).closest('[role="radiogroup"]');
  group?.querySelectorAll<HTMLElement>('[role="radio"]').item(next)?.focus();
}
