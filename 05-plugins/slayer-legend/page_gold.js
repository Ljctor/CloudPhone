// Gold per second, measured by the gateway (a reading every 10 s, the
// slope over 5 minutes), written top left on the game under the other
// features' overlay lines (the mode's), in the gold counter's own pixel
// font (gold_text.js). Options: the "Gold" section.
import { drawText } from './gold_text.js';

// overlay: functions giving the lines written above the gold line.
export default function goldFeature(api, { overlay }) {
  const gold = { answer: null, timer: null, font: null, line: '' };
  api.get('/gold-font').catch(() => null).then((font) => {
    gold.font = font;
    showGold();
  });
  // The lines, under the player's level (top left).
  const label = document.createElement('canvas');
  label.style.cssText = 'position:absolute;image-rendering:pixelated;left:3%;top:5.6%';
  let drawn = '';
  const showLabel = (shown) => {
    if (!shown) {
      label.remove();
      drawn = '';
      return;
    }
    if (!label.isConnected) api.layer.appendChild(label);
    const lines = overlay.flatMap((lines) => lines());
    if (gold.line) lines.push(gold.line);
    // As high as the level's text above it (8 game pixels, the screen
    // being 1040 of them high), not the gold counter's 13.
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    const key = `${lines.join('|')}@${cell}`;
    if (key !== drawn) {
      drawText(label, gold.font, lines, cell);
      drawn = key;
    }
  };
  const tick = window.setInterval(() => {
    if (label.isConnected) showLabel(true);
  }, 1000);
  const goldText = () => {
    const answer = gold.answer;
    if (!answer) return '…';
    if (answer.rate_text) return `${answer.span < 285 ? '~' : ''}${answer.rate_text}/s`;
    return answer.read ? api.tr('pas encore mesuré') : api.tr('non visible (économie d’énergie ?)');
  };
  const showGold = () => {
    const answer = gold.answer;
    const box = answer?.box;
    // Only while the counter was read lately: it moves with the game's
    // panels and Power Saving Mode hides it.
    const fresh = box && answer.read && Date.now() / 1000 - answer.read < 25;
    // "~" while the 5-minute window is not full yet.
    const partial = answer?.span < 285 ? '~' : '';
    gold.line = api.setting('goldOverlay') === 'off' || !fresh ? ''
      : `GOLD ${answer.rate_text ? `${partial}${answer.rate_text}/S` : '...'}`;
    showLabel(Boolean(fresh && gold.font));
  };
  const askGold = async () => {
    gold.answer = await api.get('/gold').catch(() => null);
    showGold();
    api.refresh();
    window.clearTimeout(gold.timer);
    gold.timer = window.setTimeout(askGold, 10000);
  };
  askGold();

  return {
    options: [
      { type: 'section', key: 'gold', label: 'Gold' },
      { type: 'status', label: 'Gold par seconde', value: goldText },
      {
        type: 'choice', key: 'goldOverlay', label: 'Overlay gold/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
    ],
    onSetting: (key) => {
      if (key === 'goldOverlay') showGold();
    },
    dispose: () => {
      window.clearTimeout(gold.timer);
      window.clearInterval(tick);
      label.remove();
    },
  };
}
