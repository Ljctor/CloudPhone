// The information panel's client tab, as [title, [[label, value], ...]]
// sections (French source texts). No React, no DOM: the page passes what
// the browser reports.
import { formatValue } from './serverInfo';

// What this browser's device offers and what Android sends, as label/value
// rows: CSS pixels (layout) and physical pixels (CSS × devicePixelRatio).
// ratio: devicePixelRatio; device: the device's screen, viewport: the
// window and shown: the Android image, each { width, height } in CSS pixels.
export function deviceRows({ ratio, device, viewport, shown }) {
  const physical = (width, height) => `${Math.round(width * ratio)}×${Math.round(height * ratio)}`;
  return [
    ['Écran de l’appareil', `${physical(device.width, device.height)} px`],
    ['Fenêtre', `${viewport.width}×${viewport.height} CSS · ${physical(viewport.width, viewport.height)} px`],
    ['Densité', `×${ratio.toFixed(2)}`],
    ['Image affichée', `${shown.width}×${shown.height} CSS · ${physical(shown.width, shown.height)} px`],
  ];
}

// stats: the stream's (streamStats.ts); stream: its connection state;
// inputPath: how touches reach Android; device: deviceRows().
export function clientSections({ stats, stream, inputPath, device }) {
  return [
    ['Réseau', [
      ['Ping', stats.ping === null ? '–' : `${Math.round(stats.ping)} ms (${stats.pingSource})`],
      ['Connexion', stats.connection ?? stream],
      ['Chemin', stats.path ?? '–'],
      ['Paquets perdus', formatValue(stats.packetsLost)],
      ['Gigue', stats.jitter === null ? '–' : `${Math.round(stats.jitter)} ms`],
    ]],
    ['Affichage', [
      ['Images affichées', `${formatValue(stats.phone)} /s`],
      ['Images reçues / décodées', `${formatValue(stats.framesReceived)} / ${formatValue(stats.framesDecoded)}`],
      ['Gels du décodeur', formatValue(stats.freezeCount)],
      ['Images perdues', formatValue(stats.framesDropped)],
      ['Tampon vidéo', stats.bufferDelay === null ? '–' : `${Math.round(stats.bufferDelay)} ms`],
      ...device,
    ]],
    ['Entrées', [['Touches via', inputPath]]],
  ];
}
