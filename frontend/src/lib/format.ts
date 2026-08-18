export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

// Four decimals, because a single cheap call costs a fraction of a cent.
export function formatUsd(value: number): string {
  return `$${value.toFixed(4)}`;
}

export function formatSeconds(value: number): string {
  if (value < 60) return `${value.toFixed(1)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes} m ${seconds} s`;
}

export function formatTokens(value: number): string {
  return value.toLocaleString();
}
