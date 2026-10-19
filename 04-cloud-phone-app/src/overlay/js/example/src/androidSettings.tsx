// Android's screen size and settings: the polls of GET /api/v1/display and
// GET /api/v1/emulator-settings, and the form that changes them (Server
// tab). The choices are in emulatorSettings.ts and screenSize.ts.
import { useEffect, useState } from 'react';
import { tr } from './i18n';
import { coreOptions, memoryOptions, rendererOptions, sameSettings } from './emulatorSettings';
import { DEVICE_SHAPES, RESOLUTIONS, matchPresets, targetSize } from './screenSize';
import { postFetch, postHeaders } from './api';
import { styles } from './styles';

// Polls the gateway for the screen size and the state of a size change:
// often while a change is in progress (or `changing` says one is), rarely
// otherwise.
export function useDisplayState(gatewayUrl, changing) {
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

export function useEmulatorSettings(gatewayUrl, enabled) {
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

// Renderer, cores, memory and screen Android runs with. Applying restarts
// Android once, whatever changed.
export function EmulatorSettings({ gatewayUrl, settings, refresh, rowStyle, labelStyle, buttonStyle }) {
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
  const windowRatio = window.innerHeight / Math.max(1, window.innerWidth);
  const target = targetSize(choice.shape, choice.resolution, windowRatio);
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
      const response = await postFetch(`${gatewayUrl}/api/v1/emulator-settings`, {
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
