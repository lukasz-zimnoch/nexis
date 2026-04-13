import { useEffect } from "react";

export function usePoll(
  enabled: boolean,
  callback: () => void | Promise<void>,
  intervalMs: number,
): void {
  useEffect(() => {
    if (!enabled) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    function schedule() {
      timer = setTimeout(async () => {
        try {
          await callback();
        } finally {
          if (active) schedule();
        }
      }, intervalMs);
    }
    schedule();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [enabled, callback, intervalMs]);
}
