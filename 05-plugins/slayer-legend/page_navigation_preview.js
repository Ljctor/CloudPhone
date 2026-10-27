// Inspect archived images only. This viewer never sends input or changes
// navigation/scan declarations.
export function archivedScreen(record, side) {
  const scan = record?.[`${side}_scan`];
  if (!scan || scan.screen === 'unknown') return null;
  const overlays = (scan.overlays ?? []).filter((item) => !['panel', 'better_weapon_toast'].includes(item));
  if (!overlays.length && scan.overlays?.includes('panel')) return null;
  return overlays.at(-1) ?? scan.screen ?? null;
}

export default function capturePreview({ layer, record, side, zones = [], drawZone, tr = (value) => value }) {
  const stop = (event) => { event.preventDefault(); event.stopPropagation(); };
  const modal = document.createElement('div');
  modal.setAttribute('data-capture-preview', side);
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-label', tr(side === 'before' ? 'Capture avant annotée' : 'Capture après annotée'));
  modal.style.cssText = 'position:absolute;inset:0;z-index:80;pointer-events:auto;display:flex;flex-direction:column;gap:6px;padding:8px;box-sizing:border-box;background:#101010f5;color:#fff;font:12px sans-serif;overflow:auto';
  // All preview gestures belong to this read-only viewer, including touch.
  modal.onpointerdown = (event) => event.stopPropagation();
  modal.onpointermove = (event) => event.stopPropagation();
  modal.onpointerup = (event) => event.stopPropagation();
  modal.onpointercancel = (event) => event.stopPropagation();
  const previousFocus = document.activeElement;
  const onKey = (event) => { if (event.key === 'Escape') { stop(event); close(); } };
  const close = () => { modal.remove(); window.removeEventListener?.('resize', size); window.removeEventListener?.('keydown', onKey); previousFocus?.focus?.(); };
  const bar = document.createElement('div');
  bar.style.cssText = 'display:flex;align-items:center;gap:10px;flex-wrap:wrap;flex-shrink:0';
  const title = document.createElement('strong');
  const identity = archivedScreen(record, side);
  title.textContent = `${tr(side === 'before' ? 'Capture avant' : 'Capture après')} · ${identity ?? tr('Écran historique non identifié')}`;
  bar.append(title);
  const raw = document.createElement('a');
  raw.href = record[`${side}_url`]; raw.target = '_blank'; raw.rel = 'noopener';
  raw.textContent = tr('Image originale'); raw.style.cssText = 'color:#ffe100';
  raw.setAttribute('data-capture-raw', side);
  bar.append(raw);
  const dismiss = document.createElement('button');
  dismiss.type = 'button'; dismiss.textContent = tr('Fermer');
  dismiss.style.cssText = 'margin-left:auto;padding:5px 8px;border:1px solid #aaa;border-radius:3px;background:#292929;color:#fff;font:inherit';
  dismiss.onclick = (event) => { stop(event); close(); };
  bar.append(dismiss); modal.append(bar);
  const note = document.createElement('div');
  note.textContent = tr(identity ? 'Zones connues de l’écran archivé · rouge : geste enregistré' : 'Zones historiques indisponibles · rouge : geste enregistré');
  modal.append(note);
  const stage = document.createElement('div');
  stage.style.cssText = 'display:flex;justify-content:center;align-items:flex-start;min-height:0;flex:1';
  const frame = document.createElement('div');
  frame.style.cssText = 'position:relative;display:inline-block;max-width:100%;line-height:0';
  const image = document.createElement('img');
  image.src = record[`${side}_url`];
  image.alt = tr(side === 'before' ? 'Capture avant' : 'Capture après');
  image.style.cssText = 'display:block;max-width:100%;width:auto;height:auto';
  let orientArrow = () => {};
  const size = () => { image.style.maxHeight = `${Math.max(40, layer.getBoundingClientRect().height - 100)}px`; orientArrow(); };
  size();
  window.addEventListener?.('resize', size);
  // The image and overlays share one measured wrapper, never the live video.
  frame.append(image);
  for (const zone of zones) drawZone?.(zone, frame);
  const tap = record.tap;
  const area = record.rect ?? (record.kind === 'scannable' && tap?.end
    ? [Math.min(tap.x, tap.end.x), Math.min(tap.y, tap.end.y), Math.max(tap.x, tap.end.x), Math.max(tap.y, tap.end.y)] : null);
  if (area?.length === 4 && area.every(Number.isFinite)) {
    const box = document.createElement('div');
    box.setAttribute('data-recorded-rect', '');
    box.style.cssText = `position:absolute;left:${area[0] * 100}%;top:${area[1] * 100}%;width:${(area[2] - area[0]) * 100}%;height:${(area[3] - area[1]) * 100}%;border:2px solid #52e99a;background:#52e99a33;box-sizing:border-box;pointer-events:none;z-index:2`;
    frame.append(box);
  }
  if (tap && Number.isFinite(tap.x) && Number.isFinite(tap.y)) {
    const marker = document.createElement('div');
    marker.setAttribute('data-recorded-tap', '');
    marker.style.cssText = `position:absolute;left:${tap.x * 100}%;top:${tap.y * 100}%;width:28px;height:28px;transform:translate(-50%,-50%);border:3px solid #ff4040;border-radius:50%;box-sizing:border-box;box-shadow:0 0 0 1px #000,0 0 7px #000;pointer-events:none;z-index:3`;
    for (const vertical of [false, true]) {
      const cross = document.createElement('div');
      cross.style.cssText = `position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);background:#ff4040;box-shadow:0 0 1px #000;width:${vertical ? 2 : 40}px;height:${vertical ? 40 : 2}px`;
      marker.append(cross);
    }
    frame.append(marker);
    if (record.kind !== 'scannable' && tap.end && Number.isFinite(tap.end.x) && Number.isFinite(tap.end.y)) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 100 100'); svg.setAttribute('preserveAspectRatio', 'none');
      svg.setAttribute('data-recorded-swipe', '');
      svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible;z-index:2';
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      for (const [key, value] of Object.entries({ x1: tap.x * 100, y1: tap.y * 100, x2: tap.end.x * 100, y2: tap.end.y * 100, stroke: '#ff4040', 'stroke-width': 3, 'vector-effect': 'non-scaling-stroke' })) line.setAttribute(key, value);
      svg.append(line); frame.append(svg);
      const arrow = document.createElement('div');
      arrow.setAttribute('data-recorded-swipe-end', '');
      arrow.style.cssText = `position:absolute;left:${tap.end.x * 100}%;top:${tap.end.y * 100}%;width:12px;height:12px;border-right:3px solid #ff4040;border-bottom:3px solid #ff4040;pointer-events:none;z-index:3`;
      const orient = () => {
        const bounds = image.getBoundingClientRect();
        const angle = Math.atan2((tap.end.y - tap.y) * bounds.height, (tap.end.x - tap.x) * bounds.width) * 180 / Math.PI;
        arrow.style.transform = `translate(-50%,-50%) rotate(${angle - 45}deg)`;
      };
      orientArrow = orient; image.onload = orient; orient(); frame.append(arrow);
    }
  }
  stage.append(frame); modal.append(stage); layer.append(modal);
  window.addEventListener?.('keydown', onKey);
  dismiss.focus?.();
  return close;
}
