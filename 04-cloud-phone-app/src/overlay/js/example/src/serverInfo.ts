// The information panel's rows, as plain data: [section title, [[label,
// value], ...]] with the values already formatted. No React, no DOM.
import { tr } from './i18n';

export function formatValue(value) {
  return value === null || value === undefined ? '–' : String(Math.round(value));
}

export function shortSide(size) {
  return size?.width ? `${Math.min(size.width, size.height)}p` : '–';
}

export function describeUnit(unit) {
  if (!unit) return '–';
  const restarts = unit.restarts
    ? `, ${tr(unit.restarts > 1 ? '{n} redémarrages' : '{n} redémarrage', { n: unit.restarts })}` : '';
  return `${unit.active} (${unit.sub})${restarts}`;
}

const mib = (value) => (value === null || value === undefined ? '–'
  : value >= 1024 ? `${(value / 1024).toFixed(1)} ${tr('Go')}` : `${value} ${tr('Mo')}`);
const memoryRow = (memory) => (memory?.total
  ? tr('{used} utilisés / {total}', { used: mib(memory.total - memory.available), total: mib(memory.total) }) : '–');
const liveMemory = (memory) => (memory?.total
  ? tr('{percent} % · {used} / {total}', {
    percent: Math.round(100 * (memory.total - memory.available) / memory.total),
    used: mib(memory.total - memory.available), total: mib(memory.total),
  }) : '–');
const swapRow = (memory) => (memory?.swapTotal ? `${mib(memory.swapUsed)} / ${mib(memory.swapTotal)}` : '–');

// The Server tab: the state poll (server), the configured screen size
// (configured, from GET /api/v1/display) or the one in use (display), and
// the stream's statistics (stats).
export function serverSections({ server, configured, display, stats }) {
  const load = server.value?.load;
  const metrics = server.value?.metrics;
  const host = metrics?.host;
  const emulator = metrics?.emulator;
  const android = metrics?.android;
  return [
    ['État', [
      ['Serveur', server.failures >= 2 ? tr('injoignable') : server.value ? tr('joignable') : '…'],
      ['Service Android', describeUnit(server.value?.emulator)],
      ['Android démarré', server.value?.android?.booted === true ? tr('oui')
        : server.value?.android?.booted === false ? tr('en cours') : tr('sans réponse')],
      ['Appareils connectés', formatValue(server.value?.viewers)],
      ['Charge du serveur', load ? (load.cores ? tr('{load} tâches pour {cpus} threads ({cores} cœurs)', { load: load.one.toFixed(1), cpus: load.cpus, cores: load.cores })
        : tr('{load} tâches pour {cpus} threads', { load: load.one.toFixed(1), cpus: load.cpus })) : '–'],
      ['CPU (en direct)', host?.cpu === null || host?.cpu === undefined ? '–'
        : tr('{cpu} % de {cpus} threads', { cpu: host.cpu, cpus: host.cpus })],
      ['Mémoire (en direct)', liveMemory(host?.memory)],
    ]],
    ['Machine', [
      ['Fréquence', host?.mhz ? `${host.mhz} MHz${host.governor ? ` (${host.governor})` : ''}` : '–'],
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
}
