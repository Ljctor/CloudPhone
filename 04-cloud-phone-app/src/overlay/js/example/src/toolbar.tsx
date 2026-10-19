// The page's toolbar and its folding. The colours it shows come from
// toolbarStatus.ts.
import { useEffect, useRef, useState } from 'react';
import { tr } from './i18n';
import { Icon } from './icons';
import { formatValue } from './serverInfo';
import { styles } from './styles';
import { ledColor, pingColor } from './toolbarStatus';

function toggleFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen?.().catch(() => {});
  } else {
    document.documentElement.requestFullscreen?.({ navigationUI: 'hide' }).catch(() => {});
  }
}

const LONG_PRESS_MS = 500;

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

// The bar's folding: folded or not, fullscreen or not, the unfold handle's
// place, and folding 3 s after entering fullscreen (settings autoFold, unless
// docked). readSettings: the stored settings, read when fullscreen starts.
export function useBarFold(readSettings) {
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
  useEffect(() => {
    const folder = () => {
      const current = readSettings();
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
  return { barFolded, setBarFolded, fullscreen, foldButtonRef, handlePosition, setHandlePosition, foldBar };
}

// The toolbar: Android's keys, the metrics block, the options, reconnect
// (with the connection LED), fullscreen and folding; and the handle that
// unfolds a folded bar. placement: 'side', 'below' or 'overlay' (layout).
export function Toolbar({
  placement, fold, docked, setDocked, stream, problem, reconnecting, onReconnect, stats, panel, onInfo, onOptions, sendKey,
}) {
  const foldPress = useRef({ timer: null, long: false });
  const row = placement === 'side';
  const overlay = placement === 'overlay';
  const buttonStyle = row ? styles.button : { ...styles.button, ...styles.buttonBelow };
  const keyButton = (key, label, icon) => (
    <button className="tool-button" style={buttonStyle} onClick={() => sendKey(key)}
      aria-label={label}><Icon name={icon} /></button>
  );
  const connected = stream === 'connected';
  // The connection LED sits in the refresh button's corner.
  const reloadButton = (
    <button
      className="tool-button"
      style={{ ...buttonStyle, ...styles.withLed, ...(reconnecting ? styles.buttonBusy : null) }}
      onClick={onReconnect}
      aria-label={tr('Reconnecter la vidéo')}
      aria-busy={reconnecting}
    >
      <Icon name="refresh" spinning={reconnecting} />
      <span
        title={stream}
        aria-label={tr('Connexion {state}', { state: stream })}
        style={{ ...styles.led, background: ledColor(problem, connected) }}
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
      ref={fold.foldButtonRef}
      className="tool-button"
      style={{ ...buttonStyle, ...(docked ? styles.buttonDocked : null) }}
      aria-label={docked ? tr('Barre fixe : toucher pour la rendre flottante')
        : tr('Replier la barre (appui long : barre fixe)')}
      aria-pressed={docked}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={() => {
        foldPress.current.long = false;
        window.clearTimeout(foldPress.current.timer);
        foldPress.current.timer = window.setTimeout(() => {
          foldPress.current.long = true;
          navigator.vibrate?.(20);
          setDocked(true);
        }, LONG_PRESS_MS);
      }}
      onPointerUp={() => window.clearTimeout(foldPress.current.timer)}
      onPointerCancel={() => window.clearTimeout(foldPress.current.timer)}
      onPointerLeave={() => window.clearTimeout(foldPress.current.timer)}
      onClick={() => {
        if (foldPress.current.long) return;
        if (docked) setDocked(false);
        else fold.foldBar.current();
      }}
    ><Icon name={row ? 'foldSide' : 'fold'} /></button>
  );
  const zoneStyle = row ? { ...styles.barZone, ...styles.barZoneColumn } : styles.barZone;
  // The ping and the frames per second this device shows, one above the
  // other: opens the information panel on its client tab.
  const metricsBlock = (
    <button className="metric-link" style={styles.metric}
      onClick={onInfo}
      aria-label={tr('Informations : client et serveur')} aria-expanded={panel === 'info'}>
      <span style={{ ...styles.metricLine, color: pingColor(stats.ping) }}>{formatValue(stats.ping)}ms</span>
      <span style={{ ...styles.metricLine, color: '#e8ebf0' }}>{formatValue(stats.phone)}fps</span>
    </button>
  );
  const optionsButton = (
    <button className="tool-button" style={buttonStyle} onClick={onOptions}
      aria-label={tr('Options et plugins')} title={tr('Options et plugins')} aria-expanded={panel === 'options'}>
      <Icon name="cog" />
    </button>
  );
  return (
    <>
      {fold.fullscreen && fold.barFolded && (
        <FloatingHandle
          label={tr('Afficher la barre (glisser pour déplacer)')}
          position={fold.handlePosition}
          onMove={(position) => fold.setHandlePosition(position)}
          onClick={() => fold.setBarFolded(false)}
        ><Icon name="unfold" /></FloatingHandle>
      )}
      <nav
        style={row ? styles.toolbar
          : overlay ? { ...styles.toolbarBar, ...styles.toolbarOverlay, display: fold.barFolded ? 'none' : 'grid' }
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
          {fold.fullscreen && foldButton}
        </div>
      </nav>
    </>
  );
}
