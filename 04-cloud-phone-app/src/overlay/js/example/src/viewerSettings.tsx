// The page's settings, kept by the gateway for every browser (GET and POST
// /api/v1/settings), and the options panel's rows for them (language,
// touch marker, folding the bar). Read at load, each change sent at once:
// no save button. Earlier versions kept them in this browser
// (localStorage): what the gateway does not hold yet is sent to it once,
// then the browser's copy is removed. document.documentElement's
// data-settings says where they are: loading, saving, saved, failed.
import { useEffect, useState } from 'react';
import { postFetch, postHeaders } from './api';
import { LANGUAGES, defaultLanguage, setLanguage, tr } from './i18n';
import { pageLog } from './logs';
import { DEFAULT_SETTINGS, SETTINGS_KEY, migration, sentChange, serverSettings, withChange } from './pageSettings';
import { styles } from './styles';

const URL = '/api/v1/settings';
// The settings as last rendered, for the readers outside React (the bar's fold).
let current = { ...DEFAULT_SETTINGS };

export function loadSettings() {
  return current;
}

function mark(state) {
  document.documentElement.dataset.settings = state;
}

// The settings earlier versions kept in this browser, or null.
function browserCopy() {
  try {
    const text = window.localStorage.getItem(SETTINGS_KEY);
    if (text === null) return null;
    try {
      return JSON.parse(text);
    } catch {
      return {};
    }
  } catch {
    return null;
  }
}

function forgetBrowserCopy() {
  try {
    window.localStorage.removeItem(SETTINGS_KEY);
  } catch {
    // Blocked storage: nothing was kept there either.
  }
}

// One POST at a time, in order: a later change never lands first.
let queue = Promise.resolve();
let pending = 0;
let failed = false;

function send(change) {
  pending += 1;
  mark('saving');
  const sent = queue.then(async () => {
    const response = await postFetch(URL, { method: 'POST', headers: postHeaders(), body: JSON.stringify(change) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }).then((answer) => {
    failed = false;
    return answer;
  }, (error) => {
    failed = true;
    pageLog('warning', `Settings not saved on the server: ${error?.message ?? error}`);
    return null;
  });
  queue = sent.finally(() => {
    pending -= 1;
    if (!pending) mark(failed ? 'failed' : 'saved');
  });
  return sent;
}

async function fetchSettings() {
  try {
    const response = await fetch(URL, { cache: 'no-store' });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

// [settings, updateSettings(change), loaded]. Sets the page's language, so
// call it before any tr() of the render. loaded: the gateway's settings
// came (or could not be had: the defaults then).
export function useViewerSettings() {
  const [settings, setSettings] = useState(current);
  const [loaded, setLoaded] = useState(false);
  current = settings;
  // Before any tr() of this render: null means the browser's language.
  setLanguage(settings.language ?? defaultLanguage());
  useEffect(() => {
    let cancelled = false;
    mark('loading');
    (async () => {
      let answer = await fetchSettings();
      const old = browserCopy();
      if (answer?.available && old !== null) {
        const change = migration(old, answer.settings);
        if (change) {
          pageLog('normal', `Settings moved from this browser to the server: ${Object.keys(change).join(', ')}`);
          answer = (await send(change)) ?? answer;
        }
        forgetBrowserCopy();
      }
      if (cancelled) return;
      const loadedSettings = serverSettings(answer);
      current = loadedSettings;
      setSettings(loadedSettings);
      setLoaded(true);
      if (!pending) mark(answer ? 'saved' : 'failed');
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  const updateSettings = (change) => {
    const before = current;
    const sent = sentChange(before, change);
    current = withChange(before, change);
    if (Object.keys(sent).some((key) => key !== 'plugins') || Object.keys(sent.plugins ?? {}).length) {
      // A key set back to undefined is removed on the server.
      send(Object.fromEntries(Object.entries(sent).map(([key, value]) => [key, value ?? null])));
    }
    setSettings(current);
  };
  return [settings, updateSettings, loaded];
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
