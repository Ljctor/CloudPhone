// The mode (mpw18 farming by default, or a timed mode: mpw4 farming, free
// play, the mine) runs in the gateway; this browser's options are sent to
// it when they change, and on load if the gateway has not been told since
// it started. Its state is asked every 10 s. Options: the "Mode et
// farming" section. Overlay hooks, called by page_gold.js while the
// overlay applies: overlay(), the mode's lines on the game, top left;
// topBar(), the time left of a timed mode in the game's top bar.
import { drawText } from './gold_text.js';

// This browser's copy of when the timed mode ends (Unix seconds), as the
// gateway last said; sent again after a gateway restart.
const UNTIL = 'cloudphone-slayer-legend-mode-until';
// Free play starts with this timer unless set in its dialog.
const FREE_MINUTES = 60;
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
const MODE_NAMES = { mpw18: 'Farming mpw18', mpw4: 'Farming mpw4', free: 'Jeu libre', mine: 'Mine fermée' };
// Where the time left goes in the game's top bar: right of the player's
// name (which ends at about 27 % of the width), before the emerald counter
// (its icon at about 38 %), centred on the name's line (2.5 % of the height).
const BAR_LEFT = '28%';
const BAR_MIDDLE = '2.5%';

// Seconds as the game's timers write them: mm:ss, or h:mm:ss from an hour.
const clock = (seconds) => {
  const two = (n) => String(n).padStart(2, '0');
  return seconds >= 3600
    ? `${Math.floor(seconds / 3600)}:${two(Math.floor(seconds / 60) % 60)}:${two(seconds % 60)}`
    : `${two(Math.floor(seconds / 60))}:${two(seconds % 60)}`;
};

const load = (name) => {
  try {
    return window.localStorage.getItem(name);
  } catch {
    return null;
  }
};
const keep = (name, value) => {
  try {
    if (value) window.localStorage.setItem(name, String(value));
    else window.localStorage.removeItem(name);
  } catch {
    // Not kept: lost on reload.
  }
};

// known(): the last stage number read (page_screen.js).
export default function modeFeature(api, { known }) {
  const farm = { answer: null, timer: null, stages: null };
  const mode = () => api.setting('mode') || 'mpw18';
  const modeOptions = () => ({
    mode: mode(),
    until: farm.answer?.until ?? (Number(load(UNTIL)) || null),
    stage18: Number(api.setting('stage18')) || null,
    stage4: Number(api.setting('stage4')) || null,
    floor: Number(api.setting('mineFloor')) || null,
    area: Number(api.setting('mineArea') || 1),
  });
  const left = () => {
    const seconds = (farm.answer?.until ?? 0) - Date.now() / 1000;
    if (!farm.answer?.until || seconds <= 0) return api.tr('Sans limite');
    const minutes = Math.ceil(seconds / 60);
    const text = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}` : `${minutes} min`;
    const end = new Date(farm.answer.until * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${api.tr('reste {time}', { time: text })} (${end})`;
  };
  const remember = (answer) => {
    farm.answer = answer;
    if (answer) keep(UNTIL, answer.until);
  };
  const askMode = async () => {
    remember(await api.get('/mode').catch(() => null));
    api.refresh();
    window.clearTimeout(farm.timer);
    farm.timer = window.setTimeout(askMode, 10000);
  };
  const sendMode = async () => {
    const result = await api.post('/mode', modeOptions()).catch(() => null);
    if (result?.ok) remember(result.body);
    else if (result) farm.error = result.body?.error ?? `HTTP ${result.status}`;
    await askMode();
  };
  const moveTimer = async (minutes) => {
    const result = await api.post('/mode/timer', { add: minutes }).catch(() => null);
    if (result?.ok) remember(result.body);
    api.refresh();
  };
  // The mpw18 and mpw4 stages up to the highest one the gateway saw
  // farmed (all of them when it knows none).
  const loadStages = async () => {
    const remembered = known();
    farm.stages = await api.get(remembered ? `/stages?known=${remembered}` : '/stages').catch(() => null);
    api.refresh();
  };
  const stageChoices = (mpw) => [
    { value: '', label: api.tr('— choisir —') },
    ...(farm.stages?.[`mpw${mpw}`] ?? []).map((stage) => ({
      value: String(stage.number),
      label: `${DOTS[stage.colour] ?? '⚪'} mpw${mpw} · ${stage.number}`,
    })),
  ];
  api.get('/mode').catch(() => null).then((answer) => {
    // After a gateway restart it knows nothing: send this browser's options.
    if (answer && !answer.configured) {
      farm.answer = null;
      sendMode();
    } else {
      remember(answer);
      askMode();
    }
  });
  loadStages();

  // The time left of a timed mode (seconds), or null: none runs.
  const timeLeft = () => {
    const current = farm.answer?.mode ?? mode();
    if (current === 'mpw18' || !farm.answer?.until) return null;
    const seconds = Math.round(farm.answer.until - Date.now() / 1000);
    return seconds > 0 ? seconds : null;
  };
  const bar = document.createElement('canvas');
  bar.style.cssText = `position:absolute;image-rendering:pixelated;left:${BAR_LEFT}`;
  let barDrawn = '';

  return {
    // The selected mode, under the player's level (top left), and below it
    // "(défaut)" or the time left on the timer.
    overlay: () => {
      const current = farm.answer?.mode ?? mode();
      const seconds = Math.max(0, Math.round((farm.answer?.until ?? 0) - Date.now() / 1000));
      return [
        api.tr(MODE_NAMES[current] ?? current).toUpperCase(),
        `(${(current === 'mpw18' || !farm.answer?.until ? api.tr('défaut') : clock(seconds)).toUpperCase()})`,
      ];
    },
    // The time left of a timed mode in the game's top bar, in `font` at
    // `cell` CSS pixels per font pixel; removed while the overlay does not
    // apply (shown false) or no timed mode runs.
    topBar: (shown, font, cell) => {
      const seconds = shown ? timeLeft() : null;
      if (seconds === null) {
        bar.remove();
        barDrawn = '';
        return;
      }
      if (!bar.isConnected) api.layer.appendChild(bar);
      const text = clock(seconds);
      const key = `${text}@${cell}`;
      if (key !== barDrawn) {
        drawText(bar, font, [text], cell);
        bar.style.top = `calc(${BAR_MIDDLE} - ${bar.style.height} / 2)`;
        barDrawn = key;
      }
    },
    options: [
      { type: 'section', key: 'mode', label: 'Mode et farming' },
      // One row per mode: a radio button chooses it, Configurer opens its
      // settings.
      {
        type: 'dialog', label: 'Farming mpw18 (par défaut)', title: 'Configuration : farming mpw18',
        select: { key: 'mode', value: 'mpw18', default: 'mpw18' },
        options: [
          { type: 'choice', key: 'stage18', label: 'Stage mpw18', choices: () => stageChoices(18) },
          { type: 'status', label: 'Arme, gravure, réglages de combat', value: () => api.tr('à venir') },
        ],
      },
      {
        type: 'dialog', label: 'Farming mpw4', title: 'Configuration : farming mpw4',
        select: { key: 'mode', value: 'mpw4', default: 'mpw18' },
        options: [
          { type: 'choice', key: 'stage4', label: 'Stage mpw4', choices: () => stageChoices(4) },
        ],
      },
      {
        type: 'dialog', label: 'Jeu libre', title: 'Configuration : jeu libre',
        select: { key: 'mode', value: 'free', default: 'mpw18' },
        options: [
          {
            type: 'number', key: 'freeMinutes', label: 'Minuteur par défaut (minutes)',
            placeholder: String(FREE_MINUTES),
          },
        ],
      },
      {
        type: 'dialog', label: 'Mine fermée', title: 'Configuration : mine fermée',
        select: { key: 'mode', value: 'mine', default: 'mpw18' },
        options: [
          { type: 'number', key: 'mineFloor', label: 'Étage à farmer', placeholder: '161' },
          {
            type: 'choice', key: 'mineArea', label: 'Zone à farmer',
            choices: [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) })),
          },
          { type: 'status', label: 'Plumes', value: () => '3' },
        ],
      },
      {
        type: 'status', label: 'Minuteur',
        visible: () => mode() !== 'mpw18',
        value: left,
      },
      {
        type: 'buttons', label: 'Ajuster (minutes)',
        visible: () => mode() !== 'mpw18',
        buttons: [30, 5, 1, -1, -5, -30].map((m) => ({
          label: m > 0 ? `+${m}` : `−${-m}`,
          run: () => moveTimer(m),
          disabled: () => m < 0 && !farm.answer?.until,
        })),
      },
      {
        type: 'status', label: 'État',
        value: () => {
          if (farm.error) return farm.error;
          if (mode() === 'mine' && !Number(api.setting('mineFloor'))) return api.tr('Choisis l’étage et la zone');
          const answer = farm.answer;
          if (!answer) return '…';
          if (answer.mode === 'mine') {
            const warning = answer.mine?.gold === false ? ` ⚠ ${api.tr('plus de parchemin doré')}` : '';
            return api.tr(answer.mine?.message || 'Mine') + warning;
          }
          return api.tr(answer.message || 'Farming mpw18');
        },
      },
    ],
    onSetting: (key, value) => {
      if (key === 'mode' && value === 'free') {
        const minutes = Number(api.setting('freeMinutes')) || FREE_MINUTES;
        farm.answer = { ...farm.answer, until: Date.now() / 1000 + minutes * 60 };
      }
      if (['mode', 'stage18', 'stage4', 'mineFloor', 'mineArea'].includes(key)) {
        farm.error = null;
        sendMode();
      }
    },
    dispose: () => {
      window.clearTimeout(farm.timer);
      bar.remove();
    },
  };
}
