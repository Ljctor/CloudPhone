// The mode (the default one, « Mode par défaut »: mpw18 farming unless set
// to mpw4 farming or free play; or a timed mode) runs in the gateway; this browser's options are sent to
// it when they change, and on load if the gateway has not been told since
// it started. Its state is asked every 10 s. Options: the "Mode et
// farming" section. Overlay hook, called by page_gold.js while the
// overlay applies: overlay(), the mode's lines on the game, top left (the
// time left of a timed mode under its name, and "MISE EN PLACE..." under
// it while the gateway sets the mode up, "EN ATTENTE" while the switch
// waits for the user to stop playing; asked every 2 s then). While a
// switch is on hold, the État row says so with « Jeu libre » and
// « Reprendre » inline (POST /mode/hold). The mpw18 and mpw4 dialogs
// hold that mode's loadout (page_engraving.js). The État row ends with
// the watchdog's look at the selected mode (page_watchdog.js).
import loadout from './page_engraving.js';

// This browser's copy of when the timed mode ends (Unix seconds), as the
// gateway last said; sent again after a gateway restart.
const UNTIL = 'cloudphone-slayer-legend-mode-until';
// A timed mode starts with this timer (then +30 … −30 to adjust it).
const TIMED_MINUTES = 30;
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
const MODE_NAMES = { mpw18: 'Farming mpw18', mpw4: 'Farming mpw4', free: 'Jeu libre', mine: 'Mine fermée' };

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

// known(): the last stage number read (page_screen.js); watchdog: the
// watchdog part (page_watchdog.js: line, retry); stage: the stage's row,
// under État (page_screen.js).
export default function modeFeature(api, { known, watchdog, stage }) {
  // chosen: when the mode was last chosen here; sending: a POST under way.
  // at: when answer came (Date.now()), for the hold's countdown.
  const farm = { answer: null, timer: null, stages: null, chosen: 0, sending: 0, at: 0 };
  const loadouts = loadout(api);
  const mode = () => api.setting('mode') || 'mpw18';
  // The mode a timed one goes back to, with no timer itself.
  const defaultMode = () => api.setting('defaultMode') || 'mpw18';
  // Only what this browser has: the gateway keeps its values for the rest.
  const modeOptions = () => Object.fromEntries(Object.entries({
    mode: mode(),
    // Only once chosen here (or adopted from the gateway): a browser that
    // never chose one does not reset it.
    default: api.setting('defaultMode') || null,
    until: farm.answer?.until ?? (Number(load(UNTIL)) || null),
    stage18: Number(api.setting('stage18')) || null,
    stage4: Number(api.setting('stage4')) || null,
    floor: Number(api.setting('mineFloor')) || null,
    area: Number(api.setting('mineArea')) || null,
  }).filter(([, value]) => value !== null));
  const left = () => {
    const seconds = (farm.answer?.until ?? 0) - Date.now() / 1000;
    if (!farm.answer?.until || seconds <= 0) return api.tr('Sans limite');
    const minutes = Math.ceil(seconds / 60);
    const text = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}` : `${minutes} min`;
    const end = new Date(farm.answer.until * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${api.tr('reste {time}', { time: text })} (${end})`;
  };
  // asked: when the answer was asked (Date.now()).
  const remember = (answer, asked = 0) => {
    farm.answer = answer;
    farm.at = Date.now();
    if (answer) keep(UNTIL, answer.until);
    // The gateway changed the mode itself (a timed mode ended: back to
    // mpw18): the radio follows, without sending it back (adopt), unless
    // the answer is older than the user's last choice here. Older pages'
    // APIs have no adopt.
    if (answer?.configured && answer.mode && answer.mode !== mode() && !farm.sending && asked > farm.chosen) {
      api.adopt?.('mode', answer.mode);
    }
    if (answer?.configured && answer.default && answer.default !== defaultMode() && !farm.sending
        && asked > farm.chosen) {
      api.adopt?.('defaultMode', answer.default);
    }
  };
  const askMode = async () => {
    const asked = Date.now();
    remember(await api.get('/mode').catch(() => null), asked);
    api.refresh();
    window.clearTimeout(farm.timer);
    farm.timer = window.setTimeout(askMode, farm.answer?.setup ? 2000 : 10000);
  };
  const sendMode = async () => {
    farm.sending += 1;
    const result = await api.post('/mode', modeOptions()).catch(() => null);
    farm.sending -= 1;
    if (result?.ok) remember(result.body);
    else if (result) farm.error = result.body?.error ?? `HTTP ${result.status}`;
    await askMode();
  };
  // The user's answer to a switch on hold: free play instead, or now.
  const answerHold = async (action) => {
    const hold = farm.answer?.hold;
    const result = await api.post('/mode/hold', { action, ...(hold ? { hold: hold.id } : {}) }).catch(() => null);
    if (result?.ok) remember(result.body);
    else if (result) api.toast(api.tr(result.body?.error ?? `HTTP ${result.status}`));
    await askMode();
  };
  // The hold's seconds left, counted down between two answers.
  const holdLeft = () => Math.max(1, Math.round((farm.answer?.hold?.left ?? 0) - (Date.now() - farm.at) / 1000));
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

  return {
    // The selected mode, under the player's level (top left), and below it
    // "(défaut)" or the time left on the timer.
    overlay: () => {
      const current = farm.answer?.mode ?? mode();
      const seconds = Math.max(0, Math.round((farm.answer?.until ?? 0) - Date.now() / 1000));
      return [
        api.tr(MODE_NAMES[current] ?? current).toUpperCase(),
        ...(farm.answer?.hold ? [api.tr('EN ATTENTE')]
          : farm.answer?.setup ? [api.tr('MISE EN PLACE...')] : []),
        `(${(current === defaultMode() || !farm.answer?.until ? api.tr('défaut') : clock(seconds)).toUpperCase()})`,
      ];
    },
    options: [
      { type: 'section', key: 'mode', label: 'Mode et farming' },
      // One row per mode: a radio button chooses it, Configurer opens its
      // settings.
      {
        type: 'dialog', label: 'Farming mpw18',
        select: { key: 'mode', value: 'mpw18', default: 'mpw18' },
        options: [
          { type: 'choice', key: 'stage18', label: 'Stage mpw18', choices: () => stageChoices(18) },
          ...loadouts.options('mpw18'),
        ],
      },
      {
        type: 'dialog', label: 'Farming mpw4',
        // Only once configured: its stage chosen.
        select: { key: 'mode', value: 'mpw4', default: 'mpw18', disabled: () => !Number(api.setting('stage4')) },
        options: [
          { type: 'choice', key: 'stage4', label: 'Stage mpw4', choices: () => stageChoices(4) },
          ...loadouts.options('mpw4'),
        ],
      },
      {
        // Nothing to configure: no Configurer button.
        type: 'dialog', label: 'Jeu libre',
        select: { key: 'mode', value: 'free', default: 'mpw18' },
        options: [],
      },
      {
        type: 'dialog', label: 'Mine fermée',
        // Only once configured: its floor and area chosen.
        select: {
          key: 'mode', value: 'mine', default: 'mpw18',
          disabled: () => !Number(api.setting('mineFloor')) || !Number(api.setting('mineArea')),
        },
        options: [
          { type: 'number', key: 'mineFloor', label: 'Étage à farmer', placeholder: '161' },
          {
            type: 'choice', key: 'mineArea', label: 'Zone à farmer',
            choices: [{ value: '', label: api.tr('— choisir —') },
              ...[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }))],
          },
        ],
      },
      {
        // Saved on change. mpw4 only once its stage is chosen (as its radio
        // button); never the mine.
        type: 'choice', key: 'defaultMode', label: 'Mode par défaut',
        choices: () => [
          { value: 'mpw18', label: api.tr('Farming mpw18') },
          ...(Number(api.setting('stage4')) || defaultMode() === 'mpw4'
            ? [{ value: 'mpw4', label: api.tr('Farming mpw4') }] : []),
          { value: 'free', label: api.tr('Jeu libre') },
        ],
      },
      {
        type: 'status', label: 'Temps restant',
        visible: () => mode() !== defaultMode(),
        value: left,
      },
      {
        type: 'buttons', label: 'Ajuster (minutes)',
        visible: () => mode() !== defaultMode(),
        buttons: [30, 5, 1, -1, -5, -30].map((m) => ({
          label: m > 0 ? `+${m}` : `−${-m}`,
          run: () => moveTimer(m),
          disabled: () => m < 0 && !farm.answer?.until,
        })),
      },
      {
        type: 'status', label: 'État',
        // While a switch is on hold: « Jeu libre », « Reprendre »; else
        // « Réessayer » inline while a repair backs off.
        button: () => {
          if (farm.answer?.hold) {
            return [{ label: 'Jeu libre', run: () => answerHold('free') },
              { label: 'Reprendre', run: () => answerHold('resume') }];
          }
          return farm.answer ? watchdog?.retry(farm.answer.mode) ?? null : null;
        },
        value: () => {
          if (farm.error) return api.tr(farm.error);
          if (mode() === 'mine' && !Number(api.setting('mineFloor'))) return api.tr('Choisis l’étage et la zone');
          const answer = farm.answer;
          if (!answer) return '…';
          if (answer.hold) {
            return api.tr('{mode} · en attente : tu joues · nouvel essai dans {seconds} s',
              { mode: api.tr(MODE_NAMES[answer.hold.mode] ?? answer.hold.mode), seconds: holdLeft() });
          }
          const warning = (gold) => (gold === false ? ` ⚠ ${api.tr('plus de parchemin doré')}` : '');
          const looked = watchdog?.line(answer.mode) ?? '';
          if (answer.mode === 'mine') return api.tr(answer.mine?.message || 'Mine') + warning(answer.mine?.gold) + looked;
          // mpw4 farming: the gateway's gold scroll check (gold, mpw4 only).
          return api.tr(answer.message || 'Farming mpw18') + warning(answer.gold) + looked;
        },
      },
      ...(stage ? [stage] : []),
    ],
    onSetting: (key, value) => {
      loadouts.onSetting(key);
      if (key === 'mode' || key === 'defaultMode') farm.chosen = Date.now();
      if (key === 'mode' && value !== defaultMode() && value !== farm.answer?.mode) {
        farm.answer = { ...farm.answer, until: Date.now() / 1000 + TIMED_MINUTES * 60 };
      }
      if (['mode', 'defaultMode', 'stage18', 'stage4', 'mineFloor', 'mineArea'].includes(key)) {
        farm.error = null;
        sendMode();
      }
    },
    dispose: () => {
      loadouts.dispose();
      window.clearTimeout(farm.timer);
    },
  };
}
