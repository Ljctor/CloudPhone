// Inventory layout uses observations only. A catalogue crop is a historical
// example, never evidence of current possession, rarity or awakening.
const NEVER = 'never read';
const equipment = new Set(['weapons', 'accessories', 'classes']);
const rarity = (item) => String(item.rarity ?? '').toLowerCase();
export function inventoryTables(screen, current = () => screen) {
  const kind = screen.inventory?.kind ?? ({ spirit: 'spirits', familiar: 'familiars', equipment_relic: 'relics', black_orb: 'black_orb', black_orb_accessory: 'black_orb' }[screen.screen]);
  if (!equipment.has(kind) && !['spirits', 'familiars', 'black_orb', 'relics'].includes(kind)) return [];
  const items = () => current().inventory?.items ?? [];
  const examples = () => current().examples?.length ? current().examples : [current().example].filter(Boolean);
  const image = (item) => {
    const source = item?.source;
    const example = examples().find((entry) => entry.url?.split('/').at(-1) === source?.capture?.replace(/\.png$/, ''));
    if (!example || !Array.isArray(source?.box) || source.box.length !== 4) return null;
    // Catalogue boxes are in the original capture's pixel coordinates.
    // Legacy inventory sources were measured on 480 × 1040 captures.
    return { url: example.url, box: source.box, width: source.width ?? 480, height: source.height ?? 1040 };
  };
  const cell = (item, label = item?.name ?? NEVER) => {
    const parts = [];
    if (item?.level != null) parts.push(`Lv.${item.level}`);
    if (item?.enhancement != null) parts.push(`+${item.enhancement}`);
    if (Number.isFinite(item?.stars)) parts.push(`${item.stars} ★`);
    const fraction = item?.displayed_fraction;
    if (fraction?.numerator != null && fraction?.denominator != null)
      parts.push(`${fraction.numerator}/${fraction.denominator}`);
    const bonuses = [
      { role: 'primary', ...(item?.primary_bonus ?? (kind === 'relics' ? { display_text: NEVER } : {}) ) },
      { role: 'inheritance', ...(item?.inheritance_bonus ?? (kind === 'relics' ? { display_text: NEVER } : {}) ) },
      ...(item?.bonuses ?? []),
    ].filter((bonus) => bonus.display_text != null);
    return { label, image: image(item), value: parts.join(' · ') || NEVER, bonuses };
  };
  const empty = (label) => cell(null, label);
  const table = (suffix, label, rows, historical = false) => ({
    type: 'inventory-table', key: `inventory-${screen.screen}-${suffix}`, label,
    rows,
    caption: () => {
      if (!historical) return NEVER;
      const dates = [...new Set(examples().map((entry) => entry.captured).filter(Boolean))];
      return ['Relevé historique · possession actuelle non confirmée',
        ...dates.map((stamp) => new Date(stamp * 1000).toLocaleString())].join(' · ');
    },
  });
  const totals = table('totals', 'Bonus cumulés', () => [{ label: 'Total', cells: [empty('Bonus')] }]);
  if (kind === 'black_orb') return [table('elements', 'Black Orb · éléments', () => [{ label: 'Éléments',
    cells: items().length ? items().map((item) => cell(item)) : [empty(NEVER)] }], true)];
  if (kind === 'relics') {
    const first = ['Extra Dmg', 'Crit', 'HP'];
    const layoutKey = (item) => item.layout_key ?? item.name;
    return [table('relics', 'Relics', () => {
      const rest = items().filter((item) => !first.includes(layoutKey(item)));
      return [{ label: '1', cells: first.map((key) => {
        const item = items().find((candidate) => layoutKey(candidate) === key);
        return cell(item, item?.name ?? key);
      }) },
        ...Array.from({ length: Math.ceil(rest.length / 3) }, (_, index) => ({
          label: `${index + 2}`, cells: rest.slice(index * 3, index * 3 + 3).map((item) => cell(item)),
        }))];
    }, true)];
  }
  if (equipment.has(kind)) {
    return [totals,
      table('featured', 'Pièce équipée · capture', () => [{ label: 'Équipé',
        cells: [cell(items().find((item) => item.equipped === true))] }], true),
      table('rarities', screen.label ?? kind, () => ['Mythic', 'Legendary', 'Epic'].map((name) => ({
        label: name,
        cells: [4, 3, 2, 1].map((grade) => cell(items().find((item) => item.grade === grade &&
          (rarity(item) === name.toLowerCase() || (name === 'Legendary' && item.appearance === 'red'))), `Grade ${grade}`)),
      })), true),
    ];
  }
  if (kind === 'spirits') {
    const named = ['Loar', 'Sala', 'Noah', 'Zappy', 'Mum', 'Todd', 'Luga', 'Kart', 'Radeon', 'Ark', 'Herb', 'Bo'];
    const best = (name) => items().filter((item) => item.name === name)
      .sort((a, b) => (b.stars ?? -1) - (a.stars ?? -1) || (b.enhancement ?? -1) - (a.enhancement ?? -1))[0];
    return [totals, table('partners', 'Esprits', () => [named.slice(0, 3), named.slice(3, 6), named.slice(6)]
      .map((names, index) => ({ label: `${index + 1}`, cells: names.map((name) => cell(best(name), name)) })), true),
      table('reserves', 'Réserves', () => ['Legendary', 'Epic'].map((name) => ({ label: name,
        cells: items().filter((item) => rarity(item) === name.toLowerCase() && (!named.includes(item.name) || best(item.name) !== item))
          .map((item) => cell(item)) })).map((row) => ({ ...row, cells: row.cells.length ? row.cells : [empty(NEVER)] })), true)];
  }
  return [table('altar', 'Altar · Familiers', () => [{ label: 'Altar',
    cells: [1, 2, 3, 4, 5, 6].map((slot) => {
      const item = items().find((candidate) => candidate.altar_slot === slot);
      return cell(item, item?.name ?? `${slot}`);
    }) }], true),
    table('reserves', 'Réserves · étoiles décroissantes', () => [{ label: 'Réserves',
      cells: items().filter((item) => !item.altar_slot && Number.isFinite(item.stars))
        .sort((a, b) => b.stars - a.stars).map((item) => cell(item)) }]
      .map((row) => ({ ...row, cells: row.cells.length ? row.cells : [empty(NEVER)] })), true)];
}
