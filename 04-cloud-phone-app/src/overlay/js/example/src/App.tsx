import { LANGUAGES, defaultLanguage, setLanguage, tr } from './i18n';
import { emitTap, usePlugins } from './plugins';
import React, { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';
import { sendInputEvent } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import Proto from '../../src/proto/emulator_controller_pb';
import { TOOLBAR_WIDTH, styles } from './styles';
import { postFetch, postHeaders } from './api';
import { LogFilter, LogList, Toasts, pageLog, useLog, useServerLog, useToasts } from './logs';
import { Icon } from './icons';
import { AlertsPanel, useAlerts } from './notify';
import { formatValue, serverSections } from './serverInfo';
import { ServerPanel } from './serverPanel';
import { EmulatorSettings, useDisplayState, useEmulatorSettings } from './androidSettings';
import { useServerState } from './serverState';
import { bannerShown, diagnose } from './diagnose';
import { Banner, LEVEL_COLORS, StatusCover, useDismissed } from './banner';
import { useStreamStats } from './useStreamStats';

logger.setLevel('warn');

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

function pingColor(ms) {
  if (ms === null) return '#8a919c';
  if (ms < 60) return '#34c759';
  if (ms < 150) return '#ff9f0a';
  return '#ff453a';
}

const LONG_PRESS_MS = 500;

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
  // A plugin's dialog open over the options panel: { plugin, option }.
  const [pluginDialog, setPluginDialog] = useState(null);
  useEffect(() => { if (panel !== 'options') setPluginDialog(null); }, [panel]);
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
  // Where and when the current touch started, for plugins' onTap.
  const touchStart = useRef(null);
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
  useServerLog(gatewayUrl);
  const logs = useLog(panel === 'info');
  const [toasts, dismissToast] = useToasts();
  const alerts = useAlerts(gatewayUrl, panel === 'options');
  const pluginLayer = useRef(null);
  const plugins = usePlugins({
    gatewayUrl, deviceRef, layerRef: pluginLayer, screenWidth: screen.width, settings, postFetch, postHeaders,
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

  const loggedState = useRef(null);
  const handleStreamState = (nextState) => {
    // The stream reports its state often; only changes are logged.
    if (nextState !== loggedState.current) {
      loggedState.current = nextState;
      const said = { connected: 'Vidéo connectée', connecting: 'Vidéo en connexion…', disconnected: 'Vidéo coupée' }[nextState];
      pageLog('normal', said ? tr(said) : tr('Vidéo : {state}', { state: nextState }));
    }
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
  const [dismissed, setDismissed] = useDismissed(problem);
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

  const post = (path, body) => postFetch(`${gatewayUrl}${path}`, {
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
      if (inputPath.current === 'HTTP') pageLog('normal', tr('Les touches passent de nouveau par le canal de données'));
      inputPath.current = 'data channel';
      return;
    }
    // The session fell back to the server path: slower, worth a toast.
    if (inputPath.current !== 'HTTP') {
      pageLog('warning', tr('Les touches passent par le serveur (canal de données fermé) : elles peuvent être plus lentes'),
        { notify: true });
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
    const coordinates = touchCoordinates(event);
    touchStart.current = { ...coordinates, time: performance.now() };
    queueTouch(coordinates, true);
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
    const coordinates = touchCoordinates(event);
    queueTouch(coordinates, false);
    tellPlugins(coordinates, event.type === 'pointercancel');
  };

  // Plugins observe the user's touches (api.onTap), after they were sent:
  // tap, long press (500 ms, Android's long-press time) or swipe (moved more
  // than 4 % of the screen's width), as fractions of the screen.
  const tellPlugins = (end, cancelled) => {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start || cancelled) return;
    const moved = Math.hypot(end.x - start.x, end.y - start.y) > display.width * 0.04;
    const kind = moved ? 'swipe' : performance.now() - start.time >= 500 ? 'long' : 'tap';
    const tap = { x: start.x / display.width, y: start.y / display.height, kind };
    if (moved) tap.end = { x: end.x / display.width, y: end.y / display.height };
    emitTap(tap);
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
  const serverRows = serverSections({
    server, configured: displayState?.configured, display, stats,
  });
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
  // A section that folds under its title, folded at first; the state is
  // kept with the other settings.
  const fold = (id, title, content) => {
    const folded = settings.foldedSections?.[id] ?? true;
    return (
      <details open={!folded} onToggle={(event) => {
        const now = !event.currentTarget.open;
        if (now !== folded) updateSettings({ foldedSections: { ...settings.foldedSections, [id]: now } });
      }}>
        <summary style={{ ...styles.infoSection, cursor: 'pointer' }}>{tr(title)}</summary>
        {!folded && content}
      </details>
    );
  };
  // Which levels the log lists show, kept with the settings.
  const logFilter = (
    <LogFilter value={settings.logFilter} onChange={(logFilter) => updateSettings({ logFilter })} />
  );
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
  // A plugin's options, cut into foldable sub-sections at each
  // { type: 'section', key, label, folded? } (folded: its default state).
  const pluginSections = (plugin) => {
    const parts = [{ section: null, items: [] }];
    (plugin.instance.options ?? []).forEach((option, index) => {
      if (option.type === 'section') parts.push({ section: option, items: [] });
      else parts[parts.length - 1].items.push(pluginOption(plugin, option, index));
    });
    return parts.map(({ section, items }, index) => {
      if (!section) return <React.Fragment key="top">{items}</React.Fragment>;
      const id = `${plugin.id}:${section.key ?? section.label}`;
      const folded = settings.foldedPlugins?.[id] ?? Boolean(section.folded);
      return (
        <details key={id} open={!folded} style={styles.pluginSection}
          onToggle={(event) => {
            const now = !event.currentTarget.open;
            if (now !== folded) updateSettings({ foldedPlugins: { ...settings.foldedPlugins, [id]: now } });
          }}>
          <summary style={styles.pluginSectionTitle}>{tr(section.label)}</summary>
          {items}
        </details>
      );
    });
  };

  const pluginOption = (plugin, option, index) => {
    const key = `${plugin.id}-${index}`;
    if (!(option.visible?.() ?? true)) return null;
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
      return (
        <label key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <input type="text" inputMode="numeric" pattern="[0-9]*" maxLength={12} style={styles.numberInput}
            placeholder={(typeof option.placeholder === 'function' ? option.placeholder() : option.placeholder) ?? ''} value={settings.plugins?.[plugin.id]?.[option.key] ?? ''}
            onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value.replace(/\D/g, ''))} />
        </label>
      );
    }
    if (option.type === 'choice') {
      const choices = (typeof option.choices === 'function' ? option.choices() : option.choices) ?? [];
      return (
        <label key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <select style={styles.select} value={settings.plugins?.[plugin.id]?.[option.key] ?? choices[0]?.value ?? ''}
            onChange={(event) => setPluginOption(plugin.id, option.key, event.target.value)}>
            {choices.map((choice) => (
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
    if (option.type === 'buttons') {
      return (
        <div key={key} style={styles.infoRow}>
          <span style={styles.infoLabel}>{tr(option.label)}</span>
          <span style={styles.buttonGroup}>
            {(option.buttons ?? []).map((button) => (
              <button key={button.label} style={styles.smallButton} disabled={button.disabled?.() ?? false}
                onClick={() => Promise.resolve(button.run?.()).catch((error) => console.error(error))}>
                {tr(button.label)}
              </button>
            ))}
          </span>
        </div>
      );
    }
    if (option.type === 'dialog') {
      // select: a radio button before the label, one of a group sharing
      // the stored key (the first of the group when nothing is stored).
      const select = option.select;
      const stored = select && settings.plugins?.[plugin.id]?.[select.key];
      return (
        <div key={key} style={styles.infoRow}>
          {select ? (
            <label style={{ ...styles.infoLabel, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <input type="radio" name={`${plugin.id}-${select.key}`}
                checked={(stored ?? select.default) === select.value}
                onChange={() => setPluginOption(plugin.id, select.key, select.value)} />
              {tr(option.label)}
            </label>
          ) : <span style={styles.infoLabel}>{tr(option.label)}</span>}
          <button style={styles.panelButton} onClick={() => setPluginDialog({ plugin, option })}>
            {tr(option.button ?? 'Configurer')}
          </button>
        </div>
      );
    }
    if (option.type === 'status') {
      const value = option.value?.() ?? '–';
      const href = option.href?.();
      return row2(tr(option.label), href
        ? <a href={href} target="_blank" rel="noreferrer" style={styles.link}>{value}</a> : value);
    }
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
          <StatusCover problem={problem} stream={state} reconnecting={reconnecting} />
          <Banner problem={problem} dismissed={dismissed} dismiss={setDismissed} />
          <div ref={pluginLayer} style={styles.pluginLayer} aria-hidden="true" />
          <Toasts toasts={toasts} dismiss={dismissToast}
            top={bannerShown(problem, dismissed) ? '72px' : '8px'} />
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
                <ServerPanel
                  sections={sections(serverRows)}
                  viewers={server.value?.viewers}
                  gatewayUrl={gatewayUrl}
                  settingsForm={(
                    <EmulatorSettings
                      gatewayUrl={gatewayUrl}
                      settings={emulatorSettings}
                      refresh={refreshEmulatorSettings}
                      rowStyle={styles.infoRow}
                      labelStyle={styles.infoLabel}
                      buttonStyle={styles.panelButton}
                    />
                  )}
                  logs={fold('serverLogs', 'Journaux du serveur', <>
                    {logFilter}
                    <LogList entries={logs.server} filter={settings.logFilter} rowStyle={styles.infoRow}
                      labelStyle={styles.infoLabel} />
                  </>)}
                />
              )}
              {panel === 'info' && infoTab === 'client' && (
                <div role="tabpanel">
                  {sections(clientSections)}
                  {fold('clientLogs', 'Journaux du client', <>
                    {logFilter}
                    <LogList entries={logs.page} filter={settings.logFilter} rowStyle={styles.infoRow}
                      labelStyle={styles.infoLabel} />
                  </>)}
                </div>
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
                  <AlertsPanel alerts={alerts} />
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
                      {pluginSections(plugin)}
                    </details>
                  ))}
                </>
              )}
            </div>
          )}
          {panel === 'options' && pluginDialog && (
            <div style={styles.pluginDialog} role="dialog" aria-label={tr(pluginDialog.option.title ?? pluginDialog.option.label)}>
              <div style={styles.infoHeader}>
                <strong>{tr(pluginDialog.option.title ?? pluginDialog.option.label)}</strong>
                <button style={styles.infoClose} onClick={() => setPluginDialog(null)} aria-label={tr('Fermer')}>✕</button>
              </div>
              {(pluginDialog.option.options ?? []).map((option, index) => pluginOption(pluginDialog.plugin, option, `dialog-${index}`))}
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

export default App;
