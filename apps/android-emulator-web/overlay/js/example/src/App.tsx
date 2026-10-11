import React, { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';

logger.setLevel('warn');

const TOOLBAR_WIDTH = 42;
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

function App() {
  const emulatorRef = useRef(null);
  const pointerDown = useRef(false);
  const touchQueue = useRef(Promise.resolve());
  const reconnectTimer = useRef(null);
  const [screen, setScreen] = useState(fittedScreen);
  const [state, setState] = useState('connecting');
  const [streamMounted, setStreamMounted] = useState(true);
  const [streamGeneration, setStreamGeneration] = useState(0);
  const gateway = `${window.location.hostname}:8001`;
  const gatewayUrl = `${window.location.protocol}//${gateway}`;

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
      `}</style>
      <section style={styles.screen} aria-label="Écran Android">
        <div style={{ ...styles.device, width: screen.width, height: screen.height }}>
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
              <span style={styles.loadingText}>Connexion au flux…</span>
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
        <div style={styles.webControls} aria-label="Contrôles du flux Web">
          <button style={styles.button} onClick={reconnectStream} aria-label="Reconnecter la vidéo">↻</button>
          <span
            title={state}
            aria-label={`Connexion ${state}`}
            style={{ ...styles.status, background: state === 'connected' ? '#34c759' : '#ff9f0a' }}
          />
        </div>
        <div style={styles.separator} aria-hidden="true" />
        <div style={styles.emulatorControls} aria-label="Contrôles Android">
          <button style={styles.button} onClick={() => sendKey('GoBack')} aria-label="Retour">‹</button>
          <button style={styles.button} onClick={() => sendKey('GoHome')} aria-label="Accueil">○</button>
          <button style={styles.button} onClick={() => sendKey('AppSwitch')} aria-label="Applications récentes">□</button>
          <button style={styles.button} onClick={() => sendKey('AudioVolumeDown')} aria-label="Baisser le volume">−</button>
          <button style={styles.button} onClick={() => sendKey('AudioVolumeUp')} aria-label="Monter le volume">＋</button>
          <button style={styles.button} onClick={() => sendKey('Power')} aria-label="Marche arrêt">⏻</button>
        </div>
      </nav>
    </main>
  );
}

const styles = {
  app: {
    position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column',
    overflow: 'hidden', background: '#20242b', color: '#fff', touchAction: 'none',
  },
  screen: {
    position: 'absolute', top: 0, bottom: 0, left: 0, right: `${TOOLBAR_WIDTH}px`,
    display: 'flex', alignItems: 'center',
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
    position: 'fixed', top: 0, right: 0, bottom: 0,
    height: '100%', width: `${TOOLBAR_WIDTH}px`,
    boxSizing: 'border-box', display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', padding: '8px 3px',
    background: '#1b1d22', borderLeft: '1px solid #3b3f47', zIndex: 10,
  },
  webControls: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px',
  },
  separator: {
    width: '26px', height: '1px', flex: '0 0 1px', margin: '12px 0', background: '#555',
  },
  emulatorControls: {
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px',
  },
  button: {
    flex: '0 0 36px', width: '36px', height: '36px', minWidth: '36px', margin: 0, padding: 0,
    border: '1px solid #444', borderRadius: '9px', background: '#292929', color: '#fff',
    fontSize: '22px', lineHeight: 1, fontFamily: 'system-ui, sans-serif', touchAction: 'manipulation',
  },
  status: { width: '9px', height: '9px', flex: '0 0 9px', borderRadius: '50%' },
};

export default App;
