// Android screen sizes offered by the settings form: the size a choice
// gives and the choice closest to a size. No React, no DOM.

// Android screen shapes (height / width, portrait) and resolutions offered
// on the page. Density follows the width (160 dpi per 360 px), so Android's
// layout looks the same at every resolution: "Haute" only adds pixels, for
// sharp screenshots, at a higher CPU cost on the server.
export const DEVICE_SHAPES = [
  { id: 's23', label: '19,5:9 (Galaxy S23)', ratio: 2340 / 1080 },
  { id: 'pixel', label: '20:9 (Pixel 8)', ratio: 2400 / 1080 },
  { id: 'classic', label: '16:9', ratio: 16 / 9 },
  { id: 'tablet', label: 'Tablette 16:10', ratio: 1.6 },
  { id: 'fold', label: 'Pliable ouvert', ratio: 2176 / 1812 },
  { id: 'window', label: 'Cette fenêtre', ratio: null },
];
// 480p is the default: sharp enough on a phone, still fluid on a server
// without a GPU.
export const DEFAULT_RESOLUTION = '480';
export const RESOLUTIONS = [
  { id: '360', label: '360p', width: 360 },
  { id: '480', label: '480p (défaut)', width: 480 },
  { id: '720', label: '720p', width: 720 },
  { id: '1080', label: '1080p', width: 1080 },
];

function even(value) {
  return Math.max(2, Math.round(value / 2) * 2);
}

// windowRatio: the browser window's height / width, for "Cette fenêtre".
function shapeRatio(shape, windowRatio) {
  if (shape.ratio) return shape.ratio;
  return Math.min(2.4, Math.max(1, windowRatio));
}

export function targetSize(shapeId, resolutionId, windowRatio) {
  const shape = DEVICE_SHAPES.find((item) => item.id === shapeId) ?? DEVICE_SHAPES[0];
  const resolution = RESOLUTIONS.find((item) => item.id === resolutionId)
    ?? RESOLUTIONS.find((item) => item.id === DEFAULT_RESOLUTION);
  const width = resolution.width;
  return {
    width,
    height: Math.min(3200, even(width * shapeRatio(shape, windowRatio))),
    density: Math.round(width * 160 / 360),
  };
}

// The presets closest to a configured size, for the selectors' start values.
export function matchPresets(size) {
  if (!size?.width) return { shape: 's23', resolution: DEFAULT_RESOLUTION };
  const ratio = size.height / size.width;
  const shape = DEVICE_SHAPES.find((item) => item.ratio && Math.abs(item.ratio - ratio) / ratio < 0.015);
  const resolution = RESOLUTIONS.find((item) => item.width === size.width);
  return { shape: shape?.id ?? 'window', resolution: resolution?.id ?? DEFAULT_RESOLUTION };
}
