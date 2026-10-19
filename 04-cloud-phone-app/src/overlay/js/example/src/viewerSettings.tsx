// Per-viewer page settings, kept in this browser only, and the options
// panel's rows for them (language, touch marker, folding the bar).
import { useState } from 'react';
import { LANGUAGES, defaultLanguage, setLanguage, tr } from './i18n';
import { SETTINGS_KEY, settingsFrom, withChange } from './pageSettings';
import { styles } from './styles';

export function loadSettings() {
  let stored = null;
  try {
    stored = window.localStorage.getItem(SETTINGS_KEY);
  } catch {
    // Blocked storage: the defaults.
  }
  return settingsFrom(stored);
}

function saveSettings(settings) {
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Private mode or blocked storage: settings last for this page only.
  }
}

// [settings, updateSettings(change)]. Sets the page's language, so call it
// before any tr() of the render.
export function useViewerSettings() {
  const [settings, setSettings] = useState(loadSettings);
  // Before any tr() of this render: null means the browser's language.
  setLanguage(settings.language ?? defaultLanguage());
  const updateSettings = (change) => setSettings((current) => {
    const next = withChange(current, change);
    saveSettings(next);
    return next;
  });
  return [settings, updateSettings];
}

export function ViewerOptions({ settings, updateSettings }) {
  const toggle = (label, key) => (
    <label key={key} style={styles.infoRow}>
      <span style={styles.infoLabel}>{tr(label)}</span>
      <input type="checkbox" checked={settings[key]}
        onChange={(event) => updateSettings({ [key]: event.target.checked })} />
    </label>
  );
  return (
    <>
      <label style={styles.infoRow}>
        <span style={styles.infoLabel}>{tr('Langue')}</span>
        <select value={settings.language ?? defaultLanguage()} style={styles.select}
          onChange={(event) => updateSettings({ language: event.target.value })}>
          {LANGUAGES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
        </select>
      </label>
      {toggle('Afficher le curseur', 'touchMarker')}
      {toggle('Replier la barre 3 s après l’entrée en plein écran', 'autoFold')}
    </>
  );
}
