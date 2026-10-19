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
import mode from './page_mode.js';
import screen from './page_screen.js';
import trace from './page_trace.js';

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
  const screenPart = screen(api);
  const modePart = mode(api, { known: screenPart.known });
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
  let modeDrawn = '';
  const showMode = (shown) => {
    if (!shown) {
      modeLabel.remove();
      modeDrawn = '';
      return;
    }
    if (!modeLabel.isConnected) api.layer.appendChild(modeLabel);
    const lines = modePart.overlay();
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

  const tracePart = trace(api);
  return {
    options: [
      ...screenPart.options,
      ...launchPart.options,
      ...modePart.options,
      { type: 'section', key: 'gold', label: 'Gold' },
      { type: 'status', label: 'Gold par seconde', value: goldText },
      {
        type: 'choice', key: 'goldOverlay', label: 'Overlay gold/s',
        choices: [{ value: 'on', label: 'Affiché' }, { value: 'off', label: 'Masqué' }],
      },
      ...tracePart.options,
      ...counterPart.options,
    ],
    onSetting: (key, value) => {
      counterPart.onSetting(key, value);
      if (key === 'goldOverlay') showGold();
      modePart.onSetting(key, value);
    },
    dispose: () => {
      counterPart.dispose();
      tracePart.dispose();
      launchPart.dispose();
      screenPart.dispose();
      modePart.dispose();
      window.clearTimeout(gold.timer);
      window.clearInterval(modeTick);
      modeLabel.remove();
    },
  };
}
