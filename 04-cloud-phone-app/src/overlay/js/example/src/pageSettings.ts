// The page's settings, as plain data. No React, no DOM: the gateway keeps
// them for every browser (GET/POST /api/v1/settings, viewerSettings.tsx).
// SETTINGS_KEY: where earlier versions kept them in this browser, read
// once to move them to the gateway.
export const SETTINGS_KEY = 'cloudphone.settings';
export const DEFAULT_SETTINGS = {
  touchMarker: true, autoFold: true, barDocked: false, language: null,
  // Plugin options: { <plugin id>: { <key>: true } }.
  plugins: {},
};

// The settings from what was stored (JSON text, or null when nothing was
// or storage is blocked): stored values over the defaults; the defaults
// alone when the text does not parse.
export function settingsFrom(stored) {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(stored || '{}') };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

// The settings from the gateway's answer over the defaults.
export function serverSettings(answer) {
  const settings = answer?.settings;
  if (!settings || typeof settings !== 'object') return { ...DEFAULT_SETTINGS };
  return { ...DEFAULT_SETTINGS, ...settings, plugins: { ...(settings.plugins ?? {}) } };
}

// What this browser still holds from earlier versions (stored: the old
// key's parsed object) that the gateway has not: the change that moves it
// there, or null when there is nothing to move. A value the gateway
// already holds wins over the browser's.
export function migration(stored, server) {
  if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return null;
  const change = {};
  for (const [key, value] of Object.entries(stored)) {
    if (key === 'plugins' || value === null || value === undefined) continue;
    if (!(key in (server ?? {}))) change[key] = value;
  }
  const plugins = {};
  for (const [id, options] of Object.entries(stored.plugins ?? {})) {
    if (!options || typeof options !== 'object') continue;
    const held = server?.plugins?.[id] ?? {};
    const moved = Object.fromEntries(Object.entries(options)
      .filter(([key, value]) => value !== null && value !== undefined && !(key in held)));
    if (Object.keys(moved).length) plugins[id] = moved;
  }
  if (Object.keys(plugins).length) change.plugins = plugins;
  return Object.keys(change).length ? change : null;
}

// The change to send for a settings change: plugins' options as only the
// keys that changed, so that two browsers changing two options keep both.
export function sentChange(settings, change) {
  if (!change.plugins) return change;
  const plugins = {};
  for (const [id, options] of Object.entries(change.plugins)) {
    const before = settings.plugins?.[id] ?? {};
    const changed = Object.fromEntries(Object.entries(options ?? {}).filter(([key, value]) => before[key] !== value));
    if (Object.keys(changed).length) plugins[id] = changed;
  }
  return { ...change, plugins };
}

export function withChange(settings, change) {
  return { ...settings, ...change };
}

// The information panel's foldable sections (the logs): folded at first.
export function sectionFolded(settings, id) {
  return settings.foldedSections?.[id] ?? true;
}
