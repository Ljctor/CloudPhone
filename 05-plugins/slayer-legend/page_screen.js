// The game's screen and the stage it farms, asked to the gateway only
// while the options panel shows them: each render asks again once the
// last answer is 3 s old. stage: the stage's row, under the mode's État;
// debug: the detected screen. known(): the last stage number read, for
// the mode's stage lists.

// The battle shows behind most screens: never named, but the panel open
// over it is, by its tab's name in the game.
const PANELS = {
  character_enhance: 'Growth', skill: 'Skill', equipment_weapon: 'Equipment', companion: 'Companion',
  adventure_map: 'Adventure', shop_summon: 'Shop',
};
const SCREENS = {
  title: 'Écran titre', save: 'Choix de la sauvegarde', battle: 'Aucun panneau ouvert',
  saver: 'Économie d’énergie', other: 'Autre (menu, chargement…)',
  menu: 'Menu du jeu', away: 'Autre application',
};
// The stage's soul colour, as a coloured dot.
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };
// Where earlier versions kept the last stage read in this browser: sent
// once to the gateway, which keeps the game's state itself, then removed.
const STORE = 'cloudphone-slayer-legend-stage';

function moveOldStage(api) {
  let old = null;
  try {
    old = Number(window.localStorage.getItem(STORE)) || null;
    window.localStorage.removeItem(STORE);
  } catch {
    old = null;
  }
  if (old) api.get(`/stages?known=${old}`).catch(() => null);
}

export default function screenFeature(api) {
  const screen = { answer: null, at: 0, busy: false, timer: null };
  let remembered = null;
  moveOldStage(api);
  const watchScreen = () => {
    if (screen.busy || Date.now() - screen.at < 3000) return;
    screen.busy = true;
    api.get('/screen').catch(() => null).then((answer) => {
      if (answer?.stage?.checked) remembered = answer.stage.number;
      Object.assign(screen, { answer, at: Date.now(), busy: false });
      api.refresh();
      window.clearTimeout(screen.timer);
      screen.timer = window.setTimeout(api.refresh, 3000);
    });
  };

  return {
    known: () => remembered,
    // The stage being farmed, one row under the mode's État (page_mode.js):
    // « 920 · 🔴 · Arme · 5 par vague », or « inconnu ».
    stage: {
      type: 'status', label: 'Stage',
      visible: () => {
        watchScreen();
        return Boolean(screen.at);
      },
      value: () => {
        const stage = screen.answer?.stage;
        if (!stage?.number) return api.tr('inconnu');
        return [
          String(stage.number),
          DOTS[stage.soul_colour],
          stage.drop ? api.tr(stage.drop === 'A' ? 'Accessoire' : 'Arme') : null,
          stage.monsters_per_wave ? api.tr('{n} par vague', { n: stage.monsters_per_wave }) : null,
        ].filter(Boolean).join(' · ');
      },
    },
    options: [],
    debug: [
      {
        type: 'status', label: 'Écran détecté',
        value: () => {
          watchScreen();
          const name = screen.answer?.screen;
          if (!screen.at) return '…';
          const panel = PANELS[screen.answer?.panel];
          if (name === 'battle' && panel) return panel;
          return api.tr(name ? SCREENS[name] ?? name : 'Pas de capture d’écran');
        },
      },
    ],
    dispose: () => {
      window.clearTimeout(screen.timer);
    },
  };
}
