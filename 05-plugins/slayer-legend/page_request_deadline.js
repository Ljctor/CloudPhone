// Bound how long the UI waits. Expiry does not prove that a server-side
// mutation was cancelled; callers reconcile by reading, never auto-retry it.
export function withDeadline(request, { milliseconds = 10000, onLate = () => {} } = {}) {
  const clock = globalThis.window ?? globalThis;
  const schedule = clock.setTimeout?.bind(clock) ?? globalThis.setTimeout;
  const cancel = clock.clearTimeout?.bind(clock) ?? globalThis.clearTimeout;
  return new Promise((resolve, reject) => {
    let expired = false;
    const timer = schedule(() => {
      expired = true;
      reject(Object.assign(new Error('request deadline exceeded'), { code: 'deadline' }));
    }, milliseconds);
    Promise.resolve(request).then((value) => {
      cancel(timer);
      if (expired) onLate(); else resolve(value);
    }, (error) => {
      cancel(timer);
      if (expired) onLate(); else reject(error);
    });
  });
}
