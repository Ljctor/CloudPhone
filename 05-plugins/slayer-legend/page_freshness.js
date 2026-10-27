// Observation age in seconds: fresh readings are white, ten-minute-old
// readings light blue. Shared by overlay counters and the settings list.
export function freshnessColour(age = 0) {
  const share = Math.max(0, Math.min(1, Number(age) / 600 || 0));
  return `rgb(${Math.round(255 - 80 * share)}, ${Math.round(255 - 34 * share)}, 255)`;
}
