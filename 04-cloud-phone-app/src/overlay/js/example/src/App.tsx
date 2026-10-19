import { tr } from './i18n';
import { usePlugins } from './plugins';
import { useEffect, useRef, useState } from 'react';
import { Emulator, logger } from '../../src';
import { TOOLBAR_WIDTH, styles } from './styles';
import { postFetch, postHeaders } from './api';
import { LogFilter, LogList, Toasts, pageLog, useLog, useServerLog, useToasts } from './logs';
import { AlertsPanel, useAlerts } from './notify';
import { formatValue, serverSections } from './serverInfo';
import { ServerPanel } from './serverPanel';
import { EmulatorSettings, useDisplayState, useEmulatorSettings } from './androidSettings';
import { useServerState } from './serverState';
import { bannerShown, diagnose } from './diagnose';
import { Banner, StatusCover, useDismissed } from './banner';
import { useStreamStats } from './useStreamStats';
import { useInput } from './useInput';
import { Toolbar, useBarFold } from './toolbar';
import { infoSections } from './infoRows';
import { PluginDialog, PluginList, usePluginDialog } from './pluginOptions';
import { ViewerOptions, loadSettings, useViewerSettings } from './viewerSettings';

logger.setLevel('warn');

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

function App() {
  const emulatorRef = useRef(null);
  const deviceRef = useRef(null);
  const feedbackTimer = useRef(null);
  const [reconnecting, setReconnecting] = useState(false);
  // Open panel over the screen: 'info' (from the ping/fps block, with a
  // client and a server tab) or 'options' (from the cog).
  const [panel, setPanel] = useState(null);
  // A plugin's dialog open over the options panel: { plugin, option }.
  const [pluginDialog, setPluginDialog] = usePluginDialog(panel);
  const [infoTab, setInfoTab] = useState('client');
  const serverTab = panel === 'info' && infoTab === 'server';
  // Before any tr() of this render: sets the page's language.
  const [settings, updateSettings] = useViewerSettings();
  const reconnectTimer = useRef(null);
  const [display, setDisplay] = useState(DEFAULT_DISPLAY);
  const barFold = useBarFold(loadSettings);
  const { barFolded } = barFold;
  const [screen, setScreen] = useState(() => fittedScreen(DEFAULT_DISPLAY));
  const row = screen.toolbar === 'side';
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
  const input = useInput({ gatewayUrl, display, showMarker: settings.touchMarker });
  const { touchFailures } = input;
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
    input.pointerDown.current = false;
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

  const togglePanel = (name) => setPanel((open) => (open === name ? null : name));
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
    ['Entrées', [['Touches via', input.inputPath.current]]],
  ];
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
                  sections={infoSections(serverRows)}
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
                  {infoSections(clientSections)}
                  {fold('clientLogs', 'Journaux du client', <>
                    {logFilter}
                    <LogList entries={logs.page} filter={settings.logFilter} rowStyle={styles.infoRow}
                      labelStyle={styles.infoLabel} />
                  </>)}
                </div>
              )}
              {panel === 'options' && (
                <>
                  <ViewerOptions settings={settings} updateSettings={updateSettings} />
                  <AlertsPanel alerts={alerts} />
                  <PluginList plugins={plugins} settings={settings} updateSettings={updateSettings}
                    openDialog={setPluginDialog} />
                </>
              )}
            </div>
          )}
          {panel === 'options' && pluginDialog && (
            <PluginDialog dialog={pluginDialog} settings={settings} updateSettings={updateSettings}
              openDialog={setPluginDialog} />
          )}
          <div ref={input.touchMarker} style={styles.touchMarker} aria-hidden="true" />
          <div
            style={styles.touchLayer}
            aria-label={tr('Surface tactile Android')}
            onPointerDown={input.startTouch}
            onPointerMove={input.moveTouch}
            onPointerUp={input.endTouch}
            onPointerCancel={input.endTouch}
          />
        </div>
      </section>
      <Toolbar
        placement={screen.toolbar}
        fold={barFold}
        docked={settings.barDocked}
        setDocked={(barDocked) => updateSettings({ barDocked })}
        stream={state}
        problem={problem}
        reconnecting={reconnecting}
        onReconnect={manualReconnect}
        stats={stats}
        panel={panel}
        onInfo={() => { if (panel !== 'info') setInfoTab('client'); togglePanel('info'); }}
        onOptions={() => togglePanel('options')}
        sendKey={input.sendKey}
      />
    </main>
  );
}

export default App;
