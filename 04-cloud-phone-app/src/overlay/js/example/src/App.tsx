import React, { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';
import { activePeerConnection, sendInputEvent } from '../../src/components/emulator/net/ws_jsep_protocol_driver';
import Proto from '../../src/proto/emulator_controller_pb';

logger.setLevel('warn');

const TOOLBAR_WIDTH = 40;
const STATS_INTERVAL_MS = 1000;
// Touches over the WebRTC data channel reach the channel but this emulator
// build (36.6.11) does not apply them: keep the HTTP path until that works.
const USE_DATA_CHANNEL = false;
// Give up showing the reconnect feedback if no frame arrives in this time.
const RECONNECT_FEEDBACK_MS = 15000;
// Android's display size until the gateway reports the real one.
const DEFAULT_DISPLAY = { width: 540, height: 1170 };

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
function fittedScreen(display = DEFAULT_DISPLAY, folded = false) {
  const DEVICE_WIDTH = display.width;
  const DEVICE_HEIGHT = display.height;
  const viewport = viewportSize();
  // Fullscreen or folded bar: the screen takes the whole window and the bar
  // floats over it, so a phone shaped like Android uses every pixel.
  if (document.fullscreenElement || folded) {
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

function formatBitrate(kbps) {
  if (kbps === null || kbps === undefined) return '–';
  return kbps >= 1000 ? `${(kbps / 1000).toFixed(1)}M` : `${Math.round(kbps)}k`;
}

// Per-viewer page settings, kept in this browser only.
const SETTINGS_KEY = 'cloudphone.settings';
const DEFAULT_SETTINGS = { touchMarker: true, autoFold: true, handle: null };

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
function deviceInfo(shownScreen, video, display) {
  const ratio = window.devicePixelRatio || 1;
  const viewport = viewportSize();
  const physical = (width, height) => `${Math.round(width * ratio)}×${Math.round(height * ratio)}`;
  return [
    ['Écran de l’appareil', `${physical(window.screen.width, window.screen.height)} px`],
    ['Fenêtre', `${viewport.width}×${viewport.height} CSS · ${physical(viewport.width, viewport.height)} px`],
    ['Densité', `×${ratio.toFixed(2)}`],
    ['Image affichée', `${shownScreen.width}×${shownScreen.height} CSS · ${physical(shownScreen.width, shownScreen.height)} px`],
    ['Écran Android', `${display.width}×${display.height} px`],
    ['Flux vidéo reçu', video ? `${video.width}×${video.height} px` : '–'],
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
        if (!current) return;
        if (current.moved) onMove(place, true);
        else onClick();
      }}
      onPointerCancel={() => { drag.current = null; }}
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
  // Open panel over the screen: 'network' (from ping/fps) or 'display'
  // (from the stream information block), with the display settings.
  const [panel, setPanel] = useState(null);
  const [settings, setSettings] = useState(loadSettings);
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
  const [screen, setScreen] = useState(() => fittedScreen(DEFAULT_DISPLAY));
  const row = screen.toolbar === 'side';
  const overlay = screen.toolbar === 'overlay';
  useEffect(() => {
    const folder = () => {
      if (!document.fullscreenElement || !loadSettings().autoFold) return;
      const timer = window.setTimeout(() => setBarFolded(true), 3000);
      return () => window.clearTimeout(timer);
    };
    let cancel = null;
    const changed = () => {
      cancel?.();
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
  // The gateway listens on the port right after the page's own (8000 → 8001),
  // so several instances can share a host.
  const pagePort = Number(window.location.port) || (window.location.protocol === 'https:' ? 443 : 80);
  const gateway = `${window.location.hostname}:${pagePort + 1}`;
  const gatewayUrl = `${window.location.protocol}//${gateway}`;
  const stats = useStreamStats(deviceRef, gatewayUrl);

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
    const resize = () => setScreen(fittedScreen(display, barFolded));
    resize();
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    document.addEventListener('fullscreenchange', resize);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
      document.removeEventListener('fullscreenchange', resize);
    };
  }, [display, barFolded]);

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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((response) => {
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  }).catch((error) => console.error('Android control:', error));

  const sendKey = (key) => post('/api/v1/emulator/key', { key });

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
      aria-label="Reconnecter la vidéo"
      aria-busy={reconnecting}
    >
      <Icon name="refresh" spinning={reconnecting} />
      <span
        title={state}
        aria-label={`Connexion ${state}`}
        style={{ ...styles.led, background: connected ? '#34c759' : '#ff9f0a' }}
      />
    </button>
  );
  const fullscreenButton = (
    <button className="tool-button" style={buttonStyle} onClick={toggleFullscreen}
      aria-label="Plein écran"><Icon name="fullscreen" /></button>
  );
  const foldButton = (
    <button className="tool-button" style={buttonStyle} onClick={() => setBarFolded(true)}
      aria-label="Replier la barre"><Icon name={row ? 'foldSide' : 'fold'} /></button>
  );
  const togglePanel = (name) => setPanel((open) => (open === name ? null : name));
  const zoneStyle = row ? { ...styles.barZone, ...styles.barZoneColumn } : styles.barZone;
  // Ping and displayed fps; tap for network and connectivity details.
  const networkBlock = (
    <button className="tool-button" style={styles.metric} onClick={() => togglePanel('network')}
      aria-label="Réseau et connectivité">
      <span style={{ ...styles.metricLine, color: pingColor(stats.ping) }}>{formatValue(stats.ping)}ms</span>
      <span style={styles.metricLine}>{formatValue(stats.phone)}fps</span>
    </button>
  );
  // Stream resolution and bitrate; tap for display details and settings.
  const streamBlock = (
    <button className="tool-button" style={{ ...styles.metric, ...(row ? null : styles.metricWide) }}
      onClick={() => togglePanel('display')} aria-label="Écran, flux et réglages">
      {row ? (
        <>
          <span style={styles.metricLine}>{stats.video?.width ?? display.width}</span>
          <span style={styles.metricLine}>{stats.video?.height ?? display.height}</span>
        </>
      ) : (
        <span style={styles.metricLine}>
          {stats.video ? `${stats.video.width}×${stats.video.height}` : `${display.width}×${display.height}`}
        </span>
      )}
      <span style={styles.metricLine}>{formatBitrate(stats.bitrate)}</span>
    </button>
  );
  const row2 = (label, value) => (
    <div key={label} style={styles.infoRow}>
      <span style={styles.infoLabel}>{label}</span>
      <span>{value}</span>
    </div>
  );
  const networkRows = [
    ['Ping', stats.ping === null ? '–' : `${Math.round(stats.ping)} ms (${stats.pingSource})`],
    ['Connexion', stats.connection ?? state],
    ['Chemin', stats.path ?? '–'],
    ['Débit vidéo', stats.bitrate === null ? '–' : `${Math.round(stats.bitrate)} kbit/s`],
    ['Images reçues', `${formatValue(stats.server)} /s`],
    ['Images affichées', `${formatValue(stats.phone)} /s`],
    ['Images perdues', formatValue(stats.framesDropped)],
    ['Paquets perdus', formatValue(stats.packetsLost)],
    ['Gigue', stats.jitter === null ? '–' : `${Math.round(stats.jitter)} ms`],
    ['Tampon vidéo', stats.bufferDelay === null ? '–' : `${Math.round(stats.bufferDelay)} ms`],
    ['Codec', stats.codec ?? '–'],
    ['Touches via', inputPath.current],
  ];
  const toggle = (label, key) => (
    <label key={key} style={styles.infoRow}>
      <span style={styles.infoLabel}>{label}</span>
      <input type="checkbox" checked={settings[key]}
        onChange={(event) => updateSettings({ [key]: event.target.checked })} />
    </label>
  );

  return (
    <main style={{ ...styles.app, flexDirection: row ? 'row' : 'column' }}>
      <style>{`
        @keyframes stream-spinner {
          to { transform: rotate(360deg); }
        }
        .tool-button:active { background: #3a6ea5 !important; border-color: #4da3ff !important; }
      `}</style>
      <section style={styles.screen} aria-label="Écran Android">
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
          {state !== 'connected' && (
            <div style={styles.loading} role="status" aria-live="polite">
              <span style={styles.spinner} aria-hidden="true" />
              <span style={styles.loadingText}>{reconnecting ? 'Reconnexion…' : 'Connexion au flux…'}</span>
            </div>
          )}
          {panel && (
            <div style={styles.info} role="dialog"
              aria-label={panel === 'network' ? 'Réseau et connectivité' : 'Écran et réglages'}>
              <div style={styles.infoHeader}>
                <strong>{panel === 'network' ? 'Réseau et connectivité' : 'Écran et réglages'}</strong>
                <button style={styles.infoClose} onClick={() => setPanel(null)} aria-label="Fermer">✕</button>
              </div>
              {panel === 'network'
                ? networkRows.map(([label, value]) => row2(label, value))
                : (
                  <>
                    {deviceInfo(screen, stats.video, display).map(([label, value]) => row2(label, value))}
                    <div style={styles.infoSection}>Réglages de cette page</div>
                    {toggle('Point sous le doigt', 'touchMarker')}
                    {toggle('Replier la barre en plein écran', 'autoFold')}
                    <div style={styles.infoNote}>
                      La résolution d’Android se règle sur le serveur
                      (03-android-emulator/scripts/set-resolution.sh) et redémarre Android.
                    </div>
                  </>
                )}
            </div>
          )}
          <div ref={touchMarker} style={styles.touchMarker} aria-hidden="true" />
          <div
            style={styles.touchLayer}
            aria-label="Surface tactile Android"
            onPointerDown={startTouch}
            onPointerMove={moveTouch}
            onPointerUp={endTouch}
            onPointerCancel={endTouch}
          />
        </div>
      </section>
      {barFolded && (
        <FloatingHandle
          label="Afficher la barre (glisser pour déplacer)"
          position={settings.handle}
          onMove={(position, done) => (done ? updateSettings({ handle: position })
            : setSettings((current) => ({ ...current, handle: position })))}
          onClick={() => setBarFolded(false)}
        ><Icon name="unfold" /></FloatingHandle>
      )}
      <nav
        style={row ? styles.toolbar
          : overlay ? { ...styles.toolbarBar, ...styles.toolbarOverlay, display: barFolded ? 'none' : 'grid' }
            : styles.toolbarBar}
        aria-label="Contrôles Android"
      >
        {/* Same order beside the screen (top to bottom) and below it (left to
            right): the phone's physical keys and the network metrics,
            Android's recents, home and back centred, then the stream
            information and the page's own buttons. */}
        <div style={{ ...zoneStyle, justifyContent: 'flex-start' }}>
          {keyButton('Power', 'Marche arrêt', 'power')}
          {keyButton('AudioVolumeDown', 'Baisser le volume', 'volumeDown')}
          {keyButton('AudioVolumeUp', 'Monter le volume', 'volumeUp')}
          {networkBlock}
        </div>
        <div style={zoneStyle} aria-label="Navigation Android">
          {keyButton('AppSwitch', 'Applications récentes', 'recents')}
          {keyButton('GoHome', 'Accueil', 'home')}
          {keyButton('GoBack', 'Retour', 'back')}
        </div>
        <div style={{ ...zoneStyle, justifyContent: 'flex-end' }}>
          {streamBlock}
          {reloadButton}
          {fullscreenButton}
          {foldButton}
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
  barZone: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '3px', minWidth: 0 },
  barZoneColumn: { flexDirection: 'column', gap: '6px', minHeight: 0 },
  // Every button has the same size; below the screen they are a bit smaller
  // so the whole bar fits a narrow phone.
  buttonBelow: { flex: '0 0 30px', width: '30px', minWidth: '30px', height: '30px' },
  metric: {
    flex: '0 0 auto', minWidth: '30px', minHeight: '30px', margin: 0, padding: '1px 3px',
    border: '1px solid #444', borderRadius: '9px', background: '#292929', color: '#e8ebf0',
    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', touchAction: 'manipulation',
  },
  metricWide: { flex: '1 1 auto', minWidth: 0 },
  metricLine: { fontSize: '9px', lineHeight: 1.2, whiteSpace: 'nowrap', overflow: 'hidden' },
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
  infoSection: { marginTop: '8px', color: '#d8dde5', fontWeight: 600 },
  infoNote: { marginTop: '4px', color: '#8a919c', fontSize: '11px', lineHeight: 1.35 },
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
  icon: { display: 'block', margin: 'auto' },
  // A steady rotation of the centred icon, slow enough to read as "working".
  spinningIcon: {
    display: 'block', margin: 'auto', transformOrigin: '50% 50%',
    animation: 'stream-spinner 1.2s linear infinite',
  },
};

export default App;
