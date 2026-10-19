// Slayer Legend plugin, page side: loaded by the Cloud Phone page (see
// plugins.ts in part 04 for the API). Among its features:
// - "Lancer le jeu": the gateway starts the game and brings it to the
//   battle screen (TAP TO START, then Confirm on the latest save).
// - The emerald and diamond counters, on this screen only (nothing is sent to Android),
//   either cut at its comma ("284,086" shows "284"), or rewritten: covered
//   with the bar's colour and, in the game's font and colour at the game's
//   size for that many digits, either the digits after its comma (leading
//   zeros dropped) or a number the user chose are written over it.
// - "Enregistrer mes parcours" (on by default): each tap the user makes on
//   the game is sent to the gateway, which records the screen before and
//   after it, building a graph of the game's screens (never replayed).
import counters from './page_counters.js';
import launch from './page_launch.js';

const ENGLISH = {
  'Farmer la mine': 'Farm the mine',
  'Étage à farmer': 'Floor to farm',
  'Mode': 'Mode',
  'défaut': 'default',
  'Configuration : farming mpw18': 'Settings: mpw18 farming',
  'Configuration : farming mpw4': 'Settings: mpw4 farming',
  'Configuration : mine fermée': 'Settings: Closed Mine',
  'Arme, gravure, réglages de combat': 'Weapon, engraving, battle settings',
  'à venir': 'coming',
  'Plumes': 'Feathers',
  'Gold': 'Gold',
  'Gold par seconde': 'Gold per second',
  'Overlay gold/s': 'Gold/s overlay',
  'Affiché': 'Shown',
  'Masqué': 'Hidden',
  'pas encore mesuré': 'not measured yet',
  'non visible (économie d’énergie ?)': 'not visible (Power Saving Mode?)',
  'Farming mpw18 (par défaut)': 'mpw18 farming (default)',
  'Farming mpw4': 'mpw4 farming',
  'Farming mpw18': 'mpw18 farming',
  'Jeu libre': 'Free play',
  'Mine fermée': 'Closed Mine',
  'Configuration : jeu libre': 'Settings: free play',
  'Minuteur par défaut (minutes)': 'Default timer (minutes)',
  'Stage mpw18': 'mpw18 stage',
  'Stage mpw4': 'mpw4 stage',
  '— choisir —': '— choose —',
  'État': 'State',
  'Zone à farmer': 'Area to farm',
  'Minuteur': 'Timer',
  'Ajuster (minutes)': 'Adjust (minutes)',
  'plus de parchemin doré': 'no gold scroll',
  'Combat en cours, sans parchemin doré': 'Fighting, without the gold scroll',
  'Sans limite': 'No limit',
  'reste {time}': '{time} left',
  'Durée écoulée : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Time is up: "Repeat entry" unticked, the mine stops after this entry',
  'Durée écoulée : pas de relance': 'Time is up: no restart',
  'Durée écoulée, mais « Repeat entry » ne se décoche pas': 'Time is up, but "Repeat entry" does not untick',
  'Mine': 'Mine',
  'Surveillance de la mine': 'Watching the mine',
  'Combat en cours, parchemin doré actif': 'Fighting, gold scroll on',
  'Mine relancée': 'Mine started again',
  'Le jeu n’est pas au premier plan': 'The game is not in front',
  'Écran autre que la mine : rien à faire': 'Not a mine screen: nothing to do',
  'Parchemin doré pas vu depuis 5 minutes : pas de relance': 'Gold scroll not seen for 5 minutes: no restart',
  'Plus de parchemin doré : « Repeat entry » décoché, la mine s’arrête après cette entrée':
    'Gold scroll gone: "Repeat entry" unticked, the mine stops after this entry',
  'Plus de parchemin doré, mais « Repeat entry » ne se décoche pas': 'Gold scroll gone, but "Repeat entry" does not untick',
  'La relance a échoué 3 fois : relance la mine à la main': 'Restarting failed 3 times: start the mine by hand',
  'Choisis l’étage et la zone': 'Choose the floor and the area',
  'arrêtée': 'off',
  'Lancer le jeu': 'Launch the game',
  'Lancer': 'Launch',
  'Lancement': 'Launch',
  'Compteur d’émeraudes': 'Emerald counter',
  'Jeu': 'Game',
  'Mode et farming': 'Mode and farming',
  'Émeraudes': 'Emeralds',
  'Diamants': 'Diamonds',
  'Compteur de diamants': 'Diamond counter',
  'Inchangé': 'Unchanged',
  'Coupé à la virgule': 'Cut at the comma',
  'Réécrit': 'Rewritten',
  'Détection du compteur': 'Counter detection',
  'Nombre affiché (vide : après la virgule)': 'Number shown (empty: after the comma)',
  'détecté': 'detected',
  'non détecté': 'not detected',
  'Ouverture du jeu': 'Opening the game',
  'Écran titre touché, connexion': 'Title screen tapped, signing in',
  'Dernière sauvegarde confirmée, chargement': 'Latest save confirmed, loading',
  'Le jeu est sur l’écran de combat': 'The game is on the battle screen',
  'Sortie du mode économie d’énergie': 'Leaving Power Saving Mode',
  'Le mode économie d’énergie ne se ferme pas : touche son bouton à la main': 'Power Saving Mode does not close: tap its button by hand',
  'Écran inattendu : termine le lancement à la main': 'Unexpected screen: finish the launch by hand',
  'Le jeu n’a pas atteint l’écran de combat en 3 minutes': 'The game did not reach the battle screen in 3 minutes',
  'Android ne répond pas': 'Android does not answer',
  'Un lancement est déjà en cours': 'A launch is already running',
  'Écran détecté': 'Detected screen',
  'Écran titre': 'Title screen',
  'Choix de la sauvegarde': 'Save choice',
  'Combat': 'Battle',
  'Économie d’énergie': 'Power Saving',
  'Autre (menu, chargement…)': 'Other (menu, loading…)',
  'Pas de capture d’écran': 'No screenshot',
  'Menu du jeu': 'Game menu',
  'Autre application': 'Another app',
  'Stage sélectionné': 'Selected stage',
  'vu en mode économie d’énergie, à confirmer': 'seen in Power Saving Mode, to be confirmed',
  'inconnu : passe en mode économie d’énergie pour le lire': 'unknown: go to Power Saving Mode to read it',
  'Monstres par vague': 'Monsters per wave',
  'Équipement lâché': 'Equipment dropped',
  'Arme': 'Weapon',
  'Accessoire': 'Accessory',
  'Commun': 'Common',
  'Supérieur': 'Great',
  'Épique': 'Epic',
  'Légendaire': 'Legendary',
  'Couleur des âmes': 'Soul colour',
  'verte': 'green',
  'bleue': 'blue',
  'rouge': 'red',
  'déduite, non vérifiée': 'deduced, not checked',
  'Navigation': 'Navigation',
  'Enregistrer mes parcours': 'Record my paths',
  'Activé': 'On',
  'Désactivé': 'Off',
  'Parcours enregistrés': 'Recorded paths',
  '{nodes} écrans, {taps} appuis': '{nodes} screens, {taps} taps',
  'indisponible (passerelle sans dossier de données)': 'unavailable (the gateway has no data directory)',
};

export default function activate(api) {
  api.addTranslations(ENGLISH);
  const counterPart = counters(api);

  const launchPart = launch(api);
  // The game's screen, asked to the gateway only while the options panel
  // shows it: each render asks again once the last answer is 3 s old.
  const SCREENS = {
    title: 'Écran titre', save: 'Choix de la sauvegarde', battle: 'Combat',
    saver: 'Économie d’énergie', other: 'Autre (menu, chargement…)',
    menu: 'Menu du jeu', away: 'Autre application',
  };
  const GRADES = { Common: 'Commun', Great: 'Supérieur', Rare: 'Rare', Epic: 'Épique', Legendary: 'Légendaire' };
  const COLOURS = { green: 'verte', blue: 'bleue', red: 'rouge' };
  const stageRow = (label, value) => ({
    type: 'status', label, visible: () => Boolean(screen.answer?.stage?.name), value,
  });
  const screen = { answer: null, at: 0, busy: false, timer: null };
  // The last stage number read, kept in this browser so that the gateway
  // still knows it after a restart (it reads it only in Power Saving Mode).
  const STORE = 'cloudphone-slayer-legend-stage';
  let remembered = null;
  try {
    remembered = Number(window.localStorage.getItem(STORE)) || null;
  } catch {
    remembered = null;
  }
  const watchScreen = () => {
    if (screen.busy || Date.now() - screen.at < 3000) return;
    screen.busy = true;
    api.get(remembered ? `/screen?known=${remembered}` : '/screen').catch(() => null).then((answer) => {
      const number = answer?.stage?.checked ? answer.stage.number : null;
      if (number && number !== remembered) {
        remembered = number;
        try {
          window.localStorage.setItem(STORE, String(number));
        } catch {
          // Not kept: read again in Power Saving Mode.
        }
      }
      Object.assign(screen, { answer, at: Date.now(), busy: false });
      api.refresh();
      window.clearTimeout(screen.timer);
      screen.timer = window.setTimeout(api.refresh, 3000);
    });
  };

  // The mode (mpw18 farming by default, or a timed mode: mpw4 farming, free
  // play, the mine) runs in the gateway; this browser's
  // options are sent to it when they change, and on load if the gateway has
  // not been told since it started. Its state is asked every 10 s.
  const farm = { answer: null, timer: null, stages: null };
  // This browser's copy of when the timed mode ends (Unix seconds), as the
  // gateway last said; sent again after a gateway restart.
  const UNTIL = 'cloudphone-slayer-legend-mode-until';
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
  const mode = () => api.setting('mode') || 'mpw18';
  // Free play starts with this timer unless set in its dialog.
  const FREE_MINUTES = 60;
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
    farm.stages = await api.get(remembered ? `/stages?known=${remembered}` : '/stages').catch(() => null);
    api.refresh();
  };
  const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
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

  // Gold per second, measured by the gateway (a reading every 10 s, the
  // slope over 5 minutes), written top left under the mode in the gold
  // counter's own pixel font (from the gateway), outlined like the game.
  const gold = { answer: null, timer: null, font: null, line: '' };
  api.get('/gold-font').catch(() => null).then((font) => {
    gold.font = font;
    showGold();
  });
  // Lines of text on a canvas, `cell` CSS pixels per game pixel. Letters
  // without accents: the font has none.
  const drawText = (canvas, lines, cell) => {
    const plain = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const glyphLines = lines.map((text) => [...plain(text)].map((c) => gold.font.glyphs[c]).filter(Boolean));
    const rows = gold.font.height;
    // A game pixel of space between glyphs, one round the text for the
    // outline, two between lines.
    const widths = glyphLines.map((glyphs) => glyphs.reduce((sum, glyph) => sum + glyph[0].length + 1, 0) + 1);
    const width = Math.max(...widths);
    const height = lines.length * (rows + 2) + (lines.length - 1) * 2;
    const scale = cell * (window.devicePixelRatio || 1);
    canvas.width = Math.ceil(width * scale);
    canvas.height = Math.ceil(height * scale);
    canvas.style.width = `${width * cell}px`;
    canvas.style.height = `${height * cell}px`;
    const context = canvas.getContext('2d');
    for (const [colour, grow] of [['#000', 1], ['#ffa31a', 0]]) {
      context.fillStyle = colour;
      glyphLines.forEach((glyphs, line) => {
        const base = 1 + line * (rows + 4);
        let pen = 1;
        for (const glyph of glyphs) {
          glyph.forEach((row, y) => [...row].forEach((ink, x) => {
            if (ink === '#') {
              // Whole device pixels: fractional edges leave seams between cells.
              const left = Math.round((pen + x - grow) * scale);
              const top = Math.round((base + y - grow) * scale);
              context.fillRect(left, top, Math.round((pen + x + 1 + grow) * scale) - left,
                Math.round((base + y + 1 + grow) * scale) - top);
            }
          }));
          pen += glyph[0].length + 1;
        }
      });
    }
  };
  // The selected mode, under the player's level (top left), below it
  // "(défaut)" or the time left on the timer, then the gold per second.
  const modeLabel = document.createElement('canvas');
  modeLabel.style.cssText = 'position:absolute;image-rendering:pixelated;left:3%;top:5.6%';
  const MODE_NAMES = { mpw18: 'Farming mpw18', mpw4: 'Farming mpw4', free: 'Jeu libre', mine: 'Mine fermée' };
  let modeDrawn = '';
  const showMode = (shown) => {
    if (!shown) {
      modeLabel.remove();
      modeDrawn = '';
      return;
    }
    if (!modeLabel.isConnected) api.layer.appendChild(modeLabel);
    const current = farm.answer?.mode ?? mode();
    const seconds = Math.max(0, Math.round((farm.answer?.until ?? 0) - Date.now() / 1000));
    const two = (n) => String(n).padStart(2, '0');
    const time = seconds >= 3600
      ? `${Math.floor(seconds / 3600)}:${two(Math.floor(seconds / 60) % 60)}:${two(seconds % 60)}`
      : `${two(Math.floor(seconds / 60))}:${two(seconds % 60)}`;
    const lines = [
      api.tr(MODE_NAMES[current] ?? current).toUpperCase(),
      `(${(current === 'mpw18' || !farm.answer?.until ? api.tr('défaut') : time).toUpperCase()})`,
    ];
    if (gold.line) lines.push(gold.line);
    // As high as the level's text above it (8 game pixels, the screen
    // being 1040 of them high), not the gold counter's 13.
    const cell = api.layer.offsetHeight / 1040 * 8 / gold.font.height;
    const key = `${lines.join('|')}@${cell}`;
    if (key !== modeDrawn) {
      drawText(modeLabel, lines, cell);
      modeDrawn = key;
    }
  };
  const modeTick = window.setInterval(() => {
    if (modeLabel.isConnected) showMode(true);
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
    showMode(Boolean(fresh && gold.font));
  };
  const askGold = async () => {
    gold.answer = await api.get('/gold').catch(() => null);
    showGold();
    api.refresh();
    window.clearTimeout(gold.timer);
    gold.timer = window.setTimeout(askGold, 10000);
  };
  askGold();

  // Navigation trace: each tap on the game goes to the gateway, which
  // records the screens before and after it (screen name and a small grey
  // thumbnail, never a screenshot). On unless the user turned it off.
  // Fire and forget: a lost tap is only a missing edge.
  const tracing = () => api.setting('traceTaps') !== 'off';
  const stopTrace = api.onTap?.((tap) => {
    if (tracing()) api.post('/trace', tap).catch(() => null);
  });
  // The counts, asked only while the panel shows them, at most every 5 s.
  const traced = { answer: null, at: 0, busy: false };
  const watchTrace = () => {
    if (traced.busy || Date.now() - traced.at < 5000) return;
    traced.busy = true;
    api.get('/trace').catch(() => null).then((answer) => {
      Object.assign(traced, { answer, at: Date.now(), busy: false });
      api.refresh();
    });
  };

  return {
    options: [
      { type: 'section', key: 'game', label: 'Jeu' },
      {
        type: 'status', label: 'Écran détecté',
        value: () => {
          watchScreen();
          const name = screen.answer?.screen;
          if (!screen.at) return '…';
          return api.tr(name ? SCREENS[name] ?? name : 'Pas de capture d’écran');
        },
      },
      {
        type: 'status', label: 'Stage sélectionné',
        visible: () => Boolean(screen.at),
        value: () => {
          const stage = screen.answer?.stage;
          if (!stage?.number) return api.tr('inconnu : passe en mode économie d’énergie pour le lire');
          const text = `${stage.number}${stage.name ? ` · ${stage.name}` : ''}`;
          return stage.checked ? text : `${text} (${api.tr('vu en mode économie d’énergie, à confirmer')})`;
        },
      },
      stageRow('Monstres par vague', () => String(screen.answer.stage.monsters_per_wave ?? '–')),
      stageRow('Équipement lâché', () => {
        const stage = screen.answer.stage;
        const [grade, level] = String(stage.grade ?? '').split(' ');
        return `${api.tr(stage.drop === 'A' ? 'Accessoire' : 'Arme')}, ${api.tr(GRADES[grade] ?? grade)} ${level ?? ''}`.trim();
      }),
      stageRow('Couleur des âmes', () => {
        const stage = screen.answer.stage;
        if (!stage.soul_colour) return '–';
        const colour = api.tr(COLOURS[stage.soul_colour] ?? stage.soul_colour);
        return stage.soul_colour_confirmed ? colour : `${colour} (${api.tr('déduite, non vérifiée')})`;
      }),
      ...launchPart.options,
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
      { type: 'section', key: 'gold', label: 'Gold' },
      { type: 'status', label: 'Gold par seconde', value: goldText },
      {
        type: 'choice', key: 'goldOverlay', label: 'Overlay gold/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
      { type: 'section', key: 'navigation', label: 'Navigation', folded: true },
      {
        type: 'choice', key: 'traceTaps', label: 'Enregistrer mes parcours',
        choices: [{ value: 'on', label: 'Activé' }, { value: 'off', label: 'Désactivé' }],
      },
      {
        type: 'status', label: 'Parcours enregistrés',
        value: () => {
          watchTrace();
          const answer = traced.answer;
          if (!answer) return '…';
          if (!answer.enabled) return api.tr('indisponible (passerelle sans dossier de données)');
          return api.tr('{nodes} écrans, {taps} appuis', { nodes: answer.nodes, taps: answer.taps ?? answer.edges });
        },
      },
      ...counterPart.options,
    ],
    onSetting: (key, value) => {
      counterPart.onSetting(key, value);
      if (key === 'goldOverlay') showGold();
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
      counterPart.dispose();
      stopTrace?.();
      launchPart.dispose();
      window.clearTimeout(screen.timer);
      window.clearTimeout(farm.timer);
      window.clearTimeout(gold.timer);
      window.clearInterval(modeTick);
      modeLabel.remove();
    },
  };
}
