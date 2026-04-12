import { useEffect } from "react";

export function usePoll(
  enabled: boolean,
  callback: () => void,
  intervalMs: number,
): void {
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(callback, intervalMs);
    return () => window.clearInterval(id);
  }, [enabled, callback, intervalMs]);
}
