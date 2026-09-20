/**
 * Czech noun/adjective agreement after a number: 1 → singular, 2–4 → few,
 * 5+ (and 0) → many. Used for counts shown in the UI.
 */
export function plural(count: number, one: string, few: string, many: string): string {
  const n = Math.abs(Math.trunc(count))
  if (n === 1) return one
  if (n >= 2 && n <= 4) return few
  return many
}

/** "3 události" — the count followed by its agreeing form. */
export function pluralize(
  count: number,
  one: string,
  few: string,
  many: string,
): string {
  return `${count} ${plural(count, one, few, many)}`
}
