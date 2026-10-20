// Gold per second, measured by the gateway (a reading every 10 s, the
// slope over 5 minutes), written in the game's top bar, and the other
// features' overlay lines (the mode's) top left, both in the gold
// counter's own pixel font (gold_text.js). Options: the "Gold" section.
// The overlay applies while the counter was read lately (the game's
// battle screen).
import { drawText } from './gold_text.js';

// Where the rate goes in the game's top bar: right of the player's name
// (which ends at about 27 % of the width), before the emerald counter (its
// icon at about 38 %), centred on the name's line (2.5 % of the height).
// At the label's size the widest rate ("~44.4W/S", 71 font pixels) takes
// 9.1 % of the width: up to 37.1 %.
const BAR_LEFT = '28%';
const BAR_MIDDLE = '2.5%';

// overlay: functions giving the lines written top left.
export default function goldFeature(api, { overlay }) {
  const gold = { answer: null, timer: null, font: null, line: '' };
  api.get('/gold-font').catch(() => null).then((font) => {
    gold.font = font;
    showGold();
  });
  // The lines, top left, under the active scrolls' icons and timers
  // (under the player's level, y 6–8.7 %), above the event banner (from
  // 14 %): two lines of 8-game-pixel glyphs are 20 of the 1040 game
  // pixels, so the lines take 9.2–11.1 %. Redo this if the banner moves.
  const label = document.createElement('canvas');
  label.style.cssText = 'position:absolute;image-rendering:pixelated;left:3%;top:9.2%';
  const bar = document.createElement('canvas');
  bar.style.cssText = `position:absolute;image-rendering:pixelated;left:${BAR_LEFT}`;
  let drawn = '';
  let barDrawn = '';
  // The rate in the top bar, in the same font and size as the lines;
  // removed while the overlay does not apply or it is hidden.
  const showBar = (cell) => {
    if (!cell || !gold.line) {
      bar.remove();
      barDrawn = '';
      return;
    }
    if (!bar.isConnected) api.layer.appendChild(bar);
    const key = `${gold.line}@${cell}`;
    if (key !== barDrawn) {
      drawText(bar, gold.font, [gold.line], cell);
      bar.style.top = `calc(${BAR_MIDDLE} - ${bar.style.height} / 2)`;
      barDrawn = key;
    }
  };
  const showLabel = (shown) => {
    if (!shown) {
      label.remove();
      drawn = '';
      showBar(null);
      return;
    }
    if (!label.isConnected) api.layer.appendChild(label);
    const lines = overlay.flatMap((lines) => lines());
    // As high as the level's text above it (8 game pixels, the screen
    // being 1040 of them high), not the gold counter's 13.
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    showBar(cell);
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
      : (answer.rate_text ? `${partial}${answer.rate_text}/S` : '...');
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
      bar.remove();
    },
  };
}
