import { LANGUAGES, defaultLanguage, language, setLanguage, tr } from './i18n';
import { coreOptions, memoryOptions, rendererOptions, sameSettings } from './emulatorSettings';
import { usePlugins } from './plugins';
import React, { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';
import {
  activePeerConnection, sendInputEvent, setViewerId,
} from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import Proto from '../../src/proto/emulator_controller_pb';

logger.setLevel('warn');

const TOOLBAR_WIDTH = 40;
const STATS_INTERVAL_MS = 1000;
// Touches and keys go over the emulator's own WebRTC data channels ("touch",
// "keyboard"): no HTTP request, no gRPC hop. HTTP through the gateway stays
// as the fallback while no channel is open. See docs/DEVELOPMENT.md.
const USE_DATA_CHANNEL = true;
// Give up showing the reconnect feedback if no frame arrives in this time.
const RECONNECT_FEEDBACK_MS = 15000;
// Android's display size until the gateway reports the real one.
const DEFAULT_DISPLAY = { width: 480, height: 1040 };

function viewportSize() {
  const viewport = window.visualViewport;
  return {
    width: Math.floor(viewport?.width || window.innerWidth),
    height: Math.floor(viewport?.height || window.innerHeight),
  };
}

// Largest Android screen that fits, with the toolbar either beside it or
// below it, whichever leaves the bigger screen. A phone whose shape matches
// Android's (e.g. 19.5:9) gets the full width with the toolbar below.
function fittedScreen(display = DEFAULT_DISPLAY, folded = false, docked = false) {
  const DEVICE_WIDTH = display.width;
  const DEVICE_HEIGHT = display.height;
  const viewport = viewportSize();
  // Fullscreen or folded bar: the screen takes the whole window and the bar
  // floats over it, so a phone shaped like Android uses every pixel. A
  // docked bar keeps its own space, even in fullscreen.
  if ((document.fullscreenElement && !docked) || folded) {
    const width = Math.max(1, Math.floor(Math.min(viewport.width,
      viewport.height * DEVICE_WIDTH / DEVICE_HEIGHT)));
    return { width, height: Math.floor(width * DEVICE_HEIGHT / DEVICE_WIDTH), toolbar: 'overlay' };
  }
  const fit = (availableWidth, availableHeight) => {
    const width = Math.max(1, Math.floor(Math.min(availableWidth,
      availableHeight * DEVICE_WIDTH / DEVICE_HEIGHT)));
    return { width, height: Math.floor(width * DEVICE_HEIGHT / DEVICE_WIDTH) };
  };
  const side = fit(viewport.width - TOOLBAR_WIDTH, viewport.height);
  const below = fit(viewport.width, viewport.height - TOOLBAR_WIDTH);
  return below.width > side.width ? { ...below, toolbar: 'below' } : { ...side, toolbar: 'side' };
}

function toggleFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch(() => {});
  } else {
    document.documentElement.requestFullscreen?.({ navigationUI: 'hide' }).catch(() => {});
  }
}

// Navigation-bar shapes as on Samsung One UI (chevron back, rounded-square
// home, three-bar recents) and Material icons (Apache 2.0), 24×24.
const ICONS = {
  back: <path d="M14.5 5.5L8 12l6.5 6.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />,
  home: <rect x="6" y="6" width="12" height="12" rx="4" fill="none" stroke="currentColor" strokeWidth="2" />,
  recents: <path d="M7.5 7v10M12 7v10M16.5 7v10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />,
  volumeDown: <path fill="currentColor" d="M18.5 12c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM5 9v6h4l5 5V4L9 9H5z" />,
  volumeUp: <path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />,
  power: <path fill="currentColor" d="M13 3h-2v10h2V3zm4.83 2.17l-1.42 1.42C17.99 7.86 19 9.81 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.19 1.01-4.14 2.58-5.42L6.17 5.17C4.23 6.82 3 9.26 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9c0-2.74-1.23-5.18-3.17-6.83z" />,
  fullscreen: <path fill="currentColor" d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />,
  // Fold/unfold the bar (Material expand_more / expand_less / chevron_right).
  fold: <path fill="currentColor" d="M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z" />,
  foldSide: <path fill="currentColor" d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />,
  unfold: <path fill="currentColor" d="M12 8l-6 6 1.41 1.41L12 10.83l4.59 4.58L18 14z" />,
  // Material "settings", drawn tiny next to the clickable metrics.
  cog: <path fill="currentColor" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />,
  refresh: <path fill="currentColor" d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" />,
};

function Icon({ name, spinning = false }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"
      style={spinning ? styles.spinningIcon : styles.icon}>
      {ICONS[name]}
    </svg>
  );
}

function pingColor(ms) {
  if (ms === null) return '#8a919c';
  if (ms < 60) return '#34c759';
  if (ms < 150) return '#ff9f0a';
  return '#ff453a';
}

function formatValue(value) {
  return value === null || value === undefined ? '–' : String(Math.round(value));
}

// Android screen shapes (height / width, portrait) and resolutions offered
// on the page. Density follows the width (160 dpi per 360 px), so Android's
// layout looks the same at every resolution: "Haute" only adds pixels, for
// sharp screenshots, at a higher CPU cost on the server.
const DEVICE_SHAPES = [
  { id: 's23', label: '19,5:9 (Galaxy S23)', ratio: 2340 / 1080 },
  { id: 'pixel', label: '20:9 (Pixel 8)', ratio: 2400 / 1080 },
  { id: 'classic', label: '16:9', ratio: 16 / 9 },
  { id: 'tablet', label: 'Tablette 16:10', ratio: 1.6 },
  { id: 'fold', label: 'Pliable ouvert', ratio: 2176 / 1812 },
  { id: 'window', label: 'Cette fenêtre', ratio: null },
];
// 480p is the default: sharp enough on a phone, still fluid on a server
// without a GPU.
const DEFAULT_RESOLUTION = '480';
const RESOLUTIONS = [
  { id: '360', label: '360p', width: 360 },
  { id: '480', label: '480p (défaut)', width: 480 },
  { id: '720', label: '720p', width: 720 },
  { id: '1080', label: '1080p', width: 1080 },
];

function even(value) {
  return Math.max(2, Math.round(value / 2) * 2);
}

function shapeRatio(shape) {
  if (shape.ratio) return shape.ratio;
  const ratio = window.innerHeight / Math.max(1, window.innerWidth);
  return Math.min(2.4, Math.max(1, ratio));
}

function targetSize(shapeId, resolutionId) {
  const shape = DEVICE_SHAPES.find((item) => item.id === shapeId) ?? DEVICE_SHAPES[0];
  const resolution = RESOLUTIONS.find((item) => item.id === resolutionId)
    ?? RESOLUTIONS.find((item) => item.id === DEFAULT_RESOLUTION);
  const width = resolution.width;
  return {
    width,
    height: Math.min(3200, even(width * shapeRatio(shape))),
    density: Math.round(width * 160 / 360),
  };
}

// The presets closest to a configured size, for the selectors' start values.
function matchPresets(size) {
  if (!size?.width) return { shape: 's23', resolution: DEFAULT_RESOLUTION };
  const ratio = size.height / size.width;
  const shape = DEVICE_SHAPES.find((item) => item.ratio && Math.abs(item.ratio - ratio) / ratio < 0.015);
  const resolution = RESOLUTIONS.find((item) => item.width === size.width);
  return { shape: shape?.id ?? 'window', resolution: resolution?.id ?? DEFAULT_RESOLUTION };
}

function shortSide(size) {
  return size?.width ? `${Math.min(size.width, size.height)}p` : '–';
}

// Polls the gateway for the screen size and the state of a size change:
// often while a change is in progress (or `changing` says one is), rarely
// otherwise.
function useDisplayState(gatewayUrl, changing) {
  const [displayState, setDisplayState] = useState(null);
  const busy = changing || ['pending', 'applying'].includes(displayState?.request?.state);
  useEffect(() => {
    let cancelled = false;
    const load = () => fetch(`${gatewayUrl}/api/v1/display`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((value) => { if (!cancelled && value) setDisplayState(value); })
      .catch(() => {});
    load();
    const timer = window.setInterval(load, busy ? 2000 : 15000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl, busy]);
  return displayState;
}

function useEmulatorSettings(gatewayUrl, enabled) {
  const [value, setValue] = useState(null);
  const [nonce, setNonce] = useState(0);
  const busy = ['pending', 'applying'].includes(value?.request?.state);
  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = () => fetch(`${gatewayUrl}/api/v1/emulator-settings`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((next) => { if (!cancelled && next) setValue(next); })
      .catch(() => {});
    load();
    const timer = window.setInterval(load, busy ? 2000 : 10000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl, enabled, busy, nonce]);
  return [value, () => setNonce((n) => n + 1)];
}

// What happened to Android and the server (GET /api/v1/events), read while
// the Server tab is open.
function useEvents(gatewayUrl, enabled) {
  const [value, setValue] = useState(null);
  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;
    const load = () => fetch(`${gatewayUrl}/api/v1/events`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((next) => { if (!cancelled && next) setValue(next); })
      .catch(() => {});
    load();
    const timer = window.setInterval(load, 15000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl, enabled]);
  return value;
}

// One event as a sentence, and its cause in plain words when known.
function describeEvent(event) {
  const app = event.app ?? '?';
  const titles = {
    crash: tr('{app} a planté', { app }),
    anr: tr('{app} ne répondait plus (ANR)', { app }),
    killed: tr('{app} arrêté par Android', { app }),
    low_memory: tr('Mémoire d’Android insuffisante'),
    android_boot: tr('Android a démarré'),
    emulator_start: tr('Le service Android a démarré'),
    gateway_start: tr('La passerelle a démarré'),
  };
  let cause = event.reason ?? '';
  const update = /^stop (\S+) due to installPackageLI/.exec(cause);
  if (update) cause = tr('mise à jour de {app} (les applis qui en dépendent s’arrêtent)', { app: update[1] });
  else if (/low ?mem|lmk|swap/i.test(cause)) cause = tr('mémoire insuffisante ({reason})', { reason: cause });
  if (event.kind === 'emulator_start') {
    const parts = [];
    if (event.restarts) parts.push(tr('{n} redémarrages automatiques', { n: event.restarts }));
    if (event.reason) parts.push(tr('dernier arrêt : {result}', { result: event.reason }));
    cause = parts.join(' · ');
  }
  return { title: titles[event.kind] ?? event.kind, cause };
}

function EventList({ events, rowStyle, labelStyle }) {
  if (!events) return <div style={rowStyle}>…</div>;
  const list = events.events ?? [];
  const locale = language() === 'en' ? 'en-GB' : 'fr-FR';
  return (
    <>
      {!events.android && <div style={rowStyle}>{tr('Journaux d’Android illisibles (adb)')}</div>}
      {list.length === 0 && <div style={rowStyle}>{tr('Aucun événement')}</div>}
      {list.slice(0, 30).map((event, index) => {
        const { title, cause } = describeEvent(event);
        const date = new Date(event.time * 1000);
        return (
          <div key={`${event.time}-${index}`} style={{ ...rowStyle, alignItems: 'flex-start' }}>
            <span style={{ ...labelStyle, whiteSpace: 'nowrap' }}>
              {date.toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            <span style={{ textAlign: 'right', overflowWrap: 'anywhere' }}>
              {title}
              {cause && <><br /><span style={{ opacity: 0.7, fontSize: '0.9em' }}>{cause}</span></>}
            </span>
          </div>
        );
      })}
    </>
  );
}

// Renderer, cores, memory and screen Android runs with. Applying restarts
// Android once, whatever changed.
function EmulatorSettings({ gatewayUrl, settings, refresh, rowStyle, labelStyle, buttonStyle }) {
  const current = settings?.current;
  const display = settings?.display;
  const [choice, setChoice] = useState(null);
  const [error, setError] = useState(null);
  const currentKey = current && display
    ? `${current.renderer} ${current.cores} ${current.memoryMb} ${display.width}x${display.height}x${display.density}` : '';
  useEffect(() => {
    if (current && display) {
      setChoice({
        renderer: current.renderer, cores: Number(current.cores), memoryMb: Number(current.memoryMb),
        ...matchPresets(display),
      });
    }
  }, [currentKey]);
  if (!settings) return <div style={styles.infoNote}>{tr('Indisponible pour le moment.')}</div>;
  if (!settings.canChange || !choice) return <div style={styles.infoNote}>{tr('Non disponible sur ce serveur.')}</div>;
  const request = settings.request ?? { state: 'idle' };
  const busy = request.state === 'pending' || request.state === 'applying';
  const renderers = rendererOptions(settings.limits);
  const hint = renderers.find((item) => item.id === choice.renderer)?.hint;
  const target = targetSize(choice.shape, choice.resolution);
  const sameScreen = target.width === display.width && target.height === display.height
    && target.density === display.density;
  const unchanged = sameScreen && sameSettings(choice, current);

  const apply = async () => {
    setError(null);
    const message = `${tr('Android va redémarrer avec ces réglages.')}\n`
      + tr('Cela prend une à deux minutes. Les applications ouvertes se ferment ; les données sont conservées.');
    if (!window.confirm(message)) return;
    const { renderer, cores, memoryMb } = choice;
    try {
      const response = await fetch(`${gatewayUrl}/api/v1/emulator-settings`, {
        method: 'POST',
        headers: postHeaders(),
        body: JSON.stringify({ renderer, cores, memoryMb, ...(sameScreen ? {} : target) }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        setError(body.error ?? tr('Erreur {status}', { status: response.status }));
      }
    } catch {
      setError(tr('Passerelle injoignable'));
    }
    refresh();
  };
  const numeric = ['cores', 'memoryMb'];
  const select = (key, options, label) => (
    <select value={choice[key]} disabled={busy} style={styles.select}
      onChange={(event) => setChoice((value) => ({
        ...value, [key]: numeric.includes(key) ? Number(event.target.value) : event.target.value,
      }))}>
      {options.map((item) => <option key={item.id ?? item} value={item.id ?? item}>{label(item)}</option>)}
    </select>
  );
  return (
    <>
      <label style={rowStyle}><span style={labelStyle}>{tr('Moteur de rendu')}</span>
        {select('renderer', renderers, (item) => tr(item.label))}</label>
      {hint && <div style={styles.infoNote}>{tr(hint)}</div>}
      <label style={rowStyle}><span style={labelStyle}>{tr('Cœurs')}</span>
        {select('cores', coreOptions(settings.limits?.maxCores, current?.cores), (n) => String(n))}</label>
      <label style={rowStyle}><span style={labelStyle}>{tr('Mémoire')}</span>
        {select('memoryMb', memoryOptions(settings.limits?.maxMemoryMb, current?.memoryMb), (mb) => `${mb / 1024} ${tr('Go')}`)}</label>
      <label style={rowStyle}><span style={labelStyle}>{tr('Appareil')}</span>
        {select('shape', DEVICE_SHAPES, (item) => tr(item.label))}</label>
      <label style={rowStyle}><span style={labelStyle}>{tr('Résolution')}</span>
        {select('resolution', RESOLUTIONS, (item) => tr(item.label))}</label>
      <div style={rowStyle}>
        <span style={labelStyle}>{target.width}×{target.height}</span>
        <button style={buttonStyle} onClick={apply} disabled={busy || unchanged}>{tr('Appliquer')}</button>
      </div>
      {request.state === 'pending' && <div style={styles.infoNote}>{tr('Demande envoyée, en attente du serveur…')}</div>}
      {request.state === 'applying' && (
        <div style={styles.infoNote}>{request.width
          ? tr('Android redémarre en {size}…', { size: `${request.width}×${request.height}` })
          : tr('Android redémarre…')}</div>
      )}
      {request.state === 'failed' && <div style={styles.infoWarning}>{tr('Échec : {message}', { message: request.message })}</div>}
      {error && <div style={styles.infoWarning}>{error}</div>}
    </>
  );
}

// Polls the gateway's view of the server: emulator service, Android boot,
// viewers, load. failures counts consecutive unanswered polls.
// details: also ask for the server metrics (CPU, memory, Android's frame
// rate), which cost the server an adb call: only while the server panel is
// open.
function useServerState(gatewayUrl, details = false) {
  const [server, setServer] = useState({ value: null, failures: 0 });
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      fetch(`${gatewayUrl}/api/v1/state?viewer=${encodeURIComponent(VIEWER_ID)}${details ? '&details=1' : ''}`,
        { cache: 'no-store', signal: controller.signal })
        .then((response) => (response.ok ? response.json() : Promise.reject(new Error(String(response.status)))))
        .then((value) => { if (!cancelled) setServer({ value, failures: 0 }); })
        .catch(() => { if (!cancelled) setServer((current) => ({ ...current, failures: current.failures + 1 })); })
        .finally(() => window.clearTimeout(timeout));
    };
    load();
    const timer = window.setInterval(load, details ? 2000 : 3000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [gatewayUrl, details]);
  return server;
}

// The single most important thing to tell the user, or null.
// level: 'error' (needs action or will not fix itself), 'wait' (being
// fixed), 'info' (works, but worse than usual). blocking: covers the screen.
function diagnose({ server, stream, connectingFor, touchFailures }) {
  const value = server.value;
  if (server.failures >= 2) {
    return {
      level: 'error', blocking: true, text: 'Serveur injoignable',
      detail: 'Vérifiez que le VPN (WireGuard) est connecté sur cet appareil.',
    };
  }
  if (value?.kicked) {
    return {
      level: 'error', blocking: true, text: 'Un autre appareil a pris la main',
      detail: 'Touchez ↻ pour la reprendre.',
    };
  }
  const display = value?.display?.state;
  if (display === 'pending' || display === 'applying') {
    return { level: 'wait', blocking: true, text: 'Changement de résolution', detail: 'Android redémarre…' };
  }
  const settingsChange = value?.settings?.state;
  if (settingsChange === 'pending' || settingsChange === 'applying') {
    return { level: 'wait', blocking: true, text: 'Changement des réglages d’Android', detail: 'Android redémarre…' };
  }
  const unit = value?.emulator;
  if (unit) {
    if (unit.active === 'failed') {
      return {
        level: 'error', blocking: true, text: 'Android s’est arrêté sur une erreur',
        detail: 'Il ne redémarre pas tout seul : il faut le relancer sur le serveur.',
      };
    }
    if (unit.active === 'activating' && unit.sub === 'auto-restart') {
      return { level: 'wait', blocking: true, text: 'Android a planté', detail: 'Redémarrage automatique…' };
    }
    if (unit.active === 'inactive' || unit.active === 'deactivating') {
      return { level: 'error', blocking: true, text: 'Android est arrêté', detail: 'Il faut le démarrer sur le serveur.' };
    }
    if (unit.active === 'activating') {
      return { level: 'wait', blocking: true, text: 'Android démarre…', detail: null };
    }
  }
  const booted = value?.android?.booted;
  if (value && booted === false) {
    return { level: 'wait', blocking: stream !== 'connected', text: 'Android démarre…', detail: 'Cela peut prendre une minute.' };
  }
  if (value && booted === null) {
    return { level: 'wait', blocking: stream !== 'connected', text: 'Le serveur se reconnecte à Android…', detail: null };
  }
  if (stream === 'disconnected') {
    return { level: 'wait', blocking: true, text: 'Vidéo interrompue', detail: 'Reconnexion…' };
  }
  if (stream !== 'connected' && connectingFor >= 15) {
    return {
      level: 'error', blocking: true, text: 'La vidéo ne se connecte pas',
      detail: 'Le réseau bloque peut-être le flux vidéo (UDP). Touchez ↻ pour réessayer.',
    };
  }
  if (touchFailures >= 3) {
    return { level: 'error', blocking: false, text: 'Les touches n’arrivent pas à Android', detail: null };
  }
  if (stream === 'connected' && value?.viewers > 1) {
    const others = value.viewers - 1;
    return {
      level: 'info', blocking: false,
      text: others === 1 ? tr('Un autre appareil regarde ce téléphone')
        : tr('{n} autres appareils regardent ce téléphone', { n: others }),
      detail: 'L’image peut être plus lente.',
    };
  }
  if (value?.load && value.load.one > value.load.cpus) {
    return { level: 'info', blocking: false, text: 'Serveur très chargé', detail: 'L’image peut ralentir.' };
  }
  return null;
}

const LEVEL_COLORS = { error: '#ff453a', wait: '#ff9f0a', info: '#ffd60a' };

function describeUnit(unit) {
  if (!unit) return '–';
  const restarts = unit.restarts
    ? `, ${tr(unit.restarts > 1 ? '{n} redémarrages' : '{n} redémarrage', { n: unit.restarts })}` : '';
  return `${unit.active} (${unit.sub})${restarts}`;
}

const LONG_PRESS_MS = 500;

// One id per page load: lets this page disconnect the other viewers, and
// the gateway refuse this page after another one disconnected it.
const VIEWER_ID = window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
setViewerId(VIEWER_ID);

// The gateway writes a per-start token into the page; every POST carries it,
// so a page from another origin cannot drive Android.
function postHeaders() {
  const token = document.querySelector('meta[name="cloudphone-token"]')?.getAttribute('content') ?? '';
  return { 'Content-Type': 'application/json', 'X-CloudPhone-Token': token };
}

// Per-viewer page settings, kept in this browser only.
const SETTINGS_KEY = 'cloudphone.settings';
const DEFAULT_SETTINGS = {
  touchMarker: true, autoFold: true, barDocked: false, language: null,
  // Plugin options: { <plugin id>: { <key>: true } }.
  plugins: {},
};


function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(window.localStorage.getItem(SETTINGS_KEY) || '{}') };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(settings) {
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // Private mode or blocked storage: settings last for this page only.
  }
}

// What this browser's device offers and what Android sends, as label/value
// rows: CSS pixels (layout) and physical pixels (CSS × devicePixelRatio).
function deviceInfo(shownScreen) {
  const ratio = window.devicePixelRatio || 1;
  const viewport = viewportSize();
  const physical = (width, height) => `${Math.round(width * ratio)}×${Math.round(height * ratio)}`;
  return [
    ['Écran de l’appareil', `${physical(window.screen.width, window.screen.height)} px`],
    ['Fenêtre', `${viewport.width}×${viewport.height} CSS · ${physical(viewport.width, viewport.height)} px`],
    ['Densité', `×${ratio.toFixed(2)}`],
    ['Image affichée', `${shownScreen.width}×${shownScreen.height} CSS · ${physical(shownScreen.width, shownScreen.height)} px`],
  ];
}

// Samples the stream once per STATS_INTERVAL_MS:
// - ping: ICE round-trip time when the browser reports it, otherwise the time
//   of an HTTP request to the gateway (same network path);
// - server: video frames received from the emulator per second;
// - phone: frames this browser actually displayed per second;
// - network details for the connectivity panel.
// Frame rates are 0 while the Android screen does not change: the emulator
// sends a frame only when something moves.
const EMPTY_STATS = {
  ping: null, pingSource: null, server: null, phone: null, video: null,
  bitrate: null, packetsLost: null, jitter: null, bufferDelay: null,
  framesDropped: null, codec: null, path: null, connection: null,
};

function useStreamStats(deviceRef, gatewayUrl) {
  const [stats, setStats] = useState(EMPTY_STATS);

  useEffect(() => {
    let previous = null;
    let busy = false;
    let stopped = false;
    // Frames presented on screen, counted with requestVideoFrameCallback where
    // available: getVideoPlaybackQuality() stays at 0 for WebRTC streams in
    // some browsers.
    let presented = 0;
    let watchedVideo = null;
    let frameCallback = null;

    const watchFrames = (video) => {
      if (!video || video === watchedVideo || typeof video.requestVideoFrameCallback !== 'function') return;
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
      watchedVideo = video;
      const onFrame = () => {
        presented += 1;
        if (!stopped && watchedVideo === video) frameCallback = video.requestVideoFrameCallback(onFrame);
      };
      frameCallback = video.requestVideoFrameCallback(onFrame);
    };

    const sample = async () => {
      if (busy) return;
      busy = true;
      try {
        const now = performance.now();
        const video = deviceRef.current?.querySelector('video');
        watchFrames(video);
        let shown = null;
        if (watchedVideo) {
          shown = presented;
        } else {
          const quality = video?.getVideoPlaybackQuality?.();
          shown = quality ? quality.totalVideoFrames - quality.droppedVideoFrames : null;
        }
        const sampleData = { received: null, bytes: null, ping: null, details: {} };
        const connection = activePeerConnection();
        if (connection) {
          try {
            const report = await connection.getStats();
            const byId = new Map();
            report.forEach((entry) => byId.set(entry.id, entry));
            report.forEach((entry) => {
              if (entry.type === 'inbound-rtp' && (entry.kind ?? entry.mediaType) === 'video') {
                sampleData.received = entry.framesReceived ?? entry.framesDecoded ?? null;
                sampleData.bytes = entry.bytesReceived ?? null;
                sampleData.details.packetsLost = entry.packetsLost ?? null;
                sampleData.details.jitter = typeof entry.jitter === 'number' ? entry.jitter * 1000 : null;
                sampleData.details.framesDropped = entry.framesDropped ?? null;
                if (entry.jitterBufferEmittedCount) {
                  sampleData.details.bufferDelay = entry.jitterBufferDelay / entry.jitterBufferEmittedCount * 1000;
                }
                sampleData.details.codec = byId.get(entry.codecId)?.mimeType?.replace('video/', '') ?? null;
              } else if (entry.type === 'candidate-pair' && entry.state === 'succeeded'
                && (entry.nominated || entry.selected)) {
                if (typeof entry.currentRoundTripTime === 'number') {
                  sampleData.ping = entry.currentRoundTripTime * 1000;
                }
                const local = byId.get(entry.localCandidateId);
                const remote = byId.get(entry.remoteCandidateId);
                if (local && remote) {
                  sampleData.details.path = `${local.candidateType ?? '?'} → ${remote.candidateType ?? '?'} (${(local.protocol ?? '?').toUpperCase()})`;
                }
              }
            });
            sampleData.details.connection = connection.connectionState;
          } catch (error) {
            console.warn('Stream statistics:', error);
          }
        }
        let pingSource = sampleData.ping === null ? null : 'ICE';
        if (sampleData.ping === null) {
          const start = performance.now();
          try {
            await fetch(`${gatewayUrl}/api/v1/ping`, { cache: 'no-store' });
            sampleData.ping = performance.now() - start;
            pingSource = 'HTTP';
          } catch {
            sampleData.ping = null;
          }
        }
        const rate = (current, before, seconds) => (
          current !== null && before !== null && current >= before ? (current - before) / seconds : null);
        const seconds = previous ? (now - previous.time) / 1000 : 0;
        if (!stopped) {
          setStats({
            ...EMPTY_STATS,
            ...sampleData.details,
            ping: sampleData.ping,
            pingSource,
            server: previous ? rate(sampleData.received, previous.received, seconds) : null,
            phone: previous ? rate(shown, previous.shown, seconds) : null,
            bitrate: previous && rate(sampleData.bytes, previous.bytes, seconds) !== null
              ? rate(sampleData.bytes, previous.bytes, seconds) * 8 / 1000 : null,
            video: video?.videoWidth ? { width: video.videoWidth, height: video.videoHeight } : null,
          });
        }
        previous = { time: now, received: sampleData.received, shown, bytes: sampleData.bytes };
      } finally {
        busy = false;
      }
    };

    const timer = window.setInterval(sample, STATS_INTERVAL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      if (watchedVideo && frameCallback !== null) watchedVideo.cancelVideoFrameCallback(frameCallback);
    };
  }, [deviceRef, gatewayUrl]);

  return stats;
}

// A button that floats over the screen and can be dragged anywhere, so it
// never sits for good over something the user wants to tap. A press that
// does not move is a click.
function FloatingHandle({ position, onMove, onClick, children, label }) {
  const drag = useRef(null);
  const dragged = useRef(false);
  const size = 36;
  const clamp = (x, y) => ({
    x: Math.max(0, Math.min(window.innerWidth - size, x)),
    y: Math.max(0, Math.min(window.innerHeight - size, y)),
  });
  const place = position ? clamp(position.x, position.y)
    : clamp(window.innerWidth - size - 8, window.innerHeight - size - 8);

  return (
    <button
      style={{ ...styles.toolbarHandle, left: place.x, top: place.y }}
      aria-label={label}
      onPointerDown={(event) => {
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { startX: event.clientX, startY: event.clientY, origin: place, moved: false };
      }}
      onPointerMove={(event) => {
        const current = drag.current;
        if (!current) return;
        const dx = event.clientX - current.startX;
        const dy = event.clientY - current.startY;
        if (!current.moved && Math.hypot(dx, dy) < 6) return;
        current.moved = true;
        onMove(clamp(current.origin.x + dx, current.origin.y + dy), false);
      }}
      onPointerUp={() => {
        const current = drag.current;
        drag.current = null;
        dragged.current = Boolean(current?.moved);
        if (current?.moved) onMove(place, true);
      }}
      onPointerCancel={() => { drag.current = null; }}
      // Unfold on the click itself, not on pointerup: removing the handle at
      // pointerup sent the tap's click to the fold button now under the
      // finger, which folded the bar again at once.
      onClick={() => {
        if (dragged.current) {
          dragged.current = false;
          return;
        }
        onClick();
      }}
    >
      {children}
    </button>
  );
}

function App() {
  const emulatorRef = useRef(null);
  const deviceRef = useRef(null);
  const feedbackTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  // Open panel over the screen: 'info' (from the ping/fps block, with a
  // client and a server tab) or 'options' (from the cog).
  const [panel, setPanel] = useState(null);
  const [infoTab, setInfoTab] = useState('client');
  const serverTab = panel === 'info' && infoTab === 'server';
  const foldPress = useRef({ timer: null, long: false });
  const [settings, setSettings] = useState(loadSettings);
  // Before any tr() of this render: null means the browser's language.
  setLanguage(settings.language ?? defaultLanguage());
  const updateSettings = (change) => setSettings((current) => {
    const next = { ...current, ...change };
    saveSettings(next);
    return next;
  });
  const pointerDown = useRef(false);
  // Touch updates sent to the gateway: at most one request in flight. Press
  // and release are queued in order; while a request runs, intermediate moves
  // collapse into the latest one, so a drag never lags behind the finger.
  const touchSender = useRef({ inFlight: false, queue: [], pendingMove: null });
  const touchMarker = useRef(null);
  // "data channel" or "HTTP": how the last touch reached Android.
  const inputPath = useRef('–');
  const reconnectTimer = useRef(null);
  const [display, setDisplay] = useState(DEFAULT_DISPLAY);
  // Folded: the bar is hidden and the screen uses the whole window; a small
  // handle unfolds it. Entering fullscreen folds it after 3 s.
  const [barFolded, setBarFolded] = useState(false);
  // Folding exists only in fullscreen: outside it the bar always shows.
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  // The unfold handle appears where the fold button was, at every fold; a
  // drag moves it until the bar is unfolded.
  const foldButtonRef = useRef(null);
  const [handlePosition, setHandlePosition] = useState(null);
  const foldBar = useRef(null);
  foldBar.current = () => {
    const bounds = foldButtonRef.current?.getBoundingClientRect();
    setHandlePosition(bounds && bounds.width > 0
      ? { x: bounds.left + bounds.width / 2 - 18, y: bounds.top + bounds.height / 2 - 18 } : null);
    setBarFolded(true);
  };
  const [screen, setScreen] = useState(() => fittedScreen(DEFAULT_DISPLAY));
  const row = screen.toolbar === 'side';
  const overlay = screen.toolbar === 'overlay';
  useEffect(() => {
    const folder = () => {
      const current = loadSettings();
      if (!document.fullscreenElement || !current.autoFold || current.barDocked) return;
      const timer = window.setTimeout(() => foldBar.current(), 3000);
      return () => window.clearTimeout(timer);
    };
    let cancel = null;
    const changed = () => {
      cancel?.();
      setFullscreen(Boolean(document.fullscreenElement));
      setBarFolded(false);
      cancel = folder() ?? null;
    };
    document.addEventListener('fullscreenchange', changed);
    return () => {
      cancel?.();
      document.removeEventListener('fullscreenchange', changed);
    };
  }, []);
  const buttonStyle = row ? styles.button : { ...styles.button, ...styles.buttonBelow };
  const [state, setState] = useState('connecting');
  const [streamMounted, setStreamMounted] = useState(true);
  const [streamGeneration, setStreamGeneration] = useState(0);
  // The gateway serves this page: same origin, no CORS.
  const gateway = window.location.host;
  const gatewayUrl = `${window.location.protocol}//${gateway}`;
  const stats = useStreamStats(deviceRef, gatewayUrl);
  const server = useServerState(gatewayUrl, serverTab);
  const [emulatorSettings, refreshEmulatorSettings] = useEmulatorSettings(gatewayUrl, serverTab);
  const events = useEvents(gatewayUrl, serverTab);
  const pluginLayer = useRef(null);
  const plugins = usePlugins({
    gatewayUrl, deviceRef, layerRef: pluginLayer, screenWidth: screen.width, settings, postHeaders,
  });
  const displayState = useDisplayState(gatewayUrl,
    ['pending', 'applying'].includes(emulatorSettings?.request?.state));
  // Seconds the stream has been trying to connect, and consecutive failed
  // touch requests: both feed the message shown to the user.
  const [connectingFor, setConnectingFor] = useState(0);
  const [touchFailures, setTouchFailures] = useState(0);
  // A size change ends with the gateway restarting on the new size: reload
  // so that layout, touch mapping and the stream all start fresh.
  const firstSize = useRef(null);
  useEffect(() => {
    const running = displayState?.running;
    if (!running?.width) return;
    const size = `${running.width}x${running.height}`;
    if (firstSize.current === null) firstSize.current = size;
    else if (size !== firstSize.current) window.location.reload();
  }, [displayState]);

  // The gateway reads Android's display size from the running device, so
  // layout and touch mapping follow the AVD instead of a constant.
  useEffect(() => {
    let cancelled = false;
    fetch(`${gatewayUrl}/api/v1/emulator/status`, { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((status) => {
        const config = status?.platformConfig ?? {};
        const width = Number(config['hw.lcd.width']);
        const height = Number(config['hw.lcd.height']);
        if (!cancelled && width > 0 && height > 0) setDisplay({ width, height });
      })
      .catch((error) => console.warn('Android display size:', error));
    return () => { cancelled = true; };
  }, [gatewayUrl]);

  const stopFeedback = () => {
    setReconnecting(false);
    if (feedbackTimer.current !== null) {
      window.clearTimeout(feedbackTimer.current);
      feedbackTimer.current = null;
    }
  };

  // Manual refresh: show that the click was taken into account until the new
  // stream displays its first frame.
  const manualReconnect = () => {
    // Disconnected by another viewer: a new page load is a new viewer.
    if (server.value?.kicked) {
      window.location.reload();
      return;
    }
    setReconnecting(true);
    if (feedbackTimer.current !== null) window.clearTimeout(feedbackTimer.current);
    feedbackTimer.current = window.setTimeout(stopFeedback, RECONNECT_FEEDBACK_MS);
    reconnectStream();
  };

  const reconnectStream = () => {
    if (reconnectTimer.current !== null) return;
    pointerDown.current = false;
    setState('connecting');
    setStreamMounted(false);
    reconnectTimer.current = window.setTimeout(() => {
      setStreamGeneration((generation) => generation + 1);
      setStreamMounted(true);
      reconnectTimer.current = null;
    // Leave enough time for the WebSocket bye to reach the gateway and for the
    // emulator-side participant to be destroyed before requesting a new one.
    }, 1000);
  };

  const handleStreamState = (nextState) => {
    setState(nextState);
    if (nextState === 'connected' && reconnectTimer.current === null) stopFeedback();
  };

  useEffect(() => {
    if (state === 'connected') {
      setConnectingFor(0);
      return undefined;
    }
    const started = Date.now();
    const timer = window.setInterval(() => setConnectingFor(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [state, streamGeneration]);

  const problem = diagnose({ server, stream: state, connectingFor, touchFailures });
  // A closed warning stays hidden until it goes away and comes back.
  const [dismissed, setDismissed] = useState(null);
  useEffect(() => {
    if (dismissed !== null && problem?.text !== dismissed) setDismissed(null);
  }, [problem?.text]);
  // Android is usable again (after a crash, a restart or a lost stream):
  // reconnect the video without waiting for the user.
  const serverHealthy = server.failures < 2 && server.value?.android?.booted === true
    && server.value?.emulator?.active !== 'activating';
  useEffect(() => {
    if (!serverHealthy || state === 'connected') return undefined;
    if (state !== 'disconnected' && connectingFor < 20) return undefined;
    const timer = window.setTimeout(reconnectStream, 2000);
    return () => window.clearTimeout(timer);
  }, [serverHealthy, state, connectingFor >= 20]);

  useEffect(() => {
    const resize = () => setScreen(fittedScreen(display, barFolded, settings.barDocked));
    resize();
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    document.addEventListener('fullscreenchange', resize);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
      document.removeEventListener('fullscreenchange', resize);
    };
  }, [display, barFolded, settings.barDocked]);

  useEffect(() => {
    let wasHidden = document.visibilityState === 'hidden';

    const visibilityChanged = () => {
      if (document.visibilityState === 'hidden') {
        wasHidden = true;
      } else if (wasHidden) {
        wasHidden = false;
        reconnectStream();
      }
    };

    const pageShown = (event) => {
      if (event.persisted) reconnectStream();
    };

    document.addEventListener('visibilitychange', visibilityChanged);
    window.addEventListener('pageshow', pageShown);
    return () => {
      document.removeEventListener('visibilitychange', visibilityChanged);
      window.removeEventListener('pageshow', pageShown);
      if (reconnectTimer.current !== null) {
        window.clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (feedbackTimer.current !== null) {
        window.clearTimeout(feedbackTimer.current);
        feedbackTimer.current = null;
      }
    };
  }, []);

  const post = (path, body) => fetch(`${gatewayUrl}${path}`, {
    method: 'POST',
    headers: postHeaders(),
    body: JSON.stringify(body),
  }).then((response) => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    setTouchFailures(0);
  }).catch((error) => {
    setTouchFailures((count) => count + 1);
    console.error('Android control:', error);
  });

  // Keys: the emulator's "keyboard" data channel when open (a keypress with
  // the DOM key name), otherwise the gateway, which uses adb.
  const disconnectOthers = () => fetch(`${gatewayUrl}/api/v1/viewers/disconnect-others`, {
    method: 'POST',
    headers: postHeaders(),
    body: JSON.stringify({ viewer: VIEWER_ID }),
  }).catch((error) => console.error('Disconnect others:', error));

  const sendKey = (key) => {
    if (USE_DATA_CHANNEL) {
      const event = new Proto.KeyboardEvent();
      event.setEventtype(Proto.KeyboardEvent.KeyEventType.KEYPRESS);
      event.setKey(key);
      if (sendInputEvent('keyboard', event)) return;
    }
    post('/api/v1/emulator/key', { key });
  };

  const touchCoordinates = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(display.width - 1,
        Math.round((event.clientX - bounds.left) * display.width / bounds.width))),
      y: Math.max(0, Math.min(display.height - 1,
        Math.round((event.clientY - bounds.top) * display.height / bounds.height))),
    };
  };

  const pumpTouches = () => {
    const sender = touchSender.current;
    if (sender.inFlight) return;
    let next = sender.queue.shift();
    if (!next && sender.pendingMove) {
      next = sender.pendingMove;
      sender.pendingMove = null;
    }
    if (!next) return;
    sender.inFlight = true;
    post('/api/v1/emulator/touch', next).finally(() => {
      sender.inFlight = false;
      pumpTouches();
    });
  };

  // Preferred path: the stream's WebRTC data channel, straight to the
  // emulator, no HTTP request and no gRPC hop through the gateway.
  const sendOverChannel = (coordinates, pressed) => {
    const touch = new Proto.Touch();
    touch.setX(coordinates.x);
    touch.setY(coordinates.y);
    touch.setIdentifier(0);
    touch.setPressure(pressed ? 1024 : 0);
    touch.setTouchMajor(pressed ? 8 : 0);
    touch.setTouchMinor(pressed ? 8 : 0);
    const event = new Proto.TouchEvent();
    event.setTouchesList([touch]);
    event.setDisplay(0);
    return sendInputEvent('touch', event);
  };

  const queueTouch = (coordinates, pressed, move = false) => {
    const sender = touchSender.current;
    // Use the channel only when no HTTP touch is pending, to keep the order.
    const httpIdle = !sender.inFlight && sender.queue.length === 0 && !sender.pendingMove;
    if (USE_DATA_CHANNEL && httpIdle && sendOverChannel(coordinates, pressed)) {
      inputPath.current = 'data channel';
      return;
    }
    inputPath.current = 'HTTP';
    if (move) {
      sender.pendingMove = { ...coordinates, pressed: true };
    } else {
      if (sender.pendingMove) {
        sender.queue.push(sender.pendingMove);
        sender.pendingMove = null;
      }
      sender.queue.push({ ...coordinates, pressed });
    }
    pumpTouches();
  };

  // Local marker under the finger: immediate feedback while the video of
  // Android's reaction is still on its way.
  const showMarker = (event, visible) => {
    const marker = touchMarker.current;
    if (!marker) return;
    if (!settings.touchMarker) visible = false;
    const bounds = event.currentTarget.getBoundingClientRect();
    marker.style.transform = `translate(${event.clientX - bounds.left}px, ${event.clientY - bounds.top}px)`;
    marker.style.opacity = visible ? '1' : '0';
  };

  const startTouch = (event) => {
    event.preventDefault();
    pointerDown.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    showMarker(event, true);
    queueTouch(touchCoordinates(event), true);
  };

  const moveTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    showMarker(event, true);
    queueTouch(touchCoordinates(event), true, true);
  };

  const endTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    pointerDown.current = false;
    showMarker(event, false);
    queueTouch(touchCoordinates(event), false);
  };

  const keyButton = (key, label, icon) => (
    <button className="tool-button" style={buttonStyle} onClick={() => sendKey(key)}
      aria-label={label}><Icon name={icon} /></button>
  );
  const connected = state === 'connected';
  // The connection LED sits in the refresh button's corner.
  const reloadButton = (
    <button
      className="tool-button"
      style={{ ...buttonStyle, ...styles.withLed, ...(reconnecting ? styles.buttonBusy : null) }}
      onClick={manualReconnect}
      aria-label={tr('Reconnecter la vidéo')}
      aria-busy={reconnecting}
    >
      <Icon name="refresh" spinning={reconnecting} />
      <span
        title={state}
        aria-label={tr('Connexion {state}', { state })}
        style={{
          ...styles.led,
          background: problem && problem.level !== 'info' ? LEVEL_COLORS[problem.level]
            : connected ? '#34c759' : '#ff9f0a',
        }}
      />
    </button>
  );
  const fullscreenButton = (
    <button className="tool-button" style={buttonStyle} onClick={toggleFullscreen}
      aria-label={tr('Plein écran')}><Icon name="fullscreen" /></button>
  );
  // Tap: fold the bar away. Long press: dock it, so it keeps its own space
  // instead of floating over the screen; a tap then makes it float again.
  const foldButton = (
    <button
      ref={foldButtonRef}
      className="tool-button"
      style={{ ...buttonStyle, ...(settings.barDocked ? styles.buttonDocked : null) }}
      aria-label={settings.barDocked ? tr('Barre fixe : toucher pour la rendre flottante')
        : tr('Replier la barre (appui long : barre fixe)')}
      aria-pressed={settings.barDocked}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={() => {
        foldPress.current.long = false;
        window.clearTimeout(foldPress.current.timer);
        foldPress.current.timer = window.setTimeout(() => {
          foldPress.current.long = true;
          navigator.vibrate?.(20);
          updateSettings({ barDocked: true });
        }, LONG_PRESS_MS);
      }}
      onPointerUp={() => window.clearTimeout(foldPress.current.timer)}
      onPointerCancel={() => window.clearTimeout(foldPress.current.timer)}
      onPointerLeave={() => window.clearTimeout(foldPress.current.timer)}
      onClick={() => {
        if (foldPress.current.long) return;
        if (settings.barDocked) updateSettings({ barDocked: false });
        else foldBar.current();
      }}
    ><Icon name={row ? 'foldSide' : 'fold'} /></button>
  );
  const togglePanel = (name) => setPanel((open) => (open === name ? null : name));
  const zoneStyle = row ? { ...styles.barZone, ...styles.barZoneColumn } : styles.barZone;
  // The ping and the frames per second this device shows, one above the
  // other: opens the information panel on its client tab.
  const metricsBlock = (
    <button className="metric-link" style={styles.metric}
      onClick={() => { if (panel !== 'info') setInfoTab('client'); togglePanel('info'); }}
      aria-label={tr('Informations : client et serveur')} aria-expanded={panel === 'info'}>
      <span style={{ ...styles.metricLine, color: pingColor(stats.ping) }}>{formatValue(stats.ping)}ms</span>
      <span style={{ ...styles.metricLine, color: '#e8ebf0' }}>{formatValue(stats.phone)}fps</span>
    </button>
  );
  const optionsButton = (
    <button className="tool-button" style={buttonStyle} onClick={() => togglePanel('options')}
      aria-label={tr('Options et plugins')} title={tr('Options et plugins')} aria-expanded={panel === 'options'}>
      <Icon name="cog" />
    </button>
  );
  const row2 = (label, value) => (
    <div key={label} style={styles.infoRow}>
      <span style={styles.infoLabel}>{label}</span>
      <span>{value}</span>
    </div>
  );
  const configured = displayState?.configured;
  const load = server.value?.load;
  const metrics = server.value?.metrics;
  const mib = (value) => (value === null || value === undefined ? '–'
    : value >= 1024 ? `${(value / 1024).toFixed(1)} ${tr('Go')}` : `${value} ${tr('Mo')}`);
  const memoryRow = (memory) => (memory?.total
    ? tr('{used} utilisés / {total}', { used: mib(memory.total - memory.available), total: mib(memory.total) }) : '–');
  const swapRow = (memory) => (memory?.swapTotal ? `${mib(memory.swapUsed)} / ${mib(memory.swapTotal)}` : '–');
  const host = metrics?.host;
  const emulator = metrics?.emulator;
  const android = metrics?.android;
  const serverSections = [
    ['État', [
      ['Serveur', server.failures >= 2 ? tr('injoignable') : server.value ? tr('joignable') : '…'],
      ['Service Android', describeUnit(server.value?.emulator)],
      ['Android démarré', server.value?.android?.booted === true ? tr('oui')
        : server.value?.android?.booted === false ? tr('en cours') : tr('sans réponse')],
      ['Appareils connectés', formatValue(server.value?.viewers)],
      ['Charge du serveur', load ? (load.cores ? tr('{load} tâches pour {cpus} threads ({cores} cœurs)', { load: load.one.toFixed(1), cpus: load.cpus, cores: load.cores })
        : tr('{load} tâches pour {cpus} threads', { load: load.one.toFixed(1), cpus: load.cpus })) : '–'],
    ]],
    ['Machine', [
      ['Processeur', host ? tr('{cpu} % de {cpus} threads', { cpu: host.cpu, cpus: host.cpus }) : '–'],
      ['Fréquence', host?.mhz ? `${host.mhz} MHz${host.governor ? ` (${host.governor})` : ''}` : '–'],
      ['Mémoire', memoryRow(host?.memory)],
      ['Émulateur', emulator?.cpu === null || emulator?.cpu === undefined ? '–'
        : tr('{cores} cœurs · {memory}', { cores: (emulator.cpu / 100).toFixed(1), memory: mib(emulator.memory) })],
    ]],
    ['Android', [
      ['Écran Android', configured?.width ? `${configured.width}×${configured.height} px` : `${display.width}×${display.height} px`],
      ['Moteur de rendu', emulator?.settings?.renderer ?? '–'],
      ['Cœurs et mémoire', emulator?.settings
        ? tr('{cores} cœurs · {memory}', { cores: emulator.settings.cores ?? '?', memory: mib(Number(emulator.settings.memoryMb)) }) : '–'],
      ['Images/s du jeu', android?.fps === null || android?.fps === undefined ? '–'
        : `${android.fps}${android.app ? ` (${android.app})` : ''}`],
      ['Mémoire Android', memoryRow(android?.memory)],
      ['Swap Android', swapRow(android?.memory)],
    ]],
    ['Flux envoyé', [
      ['Flux vidéo', stats.video ? `${stats.video.width}×${stats.video.height} px (${shortSide(stats.video)})` : '–'],
      ['Images envoyées', `${formatValue(stats.server)} /s`],
      ['Débit vidéo', stats.bitrate === null ? '–' : `${Math.round(stats.bitrate)} kbit/s`],
      ['Codec', stats.codec ?? '–'],
    ]],
  ];
  const clientSections = [
    ['Réseau', [
      ['Ping', stats.ping === null ? '–' : `${Math.round(stats.ping)} ms (${stats.pingSource})`],
      ['Connexion', stats.connection ?? state],
      ['Chemin', stats.path ?? '–'],
      ['Paquets perdus', formatValue(stats.packetsLost)],
      ['Gigue', stats.jitter === null ? '–' : `${Math.round(stats.jitter)} ms`],
    ]],
    ['Affichage', [
      ['Images affichées', `${formatValue(stats.phone)} /s`],
      ['Images perdues', formatValue(stats.framesDropped)],
      ['Tampon vidéo', stats.bufferDelay === null ? '–' : `${Math.round(stats.bufferDelay)} ms`],
      ...deviceInfo(screen),
    ]],
    ['Entrées', [['Touches via', inputPath.current]]],
  ];
  const sections = (list) => list.map(([title, rows]) => (
    <div key={title}>
      <div style={styles.infoSection}>{tr(title)}</div>
      {rows.map(([label, value]) => row2(tr(label), value))}
    </div>
  ));
  const toggle = (label, key) => (
    <label key={key} style={styles.infoRow}>
      <span style={styles.infoLabel}>{tr(label)}</span>
      <input type="checkbox" checked={settings[key]}
        onChange={(event) => updateSettings({ [key]: event.target.checked })} />
    </label>
  );

  const setPluginOption = (id, key, value) => updateSettings({
    plugins: { ...settings.plugins, [id]: { ...settings.plugins?.[id], [key]: value } },
  });
  const pluginOption = (plugin, option, index) => {
    const key = `${plugin.id}-${index}`;
    if (option.type === 'toggle') {
      return (
        <label key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <input type="checkbox" checked={Boolean(settings.plugins?.[plugin.id]?.[option.key])}
            onChange={(event) => setPluginOption(plugin.id, option.key, event.target.checked)} />
        </label>
      );
    }
    if (option.type === 'number') {
      if (!(option.visible?.() ?? true)) return null;
      return (
        <label key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <input type="text" inputMode="numeric" pattern="[0-9]*" maxLength={12} style={styles.numberInput}
            placeholder={option.placeholder ?? ''} value={settings.plugins?.[plugin.id]?.[option.key] ?? ''}
            onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value.replace(/\D/g, ''))} />
        </label>
      );
    }
    if (option.type === 'choice') {
      return (
        <label key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <select style={styles.select} value={settings.plugins?.[plugin.id]?.[option.key] ?? option.choices?.[0]?.value ?? ''}
            onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value)}>
            {(option.choices ?? []).map((choice) => (
              <option key={choice.value} value={choice.value}>{tr(choice.label)}</option>
            ))}
          </select>
        </label>
      );
    }
    if (option.type === 'action') {
      return (
        <div key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <button style={styles.panelButton} disabled={option.disabled?.() ?? false}
            onClick={() => Promise.resolve(option.run?.()).catch((error) => console.error(error))}>
            {tr(option.button ?? option.label)}
          </button>
        </div>
      );
    }
    if (option.type === 'status' && (option.visible?.() ?? true)) return row2(tr(option.label), option.value?.() ?? '–');
    return null;
  };

  return (
    <main style={{ ...styles.app, flexDirection: row ? 'row' : 'column' }}>
      <style>{`
        @keyframes stream-spinner {
          to { transform: rotate(360deg); }
        }
        .tool-button:active { background: #3a6ea5 !important; border-color: #4da3ff !important; }
        .metric-link:active { opacity: 0.6; }
        /* A long press must reach Android, not open the browser's
           select/copy menu over the video. The panels stay selectable. */
        body { -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;
          -webkit-tap-highlight-color: transparent; }
        [role="dialog"] { -webkit-user-select: text; user-select: text; }
      `}</style>
      <section style={styles.screen} aria-label={tr('Écran Android')}
        onContextMenu={(event) => event.preventDefault()}>
        <div ref={deviceRef} style={{ ...styles.device, width: screen.width, height: screen.height }}>
          {streamMounted && (
            <Emulator
              key={streamGeneration}
              ref={emulatorRef}
              uri={gateway}
              width={screen.width}
              height={screen.height}
              muted
              onStateChange={handleStreamState}
              onError={(error) => console.error('Android stream:', error)}
            />
          )}
          {(state !== 'connected' || problem?.blocking) && (
            <div style={styles.loading} role="status" aria-live="polite">
              {problem?.blocking && problem.level === 'error'
                ? <span style={{ ...styles.problemMark, color: LEVEL_COLORS.error }} aria-hidden="true">!</span>
                : <span style={styles.spinner} aria-hidden="true" />}
              <span style={styles.loadingText}>
                {problem?.blocking ? tr(problem.text) : reconnecting ? tr('Reconnexion…') : tr('Connexion au flux…')}
              </span>
              {problem?.blocking && problem.detail && <span style={styles.loadingDetail}>{tr(problem.detail)}</span>}
            </div>
          )}
          {problem && !problem.blocking && dismissed !== problem.text && (
            <div style={{ ...styles.banner, ...styles.bannerWithClose, borderColor: LEVEL_COLORS[problem.level] }}
              role="status">
              <span>{tr(problem.text)}{problem.detail && <><br /><small>{tr(problem.detail)}</small></>}</span>
              <button style={styles.bannerClose} onClick={() => setDismissed(problem.text)}
                aria-label={tr('Fermer')}>✕</button>
            </div>
          )}
          <div ref={pluginLayer} style={styles.pluginLayer} aria-hidden="true" />
          {panel && (
            <div style={styles.info} role="dialog"
              aria-label={panel === 'info' ? tr('Informations') : tr('Options')}>
              <div style={styles.infoHeader}>
                <strong>{panel === 'info' ? tr('Informations') : tr('Options')}</strong>
                <button style={styles.infoClose} onClick={() => setPanel(null)} aria-label={tr('Fermer')}>✕</button>
              </div>
              {panel === 'info' && (
                <div style={styles.tabs} role="tablist">
                  {[['client', tr('Client')], ['server', tr('Serveur')]].map(([id, label]) => (
                    <button key={id} role="tab" aria-selected={infoTab === id}
                      style={infoTab === id ? { ...styles.tab, ...styles.tabSelected } : styles.tab}
                      onClick={() => setInfoTab(id)}>{label}</button>
                  ))}
                </div>
              )}
              {panel === 'info' && infoTab === 'server' && (
                <div role="tabpanel">
                  {sections(serverSections)}
                  {server.value?.viewers > 1 && (
                    <div style={styles.infoRow}>
                      <span style={styles.infoLabel}>{tr('Autres appareils')}</span>
                      <button style={styles.panelButton} onClick={disconnectOthers}>
                        {tr('Déconnecter')}
                      </button>
                    </div>
                  )}
                  <div style={styles.infoSection}>{tr('Réglages d’Android')}</div>
                  <EmulatorSettings
                    gatewayUrl={gatewayUrl}
                    settings={emulatorSettings}
                    refresh={refreshEmulatorSettings}
                    rowStyle={styles.infoRow}
                    labelStyle={styles.infoLabel}
                    buttonStyle={styles.panelButton}
                  />
                  <div style={styles.infoSection}>{tr('Événements')}</div>
                  <EventList events={events} rowStyle={styles.infoRow} labelStyle={styles.infoLabel} />
                </div>
              )}
              {panel === 'info' && infoTab === 'client' && (
                <div role="tabpanel">{sections(clientSections)}</div>
              )}
              {panel === 'options' && (
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
                  <div style={styles.infoSection}>{tr('Plugins')}</div>
                  {plugins.length === 0 && <div style={styles.infoNote}>{tr('Aucun plugin installé.')}</div>}
                  {plugins.map((plugin) => (
                    // One foldable section per plugin, folded state kept with the settings.
                    <details key={plugin.id} open={!settings.foldedPlugins?.[plugin.id]}
                      onToggle={(event) => {
                        const folded = !event.currentTarget.open;
                        if (folded !== Boolean(settings.foldedPlugins?.[plugin.id])) {
                          updateSettings({ foldedPlugins: { ...settings.foldedPlugins, [plugin.id]: folded } });
                        }
                      }}>
                      <summary style={styles.pluginTitle}>{plugin.title}</summary>
                      {plugin.error && <div style={styles.infoWarning}>{tr('Échec : {message}', { message: plugin.error })}</div>}
                      {(plugin.instance.options ?? []).map((option, index) => pluginOption(plugin, option, index))}
                    </details>
                  ))}
                </>
              )}
            </div>
          )}
          <div ref={touchMarker} style={styles.touchMarker} aria-hidden="true" />
          <div
            style={styles.touchLayer}
            aria-label={tr('Surface tactile Android')}
            onPointerDown={startTouch}
            onPointerMove={moveTouch}
            onPointerUp={endTouch}
            onPointerCancel={endTouch}
          />
        </div>
      </section>
      {fullscreen && barFolded && (
        <FloatingHandle
          label={tr('Afficher la barre (glisser pour déplacer)')}
          position={handlePosition}
          onMove={(position) => setHandlePosition(position)}
          onClick={() => setBarFolded(false)}
        ><Icon name="unfold" /></FloatingHandle>
      )}
      <nav
        style={row ? styles.toolbar
          : overlay ? { ...styles.toolbarBar, ...styles.toolbarOverlay, display: barFolded ? 'none' : 'grid' }
            : styles.toolbarBar}
        aria-label={tr('Contrôles Android')}
      >
        {/* Same order beside the screen (top to bottom) and below it (left to
            right): the phone's physical keys and the network metrics,
            Android's recents, home and back centred, then the stream
            information and the page's own buttons. */}
        <div style={{ ...zoneStyle, justifyContent: 'flex-start' }}>
          {keyButton('Power', tr('Marche arrêt'), 'power')}
          {keyButton('AudioVolumeDown', tr('Baisser le volume'), 'volumeDown')}
          {keyButton('AudioVolumeUp', tr('Monter le volume'), 'volumeUp')}
          {metricsBlock}
        </div>
        <div style={zoneStyle} aria-label={tr('Navigation Android')}>
          {keyButton('AppSwitch', tr('Applications récentes'), 'recents')}
          {keyButton('GoHome', tr('Accueil'), 'home')}
          {keyButton('GoBack', tr('Retour'), 'back')}
        </div>
        <div style={{ ...zoneStyle, justifyContent: 'flex-end' }}>
          {optionsButton}
          {reloadButton}
          {fullscreenButton}
          {fullscreen && foldButton}
        </div>
      </nav>
    </main>
  );
}

const styles = {
  // The screen and the toolbar form one centered block, so on a wide window
  // the toolbar stays next to the screen instead of at the window's edge.
  app: {
    position: 'fixed', inset: 0, display: 'flex', flexDirection: 'row',
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden', background: '#20242b', color: '#fff', touchAction: 'none',
  },
  screen: {
    flex: '0 0 auto', display: 'flex', alignItems: 'center',
    justifyContent: 'center', overflow: 'hidden', background: '#20242b',
  },
  device: { position: 'relative', flex: '0 0 auto', background: '#000' },
  loading: {
    position: 'absolute', inset: 0, zIndex: 3, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', gap: '12px', background: '#20242b',
  },
  spinner: {
    width: '34px', height: '34px', boxSizing: 'border-box', borderRadius: '50%',
    border: '4px solid #525964', borderTopColor: '#4da3ff',
    animation: 'stream-spinner 0.8s linear infinite',
  },
  loadingText: {
    color: '#d8dde5', fontSize: '13px', fontFamily: 'system-ui, sans-serif',
  },
  pluginLayer: { position: 'absolute', inset: 0, zIndex: 1, pointerEvents: 'none' },
  pluginTitle: { marginTop: '6px', fontWeight: 600, cursor: 'pointer' },
  numberInput: {
    width: '96px', padding: '3px 6px', borderRadius: '6px', border: '1px solid #3a3f47',
    background: '#1b1d22', color: '#e8ebf0', font: 'inherit', textAlign: 'right',
  },
  tabs: { display: 'flex', gap: '6px', margin: '4px 0 6px' },
  tab: {
    flex: 1, padding: '5px 0', borderRadius: '6px', border: '1px solid #3a3f47',
    background: 'transparent', color: '#c9ced6', font: 'inherit', cursor: 'pointer',
  },
  tabSelected: { background: '#3a6ea5', borderColor: '#4da3ff', color: '#fff' },
  touchMarker: {
    position: 'absolute', left: '-14px', top: '-14px', width: '28px', height: '28px', zIndex: 2,
    borderRadius: '50%', background: 'rgba(77, 163, 255, 0.35)', border: '2px solid rgba(77, 163, 255, 0.8)',
    boxSizing: 'border-box', pointerEvents: 'none', opacity: 0, transition: 'opacity 0.15s',
  },
  touchLayer: {
    position: 'absolute', inset: 0, zIndex: 2, touchAction: 'none', cursor: 'default',
  },
  toolbar: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', width: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'grid', gridTemplateRows: 'auto 1fr auto',
    justifyItems: 'center', rowGap: '8px', padding: '6px 2px',
    background: '#1b1d22', borderLeft: '1px solid #3b3f47', zIndex: 10,
  },
  toolbarOverlay: {
    position: 'fixed', left: 0, right: 0, bottom: 0, width: '100%',
    background: 'rgba(27, 29, 34, 0.85)', borderTop: '1px solid rgba(59, 63, 71, 0.85)',
  },
  toolbarHandle: {
    position: 'fixed', zIndex: 11, touchAction: 'none',
    width: '36px', height: '36px', padding: 0, display: 'flex', alignItems: 'center',
    justifyContent: 'center', border: '1px solid rgba(85, 85, 85, 0.8)',
    borderRadius: '50%', background: 'rgba(27, 29, 34, 0.7)', color: '#d8dde5',
    boxShadow: '0 1px 4px rgba(0, 0, 0, 0.5)',
  },
  // Horizontal bar: left, centre and right zones; the centre stays centred
  // whatever the side zones hold.
  toolbarBar: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', height: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto minmax(0, 1fr)',
    alignItems: 'center', columnGap: '4px', padding: '2px 4px',
    background: '#1b1d22', borderTop: '1px solid #3b3f47', zIndex: 10,
  },
  barZone: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '2px', minWidth: 0 },
  barZoneColumn: { flexDirection: 'column', gap: '6px', minHeight: 0 },
  // Every button has the same size; below the screen they are a bit smaller
  // so the whole bar fits a narrow phone.
  buttonBelow: { flex: '0 0 28px', width: '28px', minWidth: '28px', height: '28px' },
  metric: {
    flex: '0 0 auto', minWidth: '28px', minHeight: '28px', margin: 0, padding: '1px 2px',
    border: 'none', background: 'transparent', color: '#e8ebf0', cursor: 'pointer',
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'system-ui, sans-serif', fontVariantNumeric: 'tabular-nums', touchAction: 'manipulation',
  },
  metricLine: { fontSize: '10px', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden' },
  withLed: { position: 'relative' },
  led: {
    position: 'absolute', top: '3px', right: '3px', width: '7px', height: '7px',
    borderRadius: '50%', boxShadow: '0 0 0 1px #1b1d22',
  },
  infoHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' },
  infoClose: {
    width: '26px', height: '26px', padding: 0, border: '1px solid #444', borderRadius: '7px',
    background: '#292929', color: '#fff', fontSize: '13px',
  },
  infoSection: { marginTop: '8px', marginBottom: '2px', color: '#d8dde5', fontWeight: 600 },
  infoNote: { marginTop: '4px', color: '#8a919c', fontSize: '11px', lineHeight: 1.35 },
  infoWarning: { marginTop: '4px', color: '#ff9f0a', fontSize: '12px', lineHeight: 1.35 },
  select: {
    maxWidth: '60%', padding: '3px 4px', borderRadius: '6px', border: '1px solid #444',
    background: '#292929', color: '#e8ebf0', fontSize: '12px',
  },
  panelButton: {
    padding: '4px 10px', borderRadius: '7px', border: '1px solid #4da3ff',
    background: '#2f5d8f', color: '#fff', fontSize: '12px',
  },
  problemMark: {
    width: '34px', height: '34px', borderRadius: '50%', border: '3px solid currentColor',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '20px', fontWeight: 700, fontFamily: 'system-ui, sans-serif', boxSizing: 'border-box',
  },
  loadingDetail: {
    maxWidth: '80%', color: '#8a919c', fontSize: '12px', textAlign: 'center',
    fontFamily: 'system-ui, sans-serif', lineHeight: 1.35,
  },
  banner: {
    position: 'absolute', left: '50%', top: '8px', transform: 'translateX(-50%)', zIndex: 3,
    padding: '10px 14px', borderRadius: '10px', background: 'rgba(20, 22, 27, 0.92)',
    border: '1px solid #3b3f47', color: '#e8ebf0', fontFamily: 'system-ui, sans-serif',
    fontSize: '13px', textAlign: 'center', maxWidth: '80%', boxSizing: 'border-box',
  },
  // In the corner, with the same padding on both sides: the text stays
  // centred.
  bannerWithClose: { padding: '10px 28px' },
  bannerClose: {
    position: 'absolute', top: '4px', right: '4px',
    width: '22px', height: '22px', padding: 0, border: 'none',
    background: 'transparent', color: '#8a919c', fontSize: '14px', lineHeight: 1,
  },
  info: {
    position: 'absolute', left: '8px', right: '8px', top: '8px', zIndex: 4,
    maxHeight: 'calc(100% - 16px)', overflowY: 'auto', touchAction: 'pan-y', boxSizing: 'border-box',
    padding: '10px 12px', borderRadius: '10px', background: 'rgba(20, 22, 27, 0.92)',
    border: '1px solid #3b3f47', fontFamily: 'system-ui, sans-serif', fontSize: '13px',
    display: 'flex', flexDirection: 'column', gap: '4px',
  },
  infoRow: { display: 'flex', justifyContent: 'space-between', gap: '12px' },
  infoLabel: { color: '#8a919c' },
  button: {
    flex: '0 0 34px', width: '34px', height: '34px', minWidth: '34px', margin: 0, padding: 0,
    border: '1px solid #444', borderRadius: '9px', background: '#292929', color: '#fff',
    display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '22px', lineHeight: 1, fontFamily: 'system-ui, sans-serif', touchAction: 'manipulation',
  },
  buttonBusy: { background: '#2f5d8f', borderColor: '#4da3ff' },
  buttonDocked: { borderColor: '#4da3ff' },
  icon: { display: 'block', margin: 'auto' },
  // A steady rotation of the centred icon, slow enough to read as "working".
  spinningIcon: {
    display: 'block', margin: 'auto', transformOrigin: '50% 50%',
    animation: 'stream-spinner 1.2s linear infinite',
  },
};

export default App;
