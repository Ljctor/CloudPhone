// Shared visual semantics for live debug and the passive navigation review.
// These styles describe feedback; they never change gesture permissions.
export const ZONE_COLOURS = {
  tap: '#ffe100', navigation: '#ffe100', action: '#ff9a23', forbidden: '#ff5353',
  progression_value: '#409cff', resource_value: '#2dd4bf',
  detection: '#4ade80', scannable: '#4ade80', screen_identifier: '#4ade80',
  vertical: '#bb50ff', horizontal: '#bb50ff', draggable: '#ff65bd',
};
export const ZONE_STYLE_VERSION = 'zones-v4-rounded-navigation-hatched-forbidden';
export function zoneStyle(zone) {
  const removal = zone.proposal === 'remove' || zone.removedProposal === true;
  const user = zone.user === true || zone.source === 'user_feedback';
  const role = zone.semantic_kind ?? (zone.kind === 'forbidden' ? 'navigation' : zone.kind === 'tap' ? 'navigation' : zone.kind ?? 'navigation');
  const forbidden = zone.forbidden === true || zone.kind === 'forbidden';
  const conditionalButton = Boolean(zone.conditional) && ['navigation', 'action'].includes(role);
  return {
    hatch: !removal && forbidden,
    radius: role === 'navigation' ? 6 : 0,
    dash: removal ? '10 7' : user ? '1 5' : 'none',
    opacity: removal ? .28 : 1,
    linecap: user && !removal ? 'round' : 'butt',
    double: conditionalButton && !user && !removal,
    width: conditionalButton && !user && !removal ? 1 : 2,
  };
}

// SVG remains present in both the live overlay and frozen oral-feedback evidence.
let hatchSerial = 0;
export function addZoneHatching(box, colour, radius = 0) {
  const ns = 'http://www.w3.org/2000/svg';
  const element = (name, attributes) => {
    const node = document.createElementNS(ns, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  };
  const id = `forbidden-action-hatch-${++hatchSerial}`;
  const svg = element('svg', { 'data-zone-hatch': 'action' });
  svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;border-radius:inherit;overflow:hidden';
  const defs = element('defs', {});
  const pattern = element('pattern', { id, patternUnits: 'userSpaceOnUse', width: 8, height: 8 });
  pattern.append(element('path', { d: 'M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6', stroke: colour, 'stroke-width': 2, opacity: .45 }));
  defs.append(pattern); svg.append(defs);
  svg.append(element('rect', { width: '100%', height: '100%', rx: radius, ry: radius, fill: `url(#${id})` }));
  box.append(svg);
}

// Only two direction chevrons: a declared slider rectangle is not a raw drag path.
export function sliderChevronPath(kind, rect) {
  const [l, t, r, b] = rect, x = (l+r)/2, y = (t+b)/2;
  const arm = Math.min(7, (r-l)/4, (b-t)/4);
  return kind === 'vertical'
    ? `M${x-arm} ${t+arm*2} L${x} ${t+arm} L${x+arm} ${t+arm*2} M${x-arm} ${b-arm*2} L${x} ${b-arm} L${x+arm} ${b-arm*2}`
    : `M${l+arm*2} ${y-arm} L${l+arm} ${y} L${l+arm*2} ${y+arm} M${r-arm*2} ${y-arm} L${r-arm} ${y} L${r-arm*2} ${y+arm}`;
}
export function addSliderChevrons(box, colour, kind, rect) {
  const ns = 'http://www.w3.org/2000/svg', width = (rect[2]-rect[0])*480, height = (rect[3]-rect[1])*1040;
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('preserveAspectRatio','none');
  svg.setAttribute('data-slider-chevrons', kind);
  svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
  const path = document.createElementNS(ns,'path');
  for (const [key,value] of Object.entries({d:sliderChevronPath(kind,[0,0,width,height]), fill:'none',stroke:colour,'stroke-width':2,'stroke-dasharray':'none'})) path.setAttribute(key,value);
  svg.append(path);box.append(svg);
}
