import React, { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';
import { activePeerConnection } from '../../src/components/emulator/net/ws_jsep_protocol_driver';

logger.setLevel('warn');

const TOOLBAR_WIDTH = 40;
const STATS_INTERVAL_MS = 1000;
// Give up showing the reconnect feedback if no frame arrives in this time.
const RECONNECT_FEEDBACK_MS = 15000;
const DEVICE_WIDTH = 540;
const DEVICE_HEIGHT = 1170;

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
function fittedScreen() {
  const viewport = viewportSize();
  // Fullscreen: the screen takes the whole display and the toolbar floats
  // over it, so a phone shaped like Android uses every pixel.
  if (document.fullscreenElement) {
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
  return value === null ? '–' : String(Math.round(value));
}

// What this browser's device offers and what Android sends, as label/value
// rows: CSS pixels (layout) and physical pixels (CSS × devicePixelRatio).
function deviceInfo(shownScreen, video) {
  const ratio = window.devicePixelRatio || 1;
  const viewport = viewportSize();
  const physical = (width, height) => `${Math.round(width * ratio)}×${Math.round(height * ratio)}`;
  return [
    ['Écran de l’appareil', `${physical(window.screen.width, window.screen.height)} px`],
    ['Fenêtre', `${viewport.width}×${viewport.height} CSS · ${physical(viewport.width, viewport.height)} px`],
    ['Densité', `×${ratio.toFixed(2)}`],
    ['Image affichée', `${shownScreen.width}×${shownScreen.height} CSS · ${physical(shownScreen.width, shownScreen.height)} px`],
    ['Flux Android', video ? `${video.width}×${video.height} px` : '–'],
  ];
}

// Samples the stream once per STATS_INTERVAL_MS:
// - ping: ICE round-trip time when the browser reports it, otherwise the time
//   of an HTTP request to the gateway (same network path);
// - server: video frames received from the emulator per second (Android only
//   sends a frame when the screen changes, so a still screen shows ~0);
// - phone: frames this browser actually displayed per second.
// Both frame rates are 0 while the Android screen does not change.
function useStreamStats(deviceRef, gatewayUrl) {
  const [stats, setStats] = useState({ ping: null, server: null, phone: null, video: null });

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
        let received = null;
        let ping = null;
        const connection = activePeerConnection();
        if (connection) {
          try {
            const report = await connection.getStats();
            report.forEach((entry) => {
              if (entry.type === 'inbound-rtp' && (entry.kind ?? entry.mediaType) === 'video') {
                received = entry.framesReceived ?? entry.framesDecoded ?? null;
              } else if (entry.type === 'candidate-pair' && entry.state === 'succeeded'
                && (entry.nominated || entry.selected)
                && typeof entry.currentRoundTripTime === 'number') {
                ping = entry.currentRoundTripTime * 1000;
              }
            });
          } catch (error) {
            console.warn('Stream statistics:', error);
          }
        }
        if (ping === null) {
          const start = performance.now();
          try {
            await fetch(`${gatewayUrl}/api/v1/ping`, { cache: 'no-store' });
            ping = performance.now() - start;
          } catch {
            ping = null;
          }
        }
        const rate = (current, before, seconds) => (
          current !== null && before !== null && current >= before ? (current - before) / seconds : null);
        const seconds = previous ? (now - previous.time) / 1000 : 0;
        if (!stopped) {
          setStats({
            ping,
            server: previous ? rate(received, previous.received, seconds) : null,
            phone: previous ? rate(shown, previous.shown, seconds) : null,
            video: video?.videoWidth ? { width: video.videoWidth, height: video.videoHeight } : null,
          });
        }
        previous = { time: now, received, shown };
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

function App() {
  const emulatorRef = useRef(null);
  const deviceRef = useRef(null);
  const feedbackTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const pointerDown = useRef(false);
  // Touch updates sent to the gateway: at most one request in flight. Press
  // and release are queued in order; while a request runs, intermediate moves
  // collapse into the latest one, so a drag never lags behind the finger.
  const touchSender = useRef({ inFlight: false, queue: [], pendingMove: null });
  const touchMarker = useRef(null);
  const reconnectTimer = useRef(null);
  const [screen, setScreen] = useState(fittedScreen);
  const row = screen.toolbar === 'side';
  const overlay = screen.toolbar === 'overlay';
  const [toolbarShown, setToolbarShown] = useState(true);
  useEffect(() => {
    // Entering fullscreen shows the floating toolbar briefly, then hides it.
    if (!overlay) return undefined;
    setToolbarShown(true);
    const timer = window.setTimeout(() => setToolbarShown(false), 3000);
    return () => window.clearTimeout(timer);
  }, [overlay]);
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
    const resize = () => setScreen(fittedScreen());
    window.addEventListener('resize', resize);
    window.visualViewport?.addEventListener('resize', resize);
    document.addEventListener('fullscreenchange', resize);
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
      document.removeEventListener('fullscreenchange', resize);
    };
  }, []);

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
      x: Math.max(0, Math.min(DEVICE_WIDTH - 1,
        Math.round((event.clientX - bounds.left) * DEVICE_WIDTH / bounds.width))),
      y: Math.max(0, Math.min(DEVICE_HEIGHT - 1,
        Math.round((event.clientY - bounds.top) * DEVICE_HEIGHT / bounds.height))),
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

  const queueTouch = (coordinates, pressed, move = false) => {
    const sender = touchSender.current;
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
          {showInfo && (
            <div style={styles.info} onClick={() => setShowInfo(false)} role="dialog" aria-label="Écran">
              {deviceInfo(screen, stats.video).map(([label, value]) => (
                <div key={label} style={styles.infoRow}>
                  <span style={styles.infoLabel}>{label}</span>
                  <span>{value}</span>
                </div>
              ))}
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
      {overlay && (
        <button
          style={{ ...styles.toolbarHandle, bottom: toolbarShown ? `${TOOLBAR_WIDTH + 6}px` : '6px' }}
          onClick={() => setToolbarShown((shown) => !shown)}
          aria-label={toolbarShown ? 'Masquer la barre' : 'Afficher la barre'}
        >{toolbarShown ? '▾' : '▴'}</button>
      )}
      <nav
        style={row ? styles.toolbar
          : overlay ? { ...styles.toolbarBelow, ...styles.toolbarOverlay, display: toolbarShown ? 'flex' : 'none' }
            : styles.toolbarBelow}
        aria-label="Contrôles Android"
      >
        <div
          style={{ ...styles.stats, ...(row ? null : styles.statsBelow) }}
          aria-label="Statistiques du flux (toucher pour les détails de l'écran)"
          role="button"
          tabIndex={0}
          onClick={() => setShowInfo((shown) => !shown)}
        >
          <span style={styles.statLabel}>ping</span>
          <span style={{ ...styles.statValue, color: pingColor(stats.ping) }}
            title="Aller-retour réseau jusqu'au serveur, en millisecondes">{formatValue(stats.ping)}</span>
          <span style={styles.statLabel}>srv</span>
          <span style={styles.statValue}
            title="Images par seconde envoyées par le serveur (≈0 quand l'écran Android ne bouge pas)">{formatValue(stats.server)}</span>
          <span style={styles.statLabel}>phone</span>
          <span style={styles.statValue}
            title="Images par seconde affichées par ce navigateur">{formatValue(stats.phone)}</span>
        </div>
        <div style={row ? styles.separator : styles.separatorBelow} aria-hidden="true" />
        <div style={{ ...styles.webControls, ...(row ? null : styles.groupBelow) }} aria-label="Contrôles du flux Web">
          <button
            className="tool-button"
            style={{ ...buttonStyle, ...(reconnecting ? styles.buttonBusy : null) }}
            onClick={manualReconnect}
            aria-label="Reconnecter la vidéo"
            aria-busy={reconnecting}
          >
            <Icon name="refresh" spinning={reconnecting} />
          </button>
          <button className="tool-button" style={buttonStyle} onClick={toggleFullscreen}
            aria-label="Plein écran"><Icon name="fullscreen" /></button>
          <span
            title={state}
            aria-label={`Connexion ${state}`}
            style={{ ...styles.status, background: state === 'connected' ? '#34c759' : '#ff9f0a' }}
          />
        </div>
        <div style={row ? styles.separator : styles.separatorBelow} aria-hidden="true" />
        <div style={{ ...styles.emulatorControls, ...(row ? null : styles.groupBelow) }} aria-label="Contrôles Android">
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('GoBack')} aria-label="Retour"><Icon name="back" /></button>
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('GoHome')} aria-label="Accueil"><Icon name="home" /></button>
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('AppSwitch')} aria-label="Applications récentes"><Icon name="recents" /></button>
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('AudioVolumeDown')} aria-label="Baisser le volume"><Icon name="volumeDown" /></button>
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('AudioVolumeUp')} aria-label="Monter le volume"><Icon name="volumeUp" /></button>
          <button className="tool-button" style={buttonStyle} onClick={() => sendKey('Power')} aria-label="Marche arrêt"><Icon name="power" /></button>
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
    boxSizing: 'border-box', display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '6px 2px',
    background: '#1b1d22', borderLeft: '1px solid #3b3f47', zIndex: 10,
  },
  toolbarOverlay: {
    position: 'fixed', left: 0, right: 0, bottom: 0, width: '100%',
    background: 'rgba(27, 29, 34, 0.85)', borderTop: '1px solid rgba(59, 63, 71, 0.85)',
  },
  toolbarHandle: {
    position: 'fixed', right: '6px', bottom: `${TOOLBAR_WIDTH + 6}px`, zIndex: 11,
    width: '28px', height: '22px', padding: 0, border: '1px solid rgba(85, 85, 85, 0.8)',
    borderRadius: '8px', background: 'rgba(27, 29, 34, 0.7)', color: '#d8dde5',
    fontSize: '14px', lineHeight: 1, touchAction: 'manipulation',
  },
  toolbarBelow: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', height: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'flex', flexDirection: 'row', alignItems: 'center',
    justifyContent: 'center', padding: '2px 6px',
    background: '#1b1d22', borderTop: '1px solid #3b3f47', zIndex: 10,
  },
  // Label above value, one column per statistic.
  statsBelow: {
    display: 'grid', gridAutoFlow: 'column', gridTemplateRows: 'auto auto',
    columnGap: '6px', justifyItems: 'center', flex: '0 0 auto',
  },
  // Below the screen the buttons share the width and shrink on narrow phones.
  buttonBelow: {
    flex: '1 1 30px', width: 'auto', minWidth: '24px', maxWidth: '40px', height: '32px',
  },
  separatorBelow: {
    width: '1px', height: '26px', flex: '0 0 1px', margin: '0 5px', background: '#555',
  },
  stats: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', lineHeight: 1.15,
  },
  info: {
    position: 'absolute', left: '8px', right: '8px', top: '8px', zIndex: 4,
    padding: '10px 12px', borderRadius: '10px', background: 'rgba(20, 22, 27, 0.92)',
    border: '1px solid #3b3f47', fontFamily: 'system-ui, sans-serif', fontSize: '13px',
    display: 'flex', flexDirection: 'column', gap: '4px',
  },
  infoRow: { display: 'flex', justifyContent: 'space-between', gap: '12px' },
  infoLabel: { color: '#8a919c' },
  statLabel: { fontSize: '9px', color: '#8a919c', marginTop: '3px' },
  statValue: { fontSize: '12px', fontWeight: 600, color: '#e8ebf0', minWidth: '3ch', textAlign: 'center' },
  groupBelow: { flexDirection: 'row', flex: '1 1 auto', gap: '3px', justifyContent: 'center' },
  webControls: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
  },
  separator: {
    width: '26px', height: '1px', flex: '0 0 1px', margin: '10px 0', background: '#555',
  },
  emulatorControls: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
  },
  button: {
    flex: '0 0 36px', width: '36px', height: '36px', minWidth: '36px', margin: 0, padding: 0,
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
  status: { width: '9px', height: '9px', flex: '0 0 9px', borderRadius: '50%' },
};

export default App;
