// Cheap structural equality. Adequate for the small JSON payloads polled by
// the dashboard; lets us bail out of setState when the server returns the
// same data, so React skips the re-render and the polling effect doesn't
// churn its interval.
export function jsonEqual<T>(a: T, b: T): boolean {
  if (a === b) return true;
  return JSON.stringify(a) === JSON.stringify(b);
}
