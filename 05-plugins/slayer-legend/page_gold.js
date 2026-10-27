// Gold per second, measured by the gateway (a reading every 10 s, the
// slope over a measured window), shown at the right edge below the top
// bar. The mode remains at the left. Souls per second are read on the Soul
// Weapon screen, where farming modes park. Values use the game's font and
// real counter icons. Gold changes from light blue to white while its
// measurement window fills.
import { drawText } from './gold_text.js';
import { GOLD, SOULS } from './page_icons.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { shortNumber } from './page_numbers.js';

// Keep the measured rates against the right edge, below Scroll (its label
// ends around 17% of the screen). Each row keeps its own icon beside its value.
const RATE_TOP = 19.5;
const RATE_STEP = 2.4;
const FRENCH = new Intl.NumberFormat('fr-FR', { maximumSignificantDigits: 3 });

// The colours measured, each its game icon and rate: [{ icon, text }];
// [] for none.
export function soulsParts(souls) {
  return ['green', 'blue', 'red', 'white'].filter((colour) => typeof souls?.[colour]?.rate === 'number')
    .map((colour) => ({ icon: SOULS[colour], text: shortNumber(souls[colour].rate) }));
}

// overlay: functions giving the lines written top left; enabled(): the
// plugin is on (nothing is drawn while it is off).
// Confidence grows as the measuring window fills: light blue to white.
export function rateColour(answer, elapsed = 0) {
  const share = Math.max(0, Math.min(1, ((answer?.span ?? 0) + elapsed) / (answer?.window ?? 300)));
  return `rgb(${Math.round(175 + 80 * share)}, ${Math.round(221 + 34 * share)}, 255)`;
}

export default function goldFeature(api, { overlay, enabled = () => true }) {
  const gold = { answer: null, at: 0, timer: null, font: null, line: '', cube: null };
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
  // Gold moves from 21% on Battle to 15.5% with a bottom panel. Cubes stay
  // between those positions, above or below Gold in turn.
  const cubeRow = document.createElement('div');
  cubeRow.style.cssText = 'position:absolute;left:37%;top:17.8%;display:flex;align-items:center;gap:2px;pointer-events:none';
  const cubeIcon = document.createElement('img');
  cubeIcon.src = RESOURCE_ICONS.cubes ?? '';
  cubeIcon.alt = '';
  cubeIcon.style.imageRendering = 'pixelated';
  const cubeValue = document.createElement('canvas');
  cubeValue.style.imageRendering = 'pixelated';
  cubeRow.append(cubeIcon, cubeValue);
  let cubeDrawn = '';
  const showCube = () => {
    const cube = gold.cube;
    const goldVisible = gold.answer?.box && gold.answer.read &&
      Date.now() / 1000 - gold.answer.read < 25;
    if (!cube?.seen || cube.value == null || !gold.font || !enabled() || !goldVisible) {
      cubeRow.remove();
      cubeDrawn = '';
      return;
    }
    const value = typeof cube.value === 'number' ? cube.value.toLocaleString('en-US') :
      String(cube.value?.text ?? cube.value);
    const age = Math.max(0, Date.now() / 1000 - cube.seen);
    const share = Math.min(1, age / 600);
    const colour = `rgb(${Math.round(255 - 80 * share)}, ${Math.round(255 - 34 * share)}, 255)`;
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    const key = `${value}@${colour}@${cell}`;
    if (key === cubeDrawn) return;
    if (!cubeRow.isConnected) api.layer.append(cubeRow);
    drawText(cubeValue, gold.font, [{ text: value, colour }], cell);
    const size = gold.font.height * cell;
    cubeIcon.style.width = `${size}px`;
    cubeIcon.style.height = `${size}px`;
    cubeDrawn = key;
  };
  const rateRows = [GOLD, SOULS.green, SOULS.blue, SOULS.red, SOULS.white].map((src, index) => {
    const row = document.createElement('div');
    row.style.cssText = `position:absolute;right:1%;top:${RATE_TOP + index * RATE_STEP}%;display:flex;align-items:center;gap:2px;pointer-events:none`;
    const icon = document.createElement('img');
    icon.src = src;
    icon.alt = '';
    icon.style.imageRendering = 'pixelated';
    const value = document.createElement('canvas');
    value.style.imageRendering = 'pixelated';
    row.append(icon, value);
    return { row, icon, value };
  });
  let drawn = '';
  let ratesDrawn = '';
  const showRates = (cell) => {
    if (!cell || !gold.answer) {
      rateRows.forEach(({ row }) => row.remove());
      ratesDrawn = '';
      return;
    }
    const souls = gold.answer?.souls ?? {};
    const entries = [api.setting('goldOverlay') === 'off' ? '' : gold.line,
      ...['green', 'blue', 'red', 'white'].map((colour) => api.setting('stonesOverlay') === 'off'
        ? '' : typeof souls[colour]?.rate === 'number' ? `${FRENCH.format(souls[colour].rate)}/s` : '')];
    const colour = rateColour(gold.answer, (Date.now() - gold.at) / 1000);
    const key = `${entries.join('|')}@${cell}@${colour}`;
    if (key !== ratesDrawn) {
      rateRows.forEach(({ row, icon, value }, index) => {
        if (!entries[index]) { row.remove(); return; }
        if (!row.isConnected) api.layer.append(row);
        drawText(value, gold.font, [{ text: entries[index], colour: index ? '#fff' : colour }], cell);
        const size = gold.font.height * cell;
        icon.style.width = `${size}px`;
        icon.style.height = `${size}px`;
      });
      ratesDrawn = key;
    }
  };
  const showLabel = (shown) => {
    if (!shown) {
      label.remove();
      drawn = '';
      showRates(null);
      return;
    }
    if (!label.isConnected) api.layer.appendChild(label);
    const lines = overlay.flatMap((lines) => lines());
    // As high as the level's text above it (8 game pixels, the screen
    // being 1040 of them high), not the gold counter's 13.
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    showRates(cell);
    const key = `${JSON.stringify(lines)}@${cell}`;
    if (key !== drawn) {
      drawText(label, gold.font, lines, cell);
      drawn = key;
    }
  };
  const tick = window.setInterval(() => {
    if (label.isConnected) showLabel(true);
    if (cubeRow.isConnected) showCube();
    if (gold.answer?.rate_text) api.refresh();
  }, 1000);
  const goldText = () => {
    const answer = gold.answer;
    if (!answer) return '…';
    if (answer.rate_text) return [{ icon: GOLD, text: `${shortNumber(answer.rate_text)}/s`,
      color: rateColour(answer, (Date.now() - gold.at) / 1000) }];
    return answer.read ? api.tr('pas encore mesuré') : api.tr('non visible');
  };
  const soulsValue = () => {
    const answer = gold.answer;
    if (!answer) return '…';
    const parts = soulsParts(answer.souls);
    return parts.length ? parts : api.tr('pas encore mesuré');
  };
  const showGold = () => {
    const answer = gold.answer;
    const box = answer?.box;
    // Only while the counter was read lately: it moves with the game's
    // panels and Power Saving Mode hides it.
    const fresh = box && answer.read && Date.now() / 1000 - answer.read < 25;
    const soulsFresh = Object.values(answer?.souls ?? {}).some((part) =>
      part.read && Date.now() / 1000 - part.read < 25);
    gold.line = !fresh ? '' : (answer.rate_text ? `${answer.rate_text}/s` : '...');
    showLabel(Boolean((fresh || soulsFresh) && gold.font && enabled()));
    showCube();
  };
  const askGold = async () => {
    const [answer, state] = await Promise.all([
      api.get('/gold').catch(() => null), api.get('/game').catch(() => null),
    ]);
    gold.answer = answer;
    gold.cube = state?.resources?.find((row) => row.field === 'cubes') ?? gold.cube;
    gold.at = Date.now();
    showGold();
    api.refresh();
    window.clearTimeout(gold.timer);
    gold.timer = window.setTimeout(askGold, 10000);
  };
  askGold();

  return {
    // Draws again (or removes) after the plugin was turned on or off.
    update: () => showGold(),
    resourceOptions: [
      { type: 'status', label: 'Gold par seconde', value: goldText, look: 'game' },
      { type: 'status', label: 'Âmes par seconde', value: soulsValue, look: 'game' },
    ],
    displayOptions: [
      { type: 'section', key: 'display-rates', label: 'Débits', folded: true, icon: GOLD },
      {
        type: 'choice', key: 'goldOverlay', label: 'Gold/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
      {
        type: 'choice', key: 'stonesOverlay', label: 'Âmes/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
    ],
    onSetting: (key) => {
      if (key === 'goldOverlay' || key === 'stonesOverlay') showGold();
    },
    dispose: () => {
      window.clearTimeout(gold.timer);
      window.clearInterval(tick);
      label.remove();
      rateRows.forEach(({ row }) => row.remove());
      cubeRow.remove();
    },
  };
}
