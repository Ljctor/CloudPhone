// The emerald and diamond counters: cut at their comma or rewritten, on
// this screen only (counter_rewrite.js). Options: their two sections.
import { COUNTERS, modeOf, startEmeraldMask } from './counter_rewrite.js';

export default function counters(api) {
  const emerald = { found: false, problem: null };
  let stopEmerald = null;
  const setEmerald = (on) => {
    if (on && !stopEmerald) stopEmerald = startEmeraldMask(api, emerald);
    if (!on && stopEmerald) {
      stopEmerald();
      stopEmerald = null;
    }
  };
  setEmerald(Boolean(modeOf(api, COUNTERS.emerald)));
  const diamond = { found: false, problem: null };
  let stopDiamond = null;
  const setDiamond = (on) => {
    if (on && !stopDiamond) stopDiamond = startEmeraldMask(api, diamond, COUNTERS.diamond);
    if (!on && stopDiamond) {
      stopDiamond();
      stopDiamond = null;
    }
  };
  setDiamond(Boolean(modeOf(api, COUNTERS.diamond)));

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
      {
        type: 'status', label: 'Détection du compteur',
        visible: () => Boolean(stopEmerald),
        value: () => (emerald.found ? api.tr('détecté')
          : emerald.problem ? `${api.tr('non détecté')} (${emerald.problem})` : api.tr('non détecté')),
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
      {
        type: 'status', label: 'Détection du compteur',
        visible: () => Boolean(stopDiamond),
        value: () => (diamond.found ? api.tr('détecté')
          : diamond.problem ? `${api.tr('non détecté')} (${diamond.problem})` : api.tr('non détecté')),
      },
    ],
    onSetting: (key, value) => {
      if (key === 'emeraldMode') setEmerald(Boolean(value));
      if (key === 'diamondMode') setDiamond(Boolean(value));
    },
    dispose: () => {
      setEmerald(false);
      setDiamond(false);
    },
  };
}
