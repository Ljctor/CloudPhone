// Full decimal values for the plugin options. The game uses A = 10^3,
// B = 10^6, and so on; expand the written digits without going through a
// JavaScript Number, which would lose digits from large Gold balances.
const GROUPED = /^\d{1,3}(?:,\d{3})+$|^\d+$/;
const ABBREVIATED = /^(\d+)(?:\.(\d+))?([A-Z])$/;
const FORMAT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 });

export function fullNumber(input) {
  if (input === null || input === undefined) return null;
  if (typeof input === 'bigint') return input.toLocaleString('en-US');
  if (typeof input === 'number') return Number.isFinite(input) ? FORMAT.format(input) : null;

  const text = String(typeof input === 'object' ? input.text ?? '' : input).trim();
  if (GROUPED.test(text)) return BigInt(text.replaceAll(',', '')).toLocaleString('en-US');
  const short = ABBREVIATED.exec(text);
  if (short) {
    const [, whole, fraction = '', letter] = short;
    const places = (letter.charCodeAt(0) - 64) * 3 - fraction.length;
    if (places >= 0) {
      const digits = BigInt(whole + fraction) * 10n ** BigInt(places);
      return digits.toLocaleString('en-US');
    }
  }
  if (typeof input === 'object' && typeof input.value === 'number') return fullNumber(input.value);
  return text;
}
