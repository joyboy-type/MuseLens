/** Monotonic clock for measuring completed user-triggered requests. */
export function monotonicNow(): number {
  return performance.now();
}
