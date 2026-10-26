// The plugins' stored options and folded sections, as plain data. No
// React, no DOM.

// The settings change that stores value under the plugin's key.
export function pluginOptionChange(settings, id, key, value) {
  return { plugins: { ...settings.plugins, [id]: { ...settings.plugins?.[id], [key]: value } } };
}

// A plugin's options cut into sub-sections at each { type: 'section', key,
// label, folded? }: [{ section (null first), options: [[option, index]] }].
export function optionParts(options) {
  const parts = [{ section: null, options: [] }];
  (options ?? []).forEach((option, index) => {
    if (option.type === 'section') parts.push({ section: option, options: [] });
    else parts[parts.length - 1].options.push([option, index]);
  });
  return parts;
}

// A section may declare depth (1 by default). Its children stay under it
// until the next section at the same or a shallower depth.
export function optionTree(options) {
  const root = { section: null, options: [], children: [] };
  const stack = [{ depth: 0, node: root }];
  (options ?? []).forEach((option, index) => {
    if (option.type !== 'section') {
      stack[stack.length - 1].node.options.push([option, index]);
      return;
    }
    const depth = Math.max(1, Math.min(Number(option.depth) || 1, stack.length));
    while (stack.length > depth) stack.pop();
    const node = { section: option, options: [], children: [] };
    stack[stack.length - 1].node.children.push(node);
    stack.push({ depth, node });
  });
  return root;
}

export function sectionFoldId(plugin, section) {
  return `${plugin.id}:${section.key ?? section.label}`;
}

// Folded as stored, else as the section says (its default state).
export function sectionFolded(settings, id, section) {
  return settings.foldedPlugins?.[id] ?? Boolean(section.folded);
}

// The settings change that stores id's folded state in settings[field].
export function foldedChange(settings, field, id, folded) {
  return { [field]: { ...settings[field], [id]: folded } };
}

// An option's field that may be a function of the plugin's state.
export function resolved(value) {
  return typeof value === 'function' ? value() : value;
}
