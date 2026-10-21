// The emerald and diamond counters: cut at their comma or rewritten, on
// this screen only (counter_rewrite.js). Options: their two sections;
// debug: whether each counter is found on the screen.
import { COUNTERS, modeOf, startEmeraldMask } from './counter_rewrite.js';

// enabled(): the plugin is on (no counter is rewritten while it is off).
export default function counters(api, { enabled = () => true } = {}) {
  const emerald = { found: false, problem: null };
  let stopEmerald = null;
  const setEmerald = (on) => {
    if (on && !stopEmerald) stopEmerald = startEmeraldMask(api, emerald);
    if (!on && stopEmerald) {
      stopEmerald();
      stopEmerald = null;
    }
  };
  setEmerald(Boolean(modeOf(api, COUNTERS.emerald)) && enabled());
  const diamond = { found: false, problem: null };
  let stopDiamond = null;
  const setDiamond = (on) => {
    if (on && !stopDiamond) stopDiamond = startEmeraldMask(api, diamond, COUNTERS.diamond);
    if (!on && stopDiamond) {
      stopDiamond();
      stopDiamond = null;
    }
  };
  setDiamond(Boolean(modeOf(api, COUNTERS.diamond)) && enabled());

  return {
    options: [
      { type: 'section', key: 'emerald', label: 'Émeraudes', folded: true },
      {
        type: 'choice', key: 'emeraldMode', label: 'Compteur d’émeraudes',
        choices: [
          { value: '', label: 'Inchangé' },
          { value: 'cut', label: 'Coupé à la virgule' },
          { value: 'rewrite', label: 'Réécrit' },
        ],
      },
      {
        type: 'number', key: 'emeraldCount', label: 'Nombre affiché (vide : après la virgule)', placeholder: '86',
        visible: () => modeOf(api, COUNTERS.emerald) === 'rewrite',
      },
      { type: 'section', key: 'diamond', label: 'Diamants', folded: true },
      {
        type: 'choice', key: 'diamondMode', label: 'Compteur de diamants',
        choices: [
          { value: '', label: 'Inchangé' },
          { value: 'cut', label: 'Coupé à la virgule' },
          { value: 'rewrite', label: 'Réécrit' },
        ],
      },
      {
        type: 'number', key: 'diamondCount', label: 'Nombre affiché (vide : après la virgule)', placeholder: '786',
        visible: () => modeOf(api, COUNTERS.diamond) === 'rewrite',
      },
    ],
    debug: [
      {
        type: 'status', label: 'Détection des émeraudes',
        visible: () => Boolean(stopEmerald),
        value: () => (emerald.found ? api.tr('détecté')
          : emerald.problem ? `${api.tr('non détecté')} (${emerald.problem})` : api.tr('non détecté')),
      },
      {
        type: 'status', label: 'Détection des diamants',
        visible: () => Boolean(stopDiamond),
        value: () => (diamond.found ? api.tr('détecté')
          : diamond.problem ? `${api.tr('non détecté')} (${diamond.problem})` : api.tr('non détecté')),
      },
    ],
    // After the plugin was turned on or off.
    update: () => {
      setEmerald(Boolean(modeOf(api, COUNTERS.emerald)) && enabled());
      setDiamond(Boolean(modeOf(api, COUNTERS.diamond)) && enabled());
    },
    onSetting: (key, value) => {
      if (key === 'emeraldMode') setEmerald(Boolean(value) && enabled());
      if (key === 'diamondMode') setDiamond(Boolean(value) && enabled());
    },
    dispose: () => {
      setEmerald(false);
      setDiamond(false);
    },
  };
}
