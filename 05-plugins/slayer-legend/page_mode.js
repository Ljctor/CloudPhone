// The mode (the default one, « Mode par défaut »: mpw18 farming unless set
// to mpw4 farming or free play; or a timed mode) runs in the gateway; the page's options (kept by the gateway) are sent to
// it when they change, and on load if the gateway has not been told since
// it started. Its state is asked every 10 s. Options: the "Mode et
// farming" section. Overlay hook, called by page_gold.js while the
// overlay applies: overlay(), only the mode and timer (or "défaut")
// on the game, top left; explanations stay in notifications and options. In the
// colour of the gateway's tone: white when reached, blue during input
// and the rolling 5 s pause, orange while returning, red when blocked.
// The timer or "défaut" is green only when stable. A touch on the game asks the tone
// again at once, and every 2 s while it holds. While a
// switch is on hold, the État row says so with « Jeu libre » and
// « Reprendre » inline (POST /mode/hold). The mpw18 and mpw4 dialogs
// hold that mode's loadout (page_engraving.js). The État row ends with
// the watchdog's look at the selected mode (page_watchdog.js).
import loadout from './page_engraving.js';
import { withDeadline } from './page_request_deadline.js';

// Where earlier versions kept when the timed mode ends, in this browser:
// sent once to a gateway that knows no mode yet, then removed (the
// gateway keeps it in state.json).
const UNTIL = 'cloudphone-slayer-legend-mode-until';
// A timed mode starts with this timer (then +30 … −30 to adjust it).
const TIMED_MINUTES = 30;
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
const MODE_NAMES = { mpw18: 'Farming mpw18', mpw4: 'Farming mpw4', free: 'Jeu libre',
  agent: 'Agent mode', mine: 'Mine fermée' };
// The overlay's colour per tone (GET /mode).
const TONES = { ok: '#ffffff', hold: '#409cff', error: '#ff4040', setup: '#ffa31a' };
const TIMER_COLOUR = '#4be04b';
const INPUT_PAUSE_MS = 5000;

// Seconds as the game's timers write them: mm:ss, or h:mm:ss from an hour.
const clock = (seconds) => {
  const two = (n) => String(n).padStart(2, '0');
  return seconds >= 3600
    ? `${Math.floor(seconds / 3600)}:${two(Math.floor(seconds / 60) % 60)}:${two(seconds % 60)}`
    : `${two(Math.floor(seconds / 60))}:${two(seconds % 60)}`;
};

// The old copy of the timer's end, read once and removed.
const takeOld = (name) => {
  try {
    const value = window.localStorage.getItem(name);
    window.localStorage.removeItem(name);
    return value;
  } catch {
    return null;
  }
};

// known(): the last stage number read (page_screen.js, from the gateway); watchdog: the
// watchdog part (page_watchdog.js: line, retry); stage: the stage's row,
// under État (page_screen.js).
export default function modeFeature(api, { known, watchdog, stage }) {
  api.addTranslations?.({
    'Appliquer la configuration': 'Apply configuration',
    'Application demandée…': 'Application requested…',
    'Application non confirmée · vérification en cours': 'Application unconfirmed · checking status',
  });
  // chosen: when the mode was last chosen here; sending: a POST under way.
  // at: when answer came (Date.now()), for the hold's countdown.
  const farm = { answer: null, timer: null, stages: null, chosen: 0, sending: 0, at: 0,
    oldUntil: Number(takeOld(UNTIL)) || null, inputUntil: 0 };
  const loadouts = loadout(api, { execution: () => farm.answer, onApplied: () => { askMode(); loadStages(); },
    onExecute: (request) => applySetup(request) });
  const mode = () => api.setting('mode') || 'mpw18';
  // The mode a timed one goes back to, with no timer itself.
  const defaultMode = () => api.setting('defaultMode') || 'mpw18';
  // Only what the page's options have: the gateway keeps its values for the rest.
  const modeOptions = () => Object.fromEntries(Object.entries({
    mode: mode(),
    // Only once chosen here (or adopted from the gateway): a browser that
    // never chose one does not reset it.
    default: api.setting('defaultMode') || null,
    until: farm.answer?.until ?? farm.oldUntil,
    floor: Number(api.setting('mineFloor')) || null,
    area: Number(api.setting('mineArea')) || null,
  }).filter(([, value]) => value !== null));
  const left = () => {
    const seconds = (farm.answer?.until ?? 0) - Date.now() / 1000;
    const current = farm.answer?.mode ?? mode();
    if (current === defaultMode()) return api.tr('défaut').toLowerCase();
    if (!Number.isFinite(farm.answer?.until)) return '…';
    if (seconds <= 0) return clock(0);
    const minutes = Math.ceil(seconds / 60);
    const text = minutes >= 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')}` : `${minutes} min`;
    const end = new Date(farm.answer.until * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${api.tr('reste {time}', { time: text })} (${end})`;
  };
  // asked: when the answer was asked (Date.now()).
  const remember = (answer, asked = 0) => {
    farm.answer = answer;
    farm.at = Date.now();
    if (answer?.configured) farm.oldUntil = null;
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
    farm.timer = window.setTimeout(askMode, farm.answer?.intention || farm.answer?.tone !== 'ok' || farm.inputUntil > Date.now() ? 1000 : 10000);
  };
  // A touch on the game: the gateway holds its taps from now, ask its tone.
  const untap = api.onTap?.(() => {
    farm.inputUntil = Date.now() + INPUT_PAUSE_MS;
    api.refresh();
    window.clearTimeout(farm.timer);
    farm.timer = window.setTimeout(askMode, 300);
  });
  const sendMode = async () => {
    farm.sending += 1;
    const result = await api.post('/mode', modeOptions()).catch(() => null);
    farm.sending -= 1;
    if (result?.ok) remember(result.body);
    else if (result) farm.error = result.body?.error_t ?? `HTTP ${result.status}`;
    await askMode();
  };
  // The user's answer to a switch on hold: free play instead, or now.
  const answerHold = async (action) => {
    const hold = farm.answer?.hold;
    const result = await api.post('/mode/hold', { action, ...(hold ? { hold: hold.id } : {}) }).catch(() => null);
    if (result?.ok) remember(result.body);
    else if (result) api.warn(result.body?.error_t ?? `HTTP ${result.status}`);
    await askMode();
  };
  const applySetup = async (request) => {
    if (farm.applying) return;
    farm.applying = true; farm.error = null; api.refresh();
    try {
      const result = await withDeadline(api.post('/mode/setup', request), { onLate: askMode })
        .catch(() => null);
      if (result?.ok) remember(result.body);
      else farm.error = result?.body?.error_t ?? 'Application non confirmée · vérification en cours';
      // An accepted request is not a verified setup; read the execution state.
      await askMode();
    } finally { farm.applying = false; api.refresh(); }
  };
  // The hold's seconds left, counted down between two answers.
  const holdLeft = () => Math.max(1, Math.round((farm.answer?.hold?.left ?? 0) - (Date.now() - farm.at) / 1000));
  const moveTimer = async (minutes) => {
    const result = await api.post('/mode/timer', { add: minutes }).catch(() => null);
    if (result?.ok) remember(result.body);
    api.refresh();
  };
  // Every mpw18 and mpw4 stage: the player may choose one beyond the
  // The last stage seen is only a lower bound for the highest unlocked one.
  const loadStages = async () => {
    farm.stages = await api.get('/stages').catch(() => null);
    api.refresh();
  };
  const stageChoices = (mpw) => {
    const highest = farm.stages?.highest ?? farm.answer?.highest;
    return [
      { value: '', label: api.tr('— choisir —') },
      ...(farm.stages?.[`mpw${mpw}`] ?? []).map((stage) => ({
        value: String(stage.number),
        label: `${DOTS[stage.colour] ?? '⚪'} mpw${mpw} · ${stage.number}`,
        muted: Boolean(highest && stage.number > highest),
      })),
    ];
  };
  api.get('/mode').catch(() => null).then((answer) => {
    // A gateway that knows no mode yet: send the page's options.
    if (answer && !answer.configured) {
      farm.answer = null;
      sendMode();
    } else {
      remember(answer);
      askMode();
    }
  });
  loadStages();

  const activeIntention = () => farm.answer?.intention ?? watchdog?.intention?.(farm.answer?.mode ?? mode()) ?? null;
  const destinationName = (intent) => intent.destination_t ?? ({
    battle: 'Combat', game: 'Slayer Legend', equipment_weapon: 'Equipment: Weapon',
    equipment_accessories: 'Equipment: Accessories', weapon_detail: 'Détail de l’arme',
    soul_weapon: 'Soul Weapon', battle_settings: 'Battle settings', mine_list: 'Mine fermée',
  }[intent.destination] ?? intent.destination);

  return {
    // The selected mode, under the player's level (top left), and below it
    // Only the mode and its timer (or "défaut") on the game.
    overlay: () => {
      const current = farm.answer?.mode ?? mode();
      const seconds = Math.max(0, Math.round((farm.answer?.until ?? 0) - Date.now() / 1000));
      const tone = farm.inputUntil > Date.now() ? 'hold' : farm.answer?.tone;
      const colour = TONES[tone] ?? TONES.setup;
      return [
        { text: api.tr(MODE_NAMES[current] ?? current).toUpperCase(), colour },
        { text: current === defaultMode() ? api.tr('défaut').toLowerCase()
          : Number.isFinite(farm.answer?.until) ? clock(seconds) : '…',
          colour: tone === 'ok' ? TIMER_COLOUR : colour },
      ];
    },
    options: [
      { type: 'section', key: 'mode', label: 'Mode et farming' },
      // One row per mode: a radio button chooses it, Configurer opens its
      // settings.
      {
        type: 'dialog', label: 'Jeu libre',
        select: { key: 'mode', value: 'free', default: 'mpw18' },
        options: [],
      },
      {
        type: 'dialog', label: 'Farming mpw18',
        select: { key: 'mode', value: 'mpw18', default: 'mpw18' },
        options: [
          ...loadouts.options('mpw18', () => stageChoices(18)),
        ],
      },
      {
        type: 'dialog', label: 'Farming mpw4',
        // Only once configured: its stage chosen.
        select: { key: 'mode', value: 'mpw4', default: 'mpw18', disabled: () => !loadouts.stage('mpw4') },
        options: [
          ...loadouts.options('mpw4', () => stageChoices(4)),
        ],
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
        type: 'dialog', label: 'Agent mode',
        select: { key: 'mode', value: 'agent', default: 'mpw18' },
        options: [],
      },
      {
        // Saved on change. mpw4 only once its stage is chosen (as its radio
        // button); never the mine.
        type: 'choice', key: 'defaultMode', label: 'Mode par défaut',
        choices: () => [
          { value: 'mpw18', label: api.tr('Farming mpw18') },
          ...(loadouts.stage('mpw4') || defaultMode() === 'mpw4'
            ? [{ value: 'mpw4', label: api.tr('Farming mpw4') }] : []),
          { value: 'free', label: api.tr('Jeu libre') },
          { value: 'agent', label: api.tr('Agent mode') },
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
          disabled: () => (farm.answer?.mode ?? mode()) === defaultMode()
            || (m < 0 && !Number.isFinite(farm.answer?.until)),
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
          const request = farm.answer?.setup_request;
          if (request) return { label: 'Appliquer la configuration',
            disabled: () => Boolean(farm.applying), run: () => applySetup(request) };
          return farm.answer ? watchdog?.retry(farm.answer.mode) ?? null : null;
        },
        value: () => {
          if (farm.applying) return api.tr('Application demandée…');
          if (farm.error) return api.tr(farm.error);
          if (mode() === 'mine' && !Number(api.setting('mineFloor'))) return api.tr('Choisis l’étage et la zone');
          const answer = farm.answer;
          if (!answer) return '…';
          if (answer.hold) {
            return api.tr('{mode} · en attente : tu joues · nouvel essai dans {seconds} s',
              { mode: api.tr(MODE_NAMES[answer.hold.mode] ?? answer.hold.mode), seconds: holdLeft() });
          }
          if (answer.setup_result?.result === 'failed' && answer.setup_result.mode === answer.mode
              && Number.isFinite(answer.setup_result.at) && Date.now() / 1000 - answer.setup_result.at >= 0
              && Date.now() / 1000 - answer.setup_result.at <= 120 && answer.setup_result.message_t) return api.tr(answer.setup_result.message_t);
          if (answer.setup_blocker_t) return api.tr(answer.setup_blocker_t);
          if (answer.setup_result?.result === 'failed') return api.tr('Configuration demandée non vérifiée');
          const warning = (gold) => (gold === false ? ` ⚠ ${api.tr('plus de parchemin doré')}` : '');
          const looked = watchdog?.line(answer.mode) ?? '';
          if (answer.mode === 'mine') return api.tr(answer.mine?.message_t || 'Mine') + warning(answer.mine?.gold) + looked;
          // mpw4 farming: the gateway's gold scroll check (gold, mpw4 only).
          return api.tr(answer.message_t || 'Farming mpw18') + warning(answer.gold) + looked;
        },
      },
      { type: 'status', label: 'Intention', visible: () => Boolean(activeIntention()),
        value: () => {
          const intent = activeIntention();
          return intent ? api.tr('Vers {destination} · {purpose}', {
            destination: api.tr(destinationName(intent)), purpose: api.tr(intent.purpose_t),
          }) : '';
        } },
      ...(stage ? [stage] : []),
    ],
    onSetting: (key, value) => {
      loadouts.onSetting(key, value);
      if (key === 'mode' || key === 'defaultMode') farm.chosen = Date.now();
      if (key === 'mode' && value !== defaultMode() && value !== farm.answer?.mode) {
        farm.answer = { ...farm.answer, until: Date.now() / 1000 + TIMED_MINUTES * 60 };
      }
      if (['mode', 'defaultMode', 'mineFloor', 'mineArea'].includes(key)) {
        farm.error = null;
        sendMode();
      }
    },
    dispose: () => {
      loadouts.dispose();
      untap?.();
      window.clearTimeout(farm.timer);
    },
  };
}
