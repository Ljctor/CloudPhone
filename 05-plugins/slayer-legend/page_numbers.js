// The plugin options use the game's A = 10^3, B = 10^6 notation.
// The game overlay has its own display rules.
const ABBREVIATED = /^\d+(?:\.\d+)?[A-Z]$/;
const FULL = /^\d{1,3}(?:,\d{3})+$|^\d+(?:\.\d+)?$/;

function shortValue(value) {
  if (!Number.isFinite(value)) return null;
  if (value < 0) return `-${shortValue(-value)}`;
  if (value < 1000) return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
  let power = 0;
  while (value >= 1000 && power < 26) {
    value /= 1000;
    power++;
  }
  let digits = value >= 99.95 ? 0 : value >= 9.995 ? 1 : 2;
  let text = value.toFixed(digits);
  if (Number(text) >= 1000 && power < 26) {
    value /= 1000;
    power++;
    digits = 2;
    text = value.toFixed(digits);
  }
  return `${text}${String.fromCharCode(64 + power)}`;
}

export function shortNumber(input) {
  if (input === null || input === undefined) return null;
  if (typeof input === 'number') return shortValue(input);
  const text = String(typeof input === 'object' ? input.text ?? '' : input).trim();
  if (ABBREVIATED.test(text)) return text.replace(/^0+(?=\d)/, '');
  if (FULL.test(text)) return shortValue(Number(text.replaceAll(',', '')));
  if (typeof input === 'object' && typeof input.value === 'number') return shortValue(input.value);
  return text;
}
