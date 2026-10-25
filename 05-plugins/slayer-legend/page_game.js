// The game's state as the gateway keeps it (GET /game, features/game.py:
// every capture scanned): one foldable section per screen of the game, a
// row per value with the time it was seen. A value not read again since
// the game was stopped or relaunched is greyed out. Asked at load, then
// every 10 s while a row shows. rows(options, at): puts the sections into
// the plugin's options list at index at, once the gateway answered.
import { RESOURCE_ICONS } from './page_resources.js';
const PIECE = '#d9a441';
const EVERY = 10000;

export default function gameFeature(api) {
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
        value: () => [{ icon: RESOURCE_ICONS[field.field], text: text(current()) }],
        muted: () => !current().verified,
      };
    }),
  ];
  const sections = () => [...resourceRows(), ...(game.answer?.screens ?? []).flatMap((screen) => [
    { type: 'section', key: `game-${screen.screen}`,
      label: (screen.path ?? [screen.label]).map((part) => api.tr(part)).join(' → '), folded: true },
    ...(screen.fields.length ? [] : [{ type: 'status', label: 'État',
      value: () => api.tr('lecteur en attente de capture') }]),
    ...screen.fields.map((field) => (field.shown === 'grid' ? {
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
    })),
  ])];
  // The sections, once: the screens and their fields are the gateway's.
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
