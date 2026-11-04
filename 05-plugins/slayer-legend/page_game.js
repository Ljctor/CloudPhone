// Account progression is grouped by topic, independently of menu paths.
// Current selection, equipped loadouts and battle state stay outside this view.
// Values fade from white to light blue with observation age; timestamps
// stay separate so the settings renderer can keep them grey at the right.
// Asked at load, then every 10 s while a row shows. rows(options, at): puts the sections into
// the plugin's options list at index at, once the gateway answered.
import { inventoryTables } from './page_inventory.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { PROGRESSION_ICONS } from './page_progression_icons.js';
import { shortNumber } from './page_numbers.js';
import { freshnessColour } from './page_freshness.js';
const PIECE = '#d9a441';
const EVERY = 10000;

export default function gameFeature(api, { resourceOptions = [], displayOptions = [] } = {}) {
  api.addTranslations?.({ 'Vue d’ensemble': 'Overview', 'Niveau': 'Level',
    'Forest of Circulation · étage le plus haut atteint': 'Highest Forest of Circulation',
    'Training Cave · étage le plus haut atteint': 'Highest Training Cave' });
  const game = { answer: null, at: 0, busy: false, list: null, start: 0, count: 0 };
  const time = (seen) => {
    const date = new Date(seen * 1000), today = new Date(Date.now());
    const old = date.toDateString() !== today.toDateString();
    return date.toLocaleString([], { ...(old ? { day: '2-digit', month: '2-digit',
      ...(date.getFullYear() !== today.getFullYear() ? { year: '2-digit' } : {}) } : {}),
      hour: '2-digit', minute: '2-digit' });
  };
  const shown = (row) => {
    const value = row.value;
    if (row.shown === 'lower_bound') return Number.isInteger(Number(value)) ? `> ${Number(value) - 1}` : `≥ ${value}`;
    if (row.shown === 'percent') return `${Math.round(value * 100)} %`;
    if (row.shown === 'switch') return api.tr(value === 'on' ? 'Activé' : 'Désactivé');
    if (value && typeof value === 'object') return shortNumber(value) ?? '';
    return String(value);
  };
  const text = (row) => {
    if (row.value === null || row.value === undefined) return 'never read';
    return shown(row);
  };
  const resourceText = (row) => {
    if (row.value == null) return 'never read';
    if (row.field === 'cubes') return String(typeof row.value === 'object' ? row.value.text ?? row.value.value : row.value);
    return shortNumber(row.value) ?? 'never read';
  };
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
  const transientField = (field) => /selected|equipped|preset|variant|engraving|progress|region|^stage$|^mine_/.test(field);
  const transientDetail = (detail) => /sélection|selected|équipé|equipped|onglet|\btab\b|actions visibles|boutons visibles|section companion|promotion affichée|défilement observé|emplacement|grille|^arme$/i.test(detail.label)
    || /sélectionnée|selected|équipés$/i.test(String(detail.value));
  const fieldRows = (screen) => (screen.fields ?? []).filter((field) => !transientField(field.field)).map((field) => (field.shown === 'grid' ? {
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
    const provenance = () => (screenOf(screen.screen) ?? screen).details_provenance;
    const capturedAt = () => provenance() ? provenance().captured : (screenOf(screen.screen) ?? screen).example?.captured;
    const subject = () => provenance()?.subject ??
      (screenOf(screen.screen) ?? screen).details?.find((row) => ['Arme sélectionnée', 'Arme'].includes(row.label))?.value;
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
      if (!detail.label || transientDetail(detail) || screen.screen === 'character_enhance' && detail.label === 'Niveau' || summaries.has(detail.label) || detail.value === null ||
          detail.value === undefined || !String(detail.value).trim()) return [];
      return [{
        type: 'status', key: `scan-${screen.screen}-${index}`, label: `${subject() ? `${subject()} · ` : ''}${api.tr(detail.label)}`,
        ...observed(() => ({ value: detail.value, seen: capturedAt() })),
        value: () => screenOf(screen.screen)?.details?.[index]?.value ?? detail.value,
        title: () => [api.tr('Capture d’exemple · relevé historique'), subject(),
          capturedAt() ? new Date(capturedAt() * 1000).toLocaleString() : api.tr('Date de capture inconnue')].filter(Boolean).join(' · '),
      }];
    });
    return details;
  };

  const inventoryRows = (screen) => {
    const tables = inventoryTables(screen, () => screenOf(screen.screen) ?? screen);
    if (tables.length) return tables.map((table) => table.key.endsWith('-featured') ? {
      ...table, key: table.key.replace(/-featured$/, '-observed'), label: 'Objet observé',
      rows: () => table.rows().map((row) => ({ ...row, label: 'Objet' })),
    } : table);
    const inventory = screen.inventory;
    if (!inventory) return [];
    if (inventory.status === 'never_read') {
      return [{ type: 'status', key: `inventory-${screen.screen}-unread`,
        label: inventory.kind === 'classes' ? 'Classes' : screen.label,
        value: () => 'never read', muted: () => true }];
    }
    if (inventory.kind === 'promotion_ranks' && inventory.ranks?.length) {
      const rows = [];
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
    return [];
  };
  const categories = [
    ['overview', 'Vue d’ensemble', 'character'], ['enhance', 'Enhance - Growing Knowledge', 'character'],
    ['growth', 'Growth - Latent Power', 'character'], ['companions', 'Companions', 'companion'],
    ['beasts', 'Beasts', 'companion'], ['weapons', 'Weapons', 'weapon'],
    ['soul-weapons', 'Soul Weapons', 'weapon'], ['accessories', 'Accessories', 'equipment'],
    ['classes', 'Classes', 'character'], ['black-orb', 'Black Orb', 'black_orb'], ['spirit', 'Spirit', 'equipment'],
    ['familiars', 'Familiars', 'skill'], ['skills', 'Skills', 'skill'],
    ['constellations', 'Constellations', 'companion'], ['memory-tree', 'Memory Tree', 'companion'],
    ['relics', 'Relics', 'equipment'], ['summon', 'Summon', 'shop'],
  ];
  const categoryOf = (screen) => {
    const id = screen.screen;
    if (/growing_knowledge/.test(id)) return 'enhance';
    if (/constell/.test(id)) return 'constellations';
    if (/memory/.test(id)) return 'memory-tree';
    if (/latent|dragon_power|dragon_spark/.test(id)) return 'growth';
    if (id === 'character_promotion') return 'overview';
    if (id === 'character_class') return 'classes';
    if (id.startsWith('character_enhance')) return 'enhance';
    if (id.startsWith('character_growth')) return 'growth';
    if (id.startsWith('beast')) return 'beasts';
    if (id.startsWith('companion')) return 'companions';
    if (id.startsWith('soul_weapon')) return 'soul-weapons';
    if (id === 'equipment_weapon' || id === 'weapon_detail') return 'weapons';
    if (id.startsWith('equipment_accessor')) return 'accessories';
    if (id.startsWith('black_orb')) return 'black-orb';
    if (id.startsWith('spirit')) return 'spirit';
    if (id.startsWith('familiar')) return 'familiars';
    if (id.startsWith('skill')) return 'skills';
    if (id.startsWith('equipment_relic')) return 'relics';
    if (id.startsWith('shop_summon')) return 'summon';
    return null;
  };
  const progression = (fields) => game.answer?.screens?.flatMap((screen) => screen.fields ?? [])
    .find((row) => fields.includes(row.field) && row.value != null);
  const overview = (key) => {
    if (key === 'level') {
      const fact = progression(['account_level', 'player_level']);
      if (fact) return fact;
      const screen = screenOf('character_enhance'), detail = screen?.details?.find((row) => row.label === 'Niveau');
      return { value: detail?.value ?? null, seen: screen?.example?.captured, historical: true };
    }
    if (key === 'promotion') {
      const fact = progression(['promotion_rank', 'account_promotion']);
      if (fact) return fact;
      const screen = screenOf('character_promotion');
      const rank = screen?.inventory?.ranks?.filter((row) => row.status === 'complete').at(-1);
      return { value: rank?.name ?? null, shown: 'lower_bound', seen: screen?.example?.captured, historical: true };
    }
    if (key === 'foc' || key === 'cave') {
      const ids = key === 'foc' ? ['highest_foc', 'highest_forest_of_circulation'] : ['highest_training_cave'];
      const fact = progression(ids); if (fact) return fact;
      const screen = screenOf(key === 'foc' ? 'dungeon_forest' : 'dungeon_training');
      const detail = screen?.details?.find((row) => row.label === (key === 'foc' ? 'CLEAR visible' : 'État visible'));
      const match = key === 'foc' ? /^(?:\d+\s*(?:à|–|-)\s*)?(\d+)$/.exec(String(detail?.value ?? ''))
        : /Area\s+(\d+)\s+MAX\s+CLEAR/i.exec(String(detail?.value ?? ''));
      const example = key === 'foc' ? screen?.examples?.find((row) => /dungeon_forest_scroll(?:_1)?$/.test(row.url)) : screen?.example;
      return { value: match ? Number(match[1]) : null, shown: 'lower_bound', seen: example?.captured, historical: true };
    }
    return progression({ highest: ['highest'], foc: ['highest_foc', 'highest_forest_of_circulation'],
      cave: ['highest_training_cave'] }[key]) ?? { value: null };
  };
  const overviewRows = () => [['level', 'Niveau'], ['promotion', 'Promotion'], ['highest', 'Stage le plus haut atteint'],
    ['foc', 'Forest of Circulation · étage le plus haut atteint'], ['cave', 'Training Cave · étage le plus haut atteint']].map(([key, label]) => ({
      type: 'status', key: `progression-${key}`, label,
      value: () => text(overview(key)), ...observed(() => overview(key)),
      title: () => overview(key).historical ? api.tr('Capture d’exemple · relevé historique') : '',
      visible: () => { ask(); return true; },
    }));
  const sections = () => {
    const rows = [
      { type: 'section', key: 'overlay', label: 'Overlay', depth: 1, folded: true }, ...resourceOptions,
      ...displayOptions.map((option) => option.type === 'section' ? { ...option, depth: 2 } : option),
      ...resourceRows(),
      { type: 'section', key: 'game-state', label: 'Progression', depth: 1, folded: true }];
    for (const [id, label, icon] of categories) {
      rows.push({ type: 'section', key: `progression-${id}`, label, depth: 2, folded: true, icon: PROGRESSION_ICONS[id] });
      const content = id === 'overview' ? overviewRows() : [];
      for (const screen of game.answer?.screens ?? []) {
        if (categoryOf(screen) !== id) continue;
        content.push(...fieldRows(screen), ...detailRows(screen), ...inventoryRows(screen));
      }
      if (id === 'enhance' && !game.answer?.screens?.some((screen) => /growing_knowledge/.test(screen.screen))) {
        content.push({ type: 'status', key: 'progression-growing-knowledge', label: 'Growing Knowledge',
          value: () => 'never read' });
      }
      if (id === 'growth' && !game.answer?.screens?.some((screen) => /latent/.test(screen.screen))) {
        content.push({ type: 'status', key: 'progression-latent-power', label: 'Latent Power',
          value: () => 'never read' });
      }
      if (id === 'growth') for (const field of ['dragon_power', 'dragon_spark']) {
        const current = () => game.answer?.resources?.find((row) => row.field === field) ?? { value: null };
        content.push({ type: 'status', key: `progression-${field}`, label: current().label ??
          (field === 'dragon_power' ? 'Dragon Power' : 'Dragon Spark'),
          value: () => resourceText(current()), ...observed(current) });
      }
      rows.push(...(content.length ? content : [{ type: 'status', label, value: () => 'never read' }]));
    }
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
