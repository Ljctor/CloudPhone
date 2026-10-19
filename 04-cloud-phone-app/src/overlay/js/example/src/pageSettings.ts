// Per-viewer page settings, as plain data. No React, no DOM: the page
// keeps them in this browser (viewerSettings.tsx).
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

export function withChange(settings, change) {
  return { ...settings, ...change };
}
