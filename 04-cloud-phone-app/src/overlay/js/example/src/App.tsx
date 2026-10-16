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

function fittedScreen() {
  const viewport = viewportSize();
  const availableHeight = Math.max(1, viewport.height);
  const availableWidth = Math.max(1, viewport.width - TOOLBAR_WIDTH);
  const width = Math.floor(Math.min(availableWidth, availableHeight * DEVICE_WIDTH / DEVICE_HEIGHT));
  return { width, height: Math.floor(width * DEVICE_HEIGHT / DEVICE_WIDTH) };
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

// Samples the stream once per STATS_INTERVAL_MS:
// - ping: ICE round-trip time when the browser reports it, otherwise the time
//   of an HTTP request to the gateway (same network path);
// - server: video frames received from the emulator per second (Android only
//   sends a frame when the screen changes, so a still screen shows ~0);
// - phone: frames this browser actually displayed per second.
function useStreamStats(deviceRef, gatewayUrl) {
  const [stats, setStats] = useState({ ping: null, server: null, phone: null });

  useEffect(() => {
    let previous = null;
    let busy = false;
    let stopped = false;

    const sample = async () => {
      if (busy) return;
      busy = true;
      try {
        const now = performance.now();
        const video = deviceRef.current?.querySelector('video');
        const quality = video?.getVideoPlaybackQuality?.();
        const shown = quality ? quality.totalVideoFrames - quality.droppedVideoFrames : null;
        let received = null;
        let ping = null;
        const connection = activePeerConnection();
        if (connection) {
          const report = await connection.getStats();
          report.forEach((entry) => {
            if (entry.type === 'inbound-rtp' && entry.kind === 'video') {
              received = entry.framesReceived ?? entry.framesDecoded ?? null;
            } else if (entry.type === 'candidate-pair' && entry.state === 'succeeded'
              && (entry.nominated || entry.selected)
              && typeof entry.currentRoundTripTime === 'number') {
              ping = entry.currentRoundTripTime * 1000;
            }
          });
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
    };
  }, [deviceRef, gatewayUrl]);

  return stats;
}

function App() {
  const emulatorRef = useRef(null);
  const deviceRef = useRef(null);
  const feedbackTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  const pointerDown = useRef(false);
  const touchQueue = useRef(Promise.resolve());
  const reconnectTimer = useRef(null);
  const [screen, setScreen] = useState(fittedScreen);
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

  // Manual ↻: show that the click was taken into account until the new
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
    return () => {
      window.removeEventListener('resize', resize);
      window.visualViewport?.removeEventListener('resize', resize);
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

  const queueTouch = (coordinates, pressed) => {
    touchQueue.current = touchQueue.current.then(() =>
      post('/api/v1/emulator/touch', { ...coordinates, pressed }));
  };

  const startTouch = (event) => {
    event.preventDefault();
    pointerDown.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    queueTouch(touchCoordinates(event), true);
  };

  const moveTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    queueTouch(touchCoordinates(event), true);
  };

  const endTouch = (event) => {
    if (!pointerDown.current) return;
    event.preventDefault();
    pointerDown.current = false;
    queueTouch(touchCoordinates(event), false);
  };

  return (
    <main style={styles.app}>
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
      <nav style={styles.toolbar} aria-label="Contrôles Android">
        <div style={styles.stats} aria-label="Statistiques du flux" role="status">
          <span style={styles.statLabel}>ping</span>
          <span style={{ ...styles.statValue, color: pingColor(stats.ping) }}
            title="Aller-retour réseau jusqu'au serveur, en millisecondes">{formatValue(stats.ping)}</span>
          <span style={styles.statLabel}>srv</span>
          <span style={styles.statValue}
            title="Images par seconde envoyées par le serveur (≈0 quand l'écran Android ne bouge pas)">{formatValue(stats.server)}</span>
          <span style={styles.statLabel}>tél</span>
          <span style={styles.statValue}
            title="Images par seconde affichées par ce navigateur">{formatValue(stats.phone)}</span>
        </div>
        <div style={styles.separator} aria-hidden="true" />
        <div style={styles.webControls} aria-label="Contrôles du flux Web">
          <button
            className="tool-button"
            style={{ ...styles.button, ...(reconnecting ? styles.buttonBusy : null) }}
            onClick={manualReconnect}
            aria-label="Reconnecter la vidéo"
            aria-busy={reconnecting}
          >
            <span style={reconnecting ? styles.spinningGlyph : styles.glyph}>↻</span>
          </button>
          <span
            title={state}
            aria-label={`Connexion ${state}`}
            style={{ ...styles.status, background: state === 'connected' ? '#34c759' : '#ff9f0a' }}
          />
        </div>
        <div style={styles.separator} aria-hidden="true" />
        <div style={styles.emulatorControls} aria-label="Contrôles Android">
          <button className="tool-button" style={styles.button} onClick={() => sendKey('GoBack')} aria-label="Retour">‹</button>
          <button className="tool-button" style={styles.button} onClick={() => sendKey('GoHome')} aria-label="Accueil">○</button>
          <button className="tool-button" style={styles.button} onClick={() => sendKey('AppSwitch')} aria-label="Applications récentes">□</button>
          <button className="tool-button" style={styles.button} onClick={() => sendKey('AudioVolumeDown')} aria-label="Baisser le volume">−</button>
          <button className="tool-button" style={styles.button} onClick={() => sendKey('AudioVolumeUp')} aria-label="Monter le volume">＋</button>
          <button className="tool-button" style={styles.button} onClick={() => sendKey('Power')} aria-label="Marche arrêt">⏻</button>
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
  touchLayer: {
    position: 'absolute', inset: 0, zIndex: 2, touchAction: 'none', cursor: 'default',
  },
  toolbar: {
    flex: `0 0 ${TOOLBAR_WIDTH}px`, alignSelf: 'stretch', width: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '6px 2px',
    background: '#1b1d22', borderLeft: '1px solid #3b3f47', zIndex: 10,
  },
  stats: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', lineHeight: 1.15,
  },
  statLabel: { fontSize: '9px', color: '#8a919c', marginTop: '3px' },
  statValue: { fontSize: '12px', fontWeight: 600, color: '#e8ebf0', minWidth: '3ch', textAlign: 'center' },
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
    fontSize: '22px', lineHeight: 1, fontFamily: 'system-ui, sans-serif', touchAction: 'manipulation',
  },
  buttonBusy: { background: '#2f5d8f', borderColor: '#4da3ff' },
  glyph: { display: 'inline-block' },
  spinningGlyph: { display: 'inline-block', animation: 'stream-spinner 0.8s linear infinite' },
  status: { width: '9px', height: '9px', flex: '0 0 9px', borderRadius: '50%' },
};

export default App;
