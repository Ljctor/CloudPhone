import { tr } from './i18n';
import { usePlugins } from './plugins';
import { useRef } from 'react';
import { Emulator, logger } from '../../src';
import { PAGE_CSS, styles } from './styles';
import { postFetch, postHeaders } from './api';
import { Toasts, useLog, useServerLog, useToasts } from './logs';
import { LogSection } from './logSection';
import { AlertsPanel, useAlerts } from './notify';
import { serverSections } from './serverInfo';
import { ServerPanel } from './serverPanel';
import { EmulatorSettings, useDisplayState, useEmulatorSettings } from './androidSettings';
import { changeInProgress } from './emulatorSettings';
import { useServerState } from './serverState';
import { bannerShown, diagnose } from './diagnose';
import { Banner, StatusCover, useDismissed } from './banner';
import { useStreamStats } from './useStreamStats';
import { useInput } from './useInput';
import { useStream } from './useStream';
import { mainDirection, toastsTop } from './layout';
import { useAndroidDisplay, useFittedScreen, useReloadOnResize, viewportSize } from './useLayout';
import { usePanels } from './usePanels';
import { Toolbar, useBarFold } from './toolbar';
import { infoSections } from './infoRows';
import { clientSections, deviceRows } from './clientInfo';
import { PluginDialog, PluginList, usePluginDialog } from './pluginOptions';
import { ViewerOptions, loadSettings, useViewerSettings } from './viewerSettings';

logger.setLevel('warn');

function App() {
  const emulatorRef = useRef(null);
  const deviceRef = useRef(null);
  const { panel, setPanel, infoTab, setInfoTab, serverTab, togglePanel, openInfo } = usePanels();
  // A plugin's dialog open over the options panel: { plugin, option }.
  const [pluginDialog, setPluginDialog] = usePluginDialog(panel);
  // Before any tr() of this render: sets the page's language.
  const [settings, updateSettings] = useViewerSettings();
  const barFold = useBarFold(loadSettings);
  const { barFolded } = barFold;
  // The gateway serves this page: same origin, no CORS.
  const gateway = window.location.host;
  const gatewayUrl = `${window.location.protocol}//${gateway}`;
  const display = useAndroidDisplay(gatewayUrl);
  const screen = useFittedScreen(display, barFolded, settings.barDocked);
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
  const displayState = useDisplayState(gatewayUrl, changeInProgress(emulatorSettings));
  const input = useInput({ gatewayUrl, display, showMarker: settings.touchMarker });
  // Seconds the stream has been trying to connect, and consecutive failed
  // touch requests: both feed the message shown to the user.
  const { touchFailures } = input;
  const stream = useStream({ server, input });
  const { state, reconnecting, connectingFor } = stream;
  useReloadOnResize(displayState);
  const problem = diagnose({ server, stream: state, connectingFor, touchFailures });
  const [dismissed, setDismissed] = useDismissed(problem);
  const serverRows = serverSections({
    server, configured: displayState?.configured, display, stats,
  });
  const clientRows = clientSections({
    stats, stream: state, inputPath: input.inputPath.current,
    device: deviceRows({
      ratio: window.devicePixelRatio || 1, device: window.screen, viewport: viewportSize(), shown: screen,
    }),
  });

  return (
    <main style={{ ...styles.app, flexDirection: mainDirection(screen.toolbar) }}>
      <style>{PAGE_CSS}</style>
      <section style={styles.screen} aria-label={tr('Écran Android')}
        onContextMenu={(event) => event.preventDefault()}>
        <div ref={deviceRef} style={{ ...styles.device, width: screen.width, height: screen.height }}>
          {stream.mounted && (
            <Emulator
              key={stream.generation}
              ref={emulatorRef}
              uri={gateway}
              width={screen.width}
              height={screen.height}
              muted
              onStateChange={stream.handleState}
              onError={(error) => console.error('Android stream:', error)}
            />
          )}
          <StatusCover problem={problem} stream={state} reconnecting={reconnecting} />
          <Banner problem={problem} dismissed={dismissed} dismiss={setDismissed} />
          <div ref={pluginLayer} style={styles.pluginLayer} aria-hidden="true" />
          <Toasts toasts={toasts} dismiss={dismissToast}
            top={toastsTop(bannerShown(problem, dismissed))} />
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
                  logs={(
                    <LogSection id="serverLogs" title="Journaux du serveur" entries={logs.server}
                      settings={settings} updateSettings={updateSettings} />
                  )}
                />
              )}
              {panel === 'info' && infoTab === 'client' && (
                <div role="tabpanel">
                  {infoSections(clientRows)}
                  <LogSection id="clientLogs" title="Journaux du client" entries={logs.page}
                    settings={settings} updateSettings={updateSettings} />
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
        onReconnect={stream.manualReconnect}
        stats={stats}
        panel={panel}
        onInfo={openInfo}
        onOptions={() => togglePanel('options')}
        sendKey={input.sendKey}
      />
    </main>
  );
}

export default App;
