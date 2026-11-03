// Observation age in seconds: fresh readings are white, ten-minute-old
// readings light blue. Shared by overlay counters and the settings list.
export function freshnessColour(age = 0) {
  const share = Math.max(0, Math.min(1, Number(age) / 600 || 0));
  return `rgb(${Math.round(255 - 80 * share)}, ${Math.round(255 - 34 * share)}, 255)`;
}

// Reading timestamps belong to the gateway's wall clock. Keep that origin
// while elapsed time advances on this browser's monotonic clock. Response
// time already includes server processing; count only time after receipt.
const observations = new WeakMap();
export function observeResponse(answer, started = performance.now() / 1000) {
  if (answer && Number.isFinite(answer.observed_at) && answer.observed_at > 0) {
    const received = performance.now() / 1000;
    observations.set(answer, { wall: received - started <= 2 ? answer.observed_at : Infinity, started: received });
  }
}
export function responseTime(answer, now = performance.now() / 1000) {
  const observation = answer && observations.get(answer);
  return observation ? observation.wall + now - observation.started : Date.now() / 1000;
}
