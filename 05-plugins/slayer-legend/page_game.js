// The game's state as the gateway keeps it (GET /game, features/game.py:
// every capture scanned): the screens with readable values are nested by
// their path through the game's menus, with resources in their own section.
// A value not read again since
// the game was stopped or relaunched is greyed out. Asked at load, then
// every 10 s while a row shows. rows(options, at): puts the sections into
// the plugin's options list at index at, once the gateway answered.
import { RESOURCE_ICONS } from './page_resources.js';
const PIECE = '#d9a441';
const EVERY = 10000;

export default function gameFeature(api, { resourceOptions = [] } = {}) {
  const game = { answer: null, at: 0, busy: false, list: null, start: 0, count: 0 };
  const time = (seen) => new Date(seen * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const shown = (row) => {
    const value = row.value;
    if (row.shown === 'percent') return `${Math.round(value * 100)} %`;
    if (row.shown === 'switch') return api.tr(value === 'on' ? 'Activé' : 'Désactivé');
    if (value && typeof value === 'object') return String(value.text ?? '');
    return String(value);
  };
  const text = (row) => {
    if (row.pending) return api.tr('lecteur en attente de capture');
    if (row.value === null || row.value === undefined) return api.tr('jamais lu');
    return `${shown(row)} · ${api.tr('vu à {time}', { time: time(row.seen) })}`;
  };
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
  const rowOf = (screen, field) => game.answer?.screens?.find((s) => s.screen === screen)
    ?.fields.find((f) => f.field === field);
  const resourceRows = () => [
    { type: 'section', key: 'resources', label: 'Ressources', folded: false },
    ...(game.answer?.resources ?? []).map((field) => {
      const current = () => game.answer?.resources?.find((row) => row.field === field.field) ?? field;
      return {
        type: 'status', label: field.label,
        visible: () => { ask(); return true; },
        value: () => [{ icon: RESOURCE_ICONS[field.field], size: 12, text: text(current()) }],
        muted: () => !current().verified,
      };
    }),
    ...resourceOptions.map((option) => option.type === 'section' ? { ...option, depth: 2 } : option),
  ];
  const accessPath = (screen) => ({
    battle: [],
    stage_select: ['Select Region'],
    soul_weapon: ['Equipment', 'Weapon', 'Soul Weapon'],
    soul_weapon_engraving: ['Equipment', 'Weapon', 'Soul Weapon', 'Engraving'],
    mine_list: ['Adventure', 'Dungeon', 'Closed Mine'],
  }[screen.screen] ?? (screen.path ?? [screen.label]).filter((part) => part !== 'Combat')
    .flatMap((part) => part.split(': ').filter(Boolean)));
  const fieldRows = (screen) => screen.fields.map((field) => (field.shown === 'grid' ? {
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
      muted: () => {
        const row = rowOf(screen.screen, field.field);
        return Boolean(row && row.value !== null && !row.verified);
      },
    }));
  const sections = () => {
    const rows = [...resourceRows(),
      { type: 'section', key: 'game-state', label: 'État du jeu', depth: 1, folded: true }];
    const made = new Set();
    for (const screen of game.answer?.screens ?? []) {
      // A page with no reader has no game state to show. It should not
      // become an empty menu; its place is retained when a reader arrives.
      if (!screen.fields?.length) continue;
      const path = accessPath(screen);
      path.forEach((label, index) => {
        const id = path.slice(0, index + 1).join('/');
        if (made.has(id)) return;
        made.add(id);
        rows.push({ type: 'section', key: index === path.length - 1 ? `game-${screen.screen}` : `game-path-${id}`,
          label, depth: index + 2, folded: true });
      });
      rows.push(...fieldRows(screen));
    }
    return rows;
  };
  // The sections, once: readable screens and their fields are the gateway's.
  const place = () => {
    if (!game.list || game.count || !game.answer) return;
    const made = sections();
    game.list.splice(game.start, 0, ...made);
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
