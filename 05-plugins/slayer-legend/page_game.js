// The game's state and archived examples from GET /game are nested by their
// path through the game's menus, with resources in their own section.
// Values fade from white to light blue with observation age; timestamps
// stay separate so the settings renderer can keep them grey at the right.
// Asked at load, then every 10 s while a row shows. rows(options, at): puts the sections into
// the plugin's options list at index at, once the gateway answered.
import { RESOURCE_ICONS } from './page_resources.js';
import { SCREEN_ICONS } from './page_screen_icons.js';
import { shortNumber } from './page_numbers.js';
import { freshnessColour } from './page_freshness.js';
const PIECE = '#d9a441';
const EVERY = 10000;

export default function gameFeature(api, { resourceOptions = [], displayOptions = [] } = {}) {
  const game = { answer: null, at: 0, busy: false, list: null, start: 0, count: 0 };
  const time = (seen) => new Date(seen * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const shown = (row) => {
    const value = row.value;
    if (row.shown === 'lower_bound') return `≥ ${value}`;
    if (row.shown === 'percent') return `${Math.round(value * 100)} %`;
    if (row.shown === 'switch') return api.tr(value === 'on' ? 'Activé' : 'Désactivé');
    if (value && typeof value === 'object') return shortNumber(value) ?? '';
    return String(value);
  };
  const text = (row) => {
    if (row.value === null || row.value === undefined) return 'never read';
    return shown(row);
  };
  const resourceText = (row) => row.value === null || row.value === undefined ? 'never read' :
    shortNumber(row.value) ?? 'never read';
  const observed = (current) => ({
    timestamp: () => current().seen ? time(current().seen) : '',
    color: () => current().value == null ? '#8a919c' :
      freshnessColour(current().seen ? Date.now() / 1000 - current().seen : 600),
  });
  const ask = () => {
    if (game.busy || Date.now() - game.at < EVERY) return;
    game.busy = true;
    api.get('/game').catch(() => null).then((answer) => {
      Object.assign(game, { at: Date.now(), busy: false });
      if (!answer) return;
      game.answer = answer;
      place();
      api.refresh();
    });
  };
  // The current answer's row of field, read at each render.
  const screenOf = (screen) => game.answer?.screens?.find((row) => row.screen === screen);
  const rowOf = (screen, field) => screenOf(screen)?.fields?.find((f) => f.field === field);
  const resourceRows = () => [
    { type: 'section', key: 'resources', label: 'Ressources', folded: false },
    ...(game.answer?.resources ?? []).map((field) => {
      const current = () => game.answer?.resources?.find((row) => row.field === field.field) ?? field;
      return {
        type: 'status', label: field.label, icon: RESOURCE_ICONS[field.field],
        compact: true,
        ...observed(current),
        title: () => current().seen ? api.tr('vu à {time}', { time: time(current().seen) }) : 'never read',
        visible: () => { ask(); return true; },
        value: () => resourceText(current()),
      };
    }),
  ];
  const accessPath = (screen) => {
    const known = {
      battle: [],
      skill: ['Skill'],
      companion: ['Companion'],
      beast: ['Companion', 'Beasts'],
      companion_advancement: ['Companion', 'Advancement'],
      adventure_map: ['Adventure'],
      dungeon_map: ['Adventure', 'Dungeon'],
      stage_select: ['Select Region'],
      scroll: ['Scroll'],
      quest_panel: ['Quest'],
      equipment_weapon: ['Equipment', 'Weapon'],
      equipment_accessories: ['Equipment', 'Accessories'],
      equipment_relic: ['Equipment', 'Relic'],
      spirit: ['Equipment', 'Spirit'],
      black_orb: ['Equipment', 'Accessories', 'Black Orb'],
      black_orb_accessory: ['Equipment', 'Accessories', 'Black Orb', 'Accessory card'],
      soul_weapon: ['Equipment', 'Weapon', 'Soul Weapon'],
      soul_weapon_engraving: ['Equipment', 'Weapon', 'Soul Weapon', 'Engraving'],
      mine_list: ['Adventure', 'Dungeon', 'Closed Mine'],
      mine_area: ['Adventure', 'Dungeon', 'Closed Mine', 'Area'],
      mine_feathers: ['Adventure', 'Dungeon', 'Closed Mine', 'Area', 'Feathers'],
      mine_fight: ['Adventure', 'Dungeon', 'Closed Mine', 'Area', 'Feathers', 'Fight'],
      adventure_story_ellie: ['Adventure', 'Slayer Story', 'Sub', 'Ellie episodes'],
    }[screen.screen];
    if (known) return known;
    const aliases = { 'Skill panel': 'Skill', 'Quest panel': 'Quest', Beast: 'Beasts' };
    const path = [];
    for (const raw of screen.path ?? [screen.label]) {
      if (raw === 'Combat') continue;
      const [prefix, tail] = raw.split(': ', 2);
      if (tail === undefined) {
        const label = aliases[prefix] ?? prefix;
        if (path.at(-1) !== label) path.push(label);
        continue;
      }
      const parent = aliases[prefix] ?? prefix;
      const seen = path.indexOf(parent);
      if (seen >= 0) path.length = seen + 1;
      else path.push(parent);
      const label = aliases[tail] ?? tail;
      if (label !== parent && path.at(-1) !== label) path.push(label);
    }
    return path;
  };
  const fieldRows = (screen) => (screen.fields ?? []).map((field) => (field.shown === 'grid' ? {
      type: 'grid', label: field.label,
      visible: () => {
        ask();
        return Boolean(rowOf(screen.screen, field.field)?.value);
      },
      rows: () => (rowOf(screen.screen, field.field)?.value?.cells ?? []).map((cells) => cells.map(
        (cell) => (cell === 'piece' ? PIECE : cell === 'empty' ? 'empty' : null))),
    } : {
      type: 'status', label: field.label,
      visible: () => {
        ask();
        return true;
      },
      value: () => text(rowOf(screen.screen, field.field) ?? field),
      ...observed(() => rowOf(screen.screen, field.field) ?? field),
    }));
  const archived = (screen) => observed(() => ({
    value: true, seen: (screenOf(screen.screen) ?? screen).example?.captured,
  }));
  const detailRows = (screen) => {
    const summaries = new Set();
    if (screen.inventory?.items?.length) {
      ['Armes visibles', 'Accessoires visibles', 'Grades visibles', 'Niveau affiché sur les armes']
        .forEach((label) => summaries.add(label));
    }
    if (screen.inventory?.kind === 'classes') summaries.add('Classes');
    if (screen.inventory?.kind === 'promotion_ranks') {
      summaries.add('Promotions observées');
      summaries.add('Promotion affichée');
      screen.inventory.ranks?.forEach((rank) => summaries.add(rank.name));
    }
    const details = (screen.details ?? []).flatMap((detail, index) => {
      if (!detail.label || summaries.has(detail.label) || detail.value === null ||
          detail.value === undefined || !String(detail.value).trim()) return [];
      return [{
        type: 'status', key: `scan-${screen.screen}-${index}`, label: detail.label,
        ...archived(screen),
        value: () => screenOf(screen.screen)?.details?.[index]?.value ?? detail.value,
      }];
    });
    if (!details.length) return details;
    if (screen.inventory?.items?.length || screen.inventory?.kind === 'promotion_ranks') return details;
    return [{ type: 'status', key: `scan-date-${screen.screen}`, label: 'Relevé historique',
      value: () => {
        const captured = screenOf(screen.screen)?.example?.captured;
        return captured ? new Date(captured * 1000).toLocaleString() : 'Capture enregistrée';
      } }, ...details];
  };
  const inventoryRows = (screen) => {
    const inventory = screen.inventory;
    if (!inventory) return [];
    if (inventory.status === 'never_read') {
      return [{ type: 'status', key: `inventory-${screen.screen}-unread`,
        label: inventory.kind === 'classes' ? 'Classes' : screen.label,
        value: () => 'never read', muted: () => true }];
    }
    if (inventory.kind === 'promotion_ranks' && inventory.ranks?.length) {
      const rows = [
        { type: 'status', key: `inventory-${screen.screen}-date`, label: 'Relevé historique',
          muted: () => true,
          value: () => {
            const captured = screenOf(screen.screen)?.example?.captured;
            return captured ? new Date(captured * 1000).toLocaleString() : 'Capture enregistrée';
          } },
        { type: 'status', key: `inventory-${screen.screen}-selected`,
          label: 'Promotion sélectionnée', ...archived(screen), value: () => screenOf(screen.screen)?.inventory?.selected ??
            inventory.selected ?? 'never read' },
      ];
      for (const rank of inventory.ranks) {
        rows.push({ type: 'status', key: `inventory-${screen.screen}-${rank.name}`,
          label: rank.name, compact: true, ...archived(screen),
          value: () => {
            const current = screenOf(screen.screen) ?? screen;
            const status = current.inventory?.ranks?.find((row) => row.name === rank.name)?.status ?? rank.status;
            const label = status === 'complete' ? api.tr('Terminé') :
              status === 'challenge' ? api.tr('Défi') : status ?? 'never read';
            const detail = current.details?.find((row) => row.label === rank.name)?.value;
            const extra = typeof detail === 'string' ? detail.split(' · ').slice(1).join(' · ') : '';
            return extra ? `${label} · ${extra}` : label;
          } });
      }
      return rows;
    }
    if (!['weapons', 'accessories'].includes(inventory.kind) || !inventory.items?.length) return [];
    const colours = { grey: 'Gris', green: 'Vert', orange: 'Orange', purple: 'Violet',
      red: 'Rouge', blue: 'Bleu', gold: 'Or' };
    const rows = [{ type: 'status', key: `inventory-${screen.screen}-date`, label: 'Relevé historique',
      muted: () => true,
      title: () => api.tr('x/5 : progression affichée par le jeu ; possession non confirmée'),
      value: () => {
        const captured = screenOf(screen.screen)?.example?.captured;
        return captured ? new Date(captured * 1000).toLocaleString() : 'Capture enregistrée';
      } }];
    const groups = new Map();
    for (const item of inventory.items) {
      const appearance = item.appearance ?? 'unknown';
      if (!groups.has(appearance)) groups.set(appearance, []);
      groups.get(appearance).push(item);
    }
    for (const [appearance, items] of groups) {
      rows.push({ type: 'section', key: `inventory-${screen.screen}-${appearance}`,
        label: api.tr(colours[appearance] ?? appearance), depth: accessPath(screen).length + 2,
        folded: true });
      for (const item of items) {
        const current = () => screenOf(screen.screen)?.inventory?.items?.find((row) => row.id === item.id) ?? item;
        rows.push({ type: 'status', key: `inventory-${screen.screen}-${item.id}`,
          label: item.name || (item.grade == null ? 'Case équipée' : `Grade ${item.grade}`),
          compact: true, ...archived(screen),
          title: () => api.tr('Relevé historique · x/5 : progression affichée, possession non confirmée'),
          value: () => {
            const found = current();
            const progress = found.displayed_fraction;
            const parts = [];
            if (found.enhancement != null) parts.push(`+${found.enhancement}`);
            if (progress?.numerator != null && progress?.denominator != null) {
              parts.push(`${progress.numerator}/${progress.denominator}`);
            }
            if (found.equipped) parts.push(api.tr('Équipé'));
            return parts.join(' · ') || 'never read';
          } });
      }
    }
    return rows;
  };
  const examplesOf = (screen) => {
    const current = screenOf(screen.screen) ?? screen;
    return current.examples?.length ? current.examples : current.example?.url ? [current.example] : [];
  };
  const captureRow = (screen) => ({
    type: 'capture', key: `capture-${screen.screen}`, label: 'Capture',
    examples: () => examplesOf(screen),
    visible: () => { ask(); return examplesOf(screen).length > 0; },
  });
  const sections = () => {
    const rows = [...resourceRows(),
      { type: 'section', key: 'analysis', label: 'Analyse', depth: 1, folded: true },
      ...resourceOptions,
      { type: 'section', key: 'display', label: 'Affichage', depth: 1, folded: true },
      ...displayOptions.map((option) => option.type === 'section' ? { ...option, depth: 2 } : option),
      { type: 'section', key: 'game-state', label: 'État du jeu', depth: 1, folded: true }];
    const root = { children: new Map(), screens: [] };
    for (const screen of game.answer?.screens ?? []) {
      // A scanned example is useful even when its OCR reader is pending.
      if (!screen.fields?.length && !screen.example?.url && !screen.examples?.length &&
          !screen.details?.length && !screen.inventory) continue;
      const path = accessPath(screen);
      let node = root;
      for (const label of path) {
        if (!node.children.has(label)) node.children.set(label, { label, children: new Map(), screens: [] });
        node = node.children.get(label);
      }
      node.screens.push(screen);
    }
    const showScreen = (screen) => {
      rows.push(...fieldRows(screen));
      rows.push(...detailRows(screen));
      rows.push(...inventoryRows(screen));
      if (screen.example?.url || screen.examples?.length) rows.push(captureRow(screen));
    };
    const showChildren = (node, path = []) => {
      for (const child of node.children.values()) {
        const at = [...path, child.label];
        const iconKey = { Quest: 'quest', Scroll: 'scroll', 'Select Region': 'stage_select',
          Weapon: 'weapon', 'Black Orb': 'black_orb' }[child.label] ?? child.label.toLowerCase();
        rows.push({ type: 'section', key: child.screens.length ? `game-${child.screens[0].screen}` :
          `game-path-${at.join('/')}`, label: child.label, depth: at.length + 1, folded: true,
          icon: SCREEN_ICONS[iconKey] });
        child.screens.forEach(showScreen);
        showChildren(child, at);
      }
    };
    root.screens.forEach(showScreen);
    showChildren(root);
    return rows;
  };
  // Rebuild when a newly captured screen appears; values keep reading the
  // latest answer without losing the user's folded-section preferences.
  const place = () => {
    if (!game.list || !game.answer) return;
    const made = sections();
    game.list.splice(game.start, game.count, ...made);
    game.count = made.length;
  };
  ask();
  return {
    rows: (options, at) => {
      Object.assign(game, { list: options, start: at });
      place();
    },
    options: [],
  };
}
