// Read-only visual tracking for debug rectangles. Gesture distances are not
// content distances (inertia and list boundaries), so only pixels move zones.
export function scrollViewport(zone, scrolls) {
  if (zone.kind !== 'tap') return null;
  const [l, t, r, b] = zone.rect;
  return scrolls.find(({ rect, direction }) => rect && ['vertical', 'horizontal'].includes(direction)
    && rect[0] <= (l + r) / 2 && (l + r) / 2 <= rect[2]
    && rect[1] <= (t + b) / 2 && (t + b) / 2 <= rect[3]) ?? null;
}

export function makePatch(frame, rect, viewport) {
  const { width, height, pixels } = frame;
  const cx = Math.round((rect[0] + rect[2]) / 2 * width);
  const cy = Math.round((rect[1] + rect[3]) / 2 * height);
  const rx = Math.max(4, Math.round((rect[2] - rect[0]) * width / 2));
  const ry = Math.max(4, Math.round((rect[3] - rect[1]) * height / 2));
  const samples = [];
  // Bound work even for a move whose declared area covers a whole list.
  const stepX = Math.max(2, Math.ceil(rx / 5));
  const stepY = Math.max(2, Math.ceil(ry / 5));
  for (let y = -ry; y <= ry; y += stepY) for (let x = -rx; x <= rx; x += stepX) {
    const px = cx + x; const py = cy + y;
    if (px < Math.ceil(viewport[0] * width) || px >= Math.floor(viewport[2] * width)
      || py < Math.ceil(viewport[1] * height) || py >= Math.floor(viewport[3] * height)) continue;
    samples.push([x, y, pixels[py * width + px]]);
  }
  if (samples.length < 12) return null;
  const mean = samples.reduce((sum, s) => sum + s[2], 0) / samples.length;
  if (samples.reduce((sum, s) => sum + (s[2] - mean) ** 2, 0) / samples.length < 64) return null;
  return { rect, viewport, cx, cy, samples, width, height };
}

export function locatePatch(patch, frame, direction) {
  if (!patch || patch.width !== frame.width || patch.height !== frame.height) return null;
  const { width, height, pixels } = frame;
  const vertical = direction === 'vertical';
  const axis = vertical ? height : width;
  const origin = vertical ? patch.cy : patch.cx;
  const start = Math.ceil(patch.viewport[vertical ? 1 : 0] * axis);
  const end = Math.floor(patch.viewport[vertical ? 3 : 2] * axis);
  const errors = [];
  for (let pos = start; pos < end; pos++) {
    let error = 0; let valid = true;
    for (const [x, y, value] of patch.samples) {
      const px = (vertical ? patch.cx : pos) + x;
      const py = (vertical ? pos : patch.cy) + y;
      if ((vertical ? py : px) < start || (vertical ? py : px) >= end) { valid = false; break; }
      error += Math.abs(pixels[py * width + px] - value);
    }
    if (valid) errors.push({ pos, error: error / patch.samples.length });
  }
  errors.sort((a, b) => a.error - b.error);
  const best = errors[0];
  const other = errors.find((item) => Math.abs(item.pos - best.pos) > 4);
  // Repeated rows, animation, disappeared content and incomplete patches fail
  // closed. Keep the original patch so an item can reappear on a reverse drag.
  if (!best || best.error > 12 || (other && other.error - best.error < 3)) return null;
  const delta = (best.pos - origin) / axis;
  const moved = patch.rect.map((v, i) => v + ((vertical ? i % 2 === 1 : i % 2 === 0) ? delta : 0));
  const clipped = moved.map((v, i) => i < 2 ? Math.max(v, patch.viewport[i]) : Math.min(v, patch.viewport[i]));
  return clipped[0] < clipped[2] && clipped[1] < clipped[3] ? clipped : null;
}

export default function visualTracker(video) {
  let screen = null;
  let patches = new Map();
  let canvas; let context;
  let lastTime = null;
  let rects = new Map();
  return {
    reset() { screen = null; patches.clear(); rects.clear(); lastTime = null; },
    update(name, zones, scrolls) {
      if (name !== screen) { screen = name; patches = new Map(); rects = new Map(); lastTime = null; }
      const moving = zones.map((zone) => ({ zone, viewport: scrollViewport(zone, scrolls) }))
        .filter((item) => item.viewport);
      if (!moving.length) return rects;
      const source = video?.();
      if (!source?.videoWidth || !source?.videoHeight || source.readyState < 2) {
        if (video) for (const { zone } of moving) rects.set(zone.id, null);
        return rects;
      }
      if (source.currentTime === lastTime) return rects;
      lastTime = source.currentTime;
      try {
        canvas ??= document.createElement('canvas');
        const height = Math.round(192 * source.videoHeight / source.videoWidth);
        if (canvas.width !== 192 || canvas.height !== height) { canvas.width = 192; canvas.height = height; }
        context ??= canvas.getContext('2d', { willReadFrequently: true });
        context.drawImage(source, 0, 0, canvas.width, canvas.height);
        const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
        const pixels = new Uint8Array(canvas.width * canvas.height);
        for (let i = 0; i < pixels.length; i++) pixels[i] = (rgba[i * 4] + rgba[i * 4 + 1] + rgba[i * 4 + 2]) / 3;
        const frame = { width: canvas.width, height: canvas.height, pixels };
        for (const { zone, viewport } of moving) {
          // The navigation graph has geometry, not visual identity. This first
          // frame establishes a session baseline, never an automation reading.
          if (!patches.has(zone.id)) patches.set(zone.id, makePatch(frame, zone.rect, viewport.rect));
          rects.set(zone.id, locatePatch(patches.get(zone.id), frame, viewport.direction));
        }
      } catch { for (const { zone } of moving) rects.set(zone.id, null); }
      return rects;
    },
  };
}
