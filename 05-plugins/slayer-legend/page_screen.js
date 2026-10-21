// The game's screen and the stage it farms, asked to the gateway only
// while the options panel shows them: each render asks again once the
// last answer is 3 s old. Options: the "Jeu" section's stage rows; debug:
// the detected screen. known(): the last stage number read, for the
// mode's stage lists.

const SCREENS = {
  title: 'Écran titre', save: 'Choix de la sauvegarde', battle: 'Combat',
  saver: 'Économie d’énergie', other: 'Autre (menu, chargement…)',
  menu: 'Menu du jeu', away: 'Autre application',
};
const GRADES = { Common: 'Commun', Great: 'Supérieur', Rare: 'Rare', Epic: 'Épique', Legendary: 'Légendaire' };
const COLOURS = { green: 'verte', blue: 'bleue', red: 'rouge' };
// The last stage number read, kept in this browser so that the gateway
// still knows it after a restart (it reads it only in Power Saving Mode).
const STORE = 'cloudphone-slayer-legend-stage';

export default function screenFeature(api) {
  const stageRow = (label, value) => ({
    type: 'status', label, visible: () => Boolean(screen.answer?.stage?.name), value,
  });
  const screen = { answer: null, at: 0, busy: false, timer: null };
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

  return {
    known: () => remembered,
    options: [
      { type: 'section', key: 'game', label: 'Jeu' },
      {
        type: 'status', label: 'Stage sélectionné',
        visible: () => {
          watchScreen();
          return Boolean(screen.at);
        },
        value: () => {
          const stage = screen.answer?.stage;
          if (!stage?.number) return api.tr('inconnu');
          return `${stage.number}${stage.name ? ` · ${stage.name}` : ''}`;
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
        return colour;
      }),
    ],
    debug: [
      {
        type: 'status', label: 'Écran détecté',
        value: () => {
          watchScreen();
          const name = screen.answer?.screen;
          if (!screen.at) return '…';
          return api.tr(name ? SCREENS[name] ?? name : 'Pas de capture d’écran');
        },
      },
    ],
    dispose: () => {
      window.clearTimeout(screen.timer);
    },
  };
}
