// The loadout of a farming mode (mpw18, mpw4): the Battle settings preset
// (I to V), the soul weapon and its engraving variant, chosen in that
// mode's dialog of page_mode.js (options(mode)) and saved in the gateway
// (POST /loadout). The weapons and their variants come from the gateway
// (GET /engravings, GET /engraving?id=N, from engravings.json); the
// variant's grid is drawn read-only (a 'grid' option), with the pieces it needs. Nothing is
// equipped or placed in the game yet.

const PRESETS = ['I', 'II', 'III', 'IV', 'V'];
// The sheet's piece colours as CSS colours; the gold variants' pieces
// have none and take these in turn.
const FILLS = { red: '#e0453a', blue: '#3b82f6', purple: '#9b5de5', green: '#3fb950', yellow: '#f2c230' };
const TURN = ['#e0453a', '#3b82f6', '#9b5de5', '#3fb950', '#f2c230', '#f08c2e', '#8b5a2b'];
// The weapons' soul colours.
const DOTS = { green: '🟢', blue: '🔵', red: '🔴' };

const ENGLISH = {
  'Préréglage de combat': 'Battle settings preset',
  'Soul Weapon': 'Soul Weapon',
  'Gravure': 'Engraving',
  'Grille': 'Grid',
  'Pièces nécessaires': 'Pieces needed',
  'Source': 'Source',
  'Attention': 'Warning',
  'Enregistrer': 'Save',
  'Enregistré': 'Saved',
  'Équipement de combat': 'Battle loadout',
  'feuille de l’utilisateur': 'the user’s sheet',
  'wiki : même grille (captures)': 'wiki: same grid (screenshots)',
  'wiki : même grille (joueurs)': 'wiki: same grid (players)',
  'wiki : grille différente': 'wiki: another grid',
  'wiki : pas de grille': 'wiki: no grid',
  'grille à vérifier en jeu d’abord': 'grid to check in game first',
  'rien': 'nothing',
  'pas encore': 'not yet',
};

const WIKI = {
  'screenshots-agree': 'wiki : même grille (captures)',
  'community-agrees': 'wiki : même grille (joueurs)',
  'screenshots-differ': 'wiki : grille différente',
  'community-differs': 'wiki : grille différente',
  none: 'wiki : pas de grille',
};

export default function loadoutFeature(api) {
  api.addTranslations(ENGLISH);
  const data = { list: null, weapons: {}, asking: new Set(), saved: null, error: {} };
  const loadList = async () => {
    data.list = await api.get('/engravings').catch(() => null);
    api.refresh();
  };
  const loadSaved = async () => {
    data.saved = (await api.get('/loadout').catch(() => null))?.loadouts ?? null;
    api.refresh();
  };
  loadList();
  loadSaved();

  // What a selector shows: this browser's choice once made (null: never
  // touched here; '' chosen empty), else the loadout saved on the server,
  // so that a browser without local settings shows, and keeps, what is saved.
  const touched = (mode, field) => api.setting(`${mode}${field}`) !== null;
  const fromServer = (mode, field) => {
    const part = data.saved?.[mode];
    if (field === 'Preset') return part?.preset ?? '';
    if (field === 'Weapon') return part?.soul_weapon ? String(part.soul_weapon.id) : '';
    // The saved variant only goes with the saved weapon.
    return part?.soul_weapon && value(mode, 'Weapon') === String(part.soul_weapon.id) ? part.soul_weapon.variant : '';
  };
  const value = (mode, field) => (touched(mode, field) ? api.setting(`${mode}${field}`) : fromServer(mode, field));
  // A choice shows its first entry while untouched: the server's value goes first.
  const firstSaved = (mode, field, choices) => {
    const saved = touched(mode, field) ? '' : fromServer(mode, field);
    const index = saved ? choices.findIndex((choice) => choice.value === saved) : -1;
    return index > 0 ? [choices[index], ...choices.slice(0, index), ...choices.slice(index + 1)] : choices;
  };

  // The chosen weapon's pattern and variants, asked once.
  const weapon = (mode) => {
    const id = Number(value(mode, 'Weapon')) || null;
    if (!id) return null;
    if (!(id in data.weapons) && !data.asking.has(id)) {
      data.asking.add(id);
      api.get(`/engraving?id=${id}`).catch(() => null).then((answer) => {
        data.weapons[id] = answer;
        data.asking.delete(id);
        api.refresh();
      });
    }
    return data.weapons[id] ?? null;
  };
  const variant = (mode) => {
    const name = value(mode, 'Variant');
    return weapon(mode)?.variants.find((v) => v.name === name) ?? null;
  };

  const presetChoices = (mode) => firstSaved(mode, 'Preset', [
    { value: '', label: api.tr('— choisir —') }, ...PRESETS.map((p) => ({ value: p, label: p })),
  ]);
  const weaponChoices = (mode) => firstSaved(mode, 'Weapon', [
    { value: '', label: api.tr('— choisir —') },
    ...(data.list?.weapons ?? []).filter((w) => w.grid).map((w) => ({
      value: String(w.id), label: `${DOTS[w.colour] ?? ''} ${w.stage} · ${w.name}`.trim(),
    })),
  ]);
  const variantChoices = (mode) => firstSaved(mode, 'Variant', [
    { value: '', label: api.tr('— choisir —') },
    ...(weapon(mode)?.variants ?? []).map((v) => ({
      value: v.name, label: v.placeable ? v.name : `${v.name} ⚠`,
    })),
  ]);
  // The grid's rows: the pieces' colours, 'empty' for an empty cell,
  // null for a cell that is not part of the grid.
  const gridRows = (mode) => {
    const entry = weapon(mode);
    const chosen = variant(mode);
    if (!entry || !chosen) return [];
    const colour = {};
    chosen.pieces.forEach((piece, index) => {
      for (const [r, c] of piece.cells) colour[`${r},${c}`] = FILLS[piece.colour] ?? TURN[index % TURN.length];
    });
    const active = new Set(entry.cells.map(([r, c]) => `${r},${c}`));
    return Array.from({ length: entry.grid }, (_, row) => Array.from({ length: entry.grid }, (__, col) => {
      const key = `${row},${col}`;
      return colour[key] ?? (active.has(key) ? 'empty' : null);
    }));
  };
  const needed = (mode) => {
    const chosen = variant(mode);
    if (!chosen) return '—';
    const names = data.list?.shapes ?? {};
    return Object.entries(chosen.needed).map(([shape, count]) => `${count} × ${names[shape] ?? shape} (${shape})`)
      .join(', ') || api.tr('rien');
  };
  const source = (mode) => {
    const entry = weapon(mode);
    if (!entry) return '—';
    return [
      api.tr(entry.source === 'user-sheet' ? 'feuille de l’utilisateur' : entry.source),
      api.tr(WIKI[entry.wiki_check] ?? entry.wiki_check),
    ].filter(Boolean).join(', ');
  };
  // Only what must be done before placing: the confidence of the data
  // stays in engravings.json and the README.
  const warnings = (mode) => {
    const entry = weapon(mode);
    if (!entry || !variant(mode)) return [];
    return entry.wiki_check === 'community-differs' ? [api.tr('grille à vérifier en jeu d’abord')] : [];
  };
  const saved = (mode) => {
    if (data.error[mode]) return data.error[mode];
    const part = data.saved?.[mode];
    if (!part || (!part.preset && !part.soul_weapon)) return api.tr('pas encore');
    const what = part.soul_weapon ? `${part.weapon} (${part.soul_weapon.variant})` : '';
    return [part.preset, what].filter(Boolean).join(' · ');
  };
  const save = async (mode) => {
    // Only what was chosen in this browser: a field left out keeps the
    // server's value (POST /loadout). An empty choice clears it; a weapon
    // without its variant yet is not a choice.
    const body = { mode };
    if (touched(mode, 'Preset')) body.preset = api.setting(`${mode}Preset`) || null;
    if (touched(mode, 'Weapon') || touched(mode, 'Variant')) {
      const chosen = variant(mode);
      if (!value(mode, 'Weapon')) body.soul_weapon = null;
      else if (chosen) body.soul_weapon = { id: weapon(mode).id, variant: chosen.name };
    }
    const result = await api.post('/loadout', body).catch(() => null);
    data.error[mode] = result?.ok ? null : (result?.body?.error ?? (result ? `HTTP ${result.status}` : '…'));
    if (result?.ok) data.saved = result.body.loadouts;
    api.refresh();
  };

  return {
    // The options of a mode's dialog, in page_mode.js.
    options: (mode) => [
      {
        type: 'choice', key: `${mode}Preset`, label: 'Préréglage de combat', choices: () => presetChoices(mode),
      },
      { type: 'choice', key: `${mode}Weapon`, label: 'Soul Weapon', choices: () => weaponChoices(mode) },
      {
        type: 'choice', key: `${mode}Variant`, label: 'Gravure',
        visible: () => Boolean(value(mode, 'Weapon')), choices: () => variantChoices(mode),
      },
      { type: 'grid', label: 'Grille', visible: () => Boolean(variant(mode)), rows: () => gridRows(mode) },
      { type: 'status', label: 'Pièces nécessaires', visible: () => Boolean(variant(mode)), value: () => needed(mode) },
      { type: 'status', label: 'Source', visible: () => Boolean(weapon(mode)), value: () => source(mode) },
      {
        type: 'status', label: 'Attention', visible: () => warnings(mode).length > 0,
        value: () => `⚠ ${warnings(mode).join(' ; ')}`,
      },
      { type: 'action', label: 'Équipement de combat', button: 'Enregistrer', run: () => save(mode) },
      { type: 'status', label: 'Enregistré', value: () => saved(mode) },
    ],
  };
}
