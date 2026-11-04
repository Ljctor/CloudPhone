import { COLOURS, reviewGesture, gestureLabel, screenLabel, inside, servicePath } from './model.js';
import oralFeedback, { freezeOralContext, oralTransport } from './page_oral_feedback.js';
import { zoneStyle } from './page_zone_style.js';
const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const serviceUrl = (path) => servicePath(path, import.meta.url);
const state = { nodes: new Map(), outgoing: new Map(), current: null, history: [], position: -1,
  overlay: true, landmarks: true, gesture: null, loading: false, revision: null, visit: 0 };
const svg = (tag, attributes = {}, text) => {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text != null) node.textContent = text;
  return node;
};
const current = () => state.nodes.get(state.current);
const outgoing = () => state.outgoing.get(state.current) ?? [];
const safeImage = (url) => typeof url === 'string' && url.startsWith('/api/image/') && !url.startsWith('//') ? serviceUrl(url) : null;
let noticeTimer;
function notice(text, error = false) {
  clearTimeout(noticeTimer); const box = $('notice');
  box.hidden = !text; box.textContent = text; box.classList.toggle('error', error);
  box.style.animation = 'none'; void box.offsetWidth; box.style.animation = '';
  if (text) noticeTimer = setTimeout(() => { box.hidden = true; }, 1500);
}
function pulse(position, kind, text = '') {
  const layer = $('effects'), colour = kind === 'forbidden' ? COLOURS.forbidden : kind === 'action' ? COLOURS.action : '#a8c5e8';
  const add = (className) => { const item = document.createElement('i'); item.className = className;
    item.style.cssText = `left:${position.x * 100}%;top:${position.y * 100}%;--feedback:${colour}`;
    layer.append(item); setTimeout(() => item.remove(), 700); return item; };
  add('pulse');
  for (let index = 0; index < 6; index++) { const dot = add('spark'), angle = index * Math.PI / 3;
    dot.style.setProperty('--dx', `${Math.cos(angle) * 34}px`); dot.style.setProperty('--dy', `${Math.sin(angle) * 34}px`); }
  if (text) notice(text, kind === 'forbidden');
}
async function visit(id, { remember = true } = {}) {
  const node = state.nodes.get(id), url = safeImage(node?.image);
  if (!url) { notice('Capture de destination absente', true); return false; }
  const ticket = ++state.visit;
  const image = new Image();
  try { image.src = url; await image.decode(); }
  catch { if (ticket === state.visit) notice('Capture de destination indisponible', true); return false; }
  if (ticket !== state.visit) return false;
  if (remember && id !== state.current) { state.history = state.history.slice(0, state.position + 1); state.history.push(id); state.position = state.history.length - 1; }
  state.current = id; $('effects').replaceChildren(); notice('');
  $('screen-image').src = url; $('screen-image').alt = `Capture enregistrée · ${screenLabel(node)}`;
  $('phone').style.aspectRatio = `${image.naturalWidth}/${image.naturalHeight}`;
  history.replaceState(null, '', `#node=${encodeURIComponent(id)}`);
  $('back').disabled = state.position <= 0;
  renderOverlay(); return true;
}
async function load() {
  if (state.loading) return; state.loading = true;
  try {
    const response = await fetch(serviceUrl('/api/graph'), { cache: 'no-store' });
    if (!response.ok) throw Error('Captures indisponibles');
    const data = await response.json();
    state.nodes = new Map((data.nodes ?? []).map((node) => [node.id, node])); state.outgoing.clear();
    for (const edge of data.edges ?? []) { if (!state.nodes.has(edge.from) || !state.nodes.has(edge.to)) continue;
      if (!state.outgoing.has(edge.from)) state.outgoing.set(edge.from, []); state.outgoing.get(edge.from).push(edge); }
    const wanted = new URLSearchParams(location.hash.slice(1)).get('node');
    const initial = current() ?? state.nodes.get(wanted) ?? state.nodes.get('screen:battle')
      ?? data.nodes.find((node) => node.screen === 'battle' && safeImage(node.image))
      ?? data.nodes.find((node) => safeImage(node.image));
    if (initial) await visit(initial.id, { remember: !state.current });
    else notice('Aucune capture enregistrée', true);
  } catch (error) { notice(error.message, true); }
  finally { state.loading = false; }
}
function renderOverlay() {
  const layer = $('overlay'); layer.replaceChildren(); layer.toggleAttribute('hidden', !state.overlay && !state.landmarks);
  if ((!state.overlay && !state.landmarks) || !current()) return;
  const defs = svg('defs');
  const hatch = svg('pattern', { id: 'forbidden-action-hatch', patternUnits: 'userSpaceOnUse', width: 8, height: 8 });
  hatch.append(svg('path', { d: 'M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6', stroke: COLOURS.forbidden, 'stroke-width': 2, opacity: .45 }));
  defs.append(hatch); layer.append(defs);
  const regions = [...(current().regions ?? [])];
  // Recorded points are useful even when no annotation rectangle was made.
  for (const edge of state.overlay ? outgoing() : []) {
    if (!edge.start) continue;
    const proposal = regions.find((region) => region.id === `edge:${edge.id}`);
    if (regions.some((region) => ['navigation', 'tap'].includes(region.kind) && inside(edge.start, region.rect))) continue;
    const isSwipe = Boolean(edge.end) && edge.kind === 'swipe';
    const kind = ['action', 'forbidden'].includes(edge.annotationKind) ? edge.annotationKind : edge.annotationKind === 'draggable' ? 'draggable' : isSwipe
      ? Math.abs(edge.end.y - edge.start.y) >= Math.abs(edge.end.x - edge.start.x) ? 'vertical' : 'horizontal' : 'navigation';
    const colour = COLOURS[kind];
    if (isSwipe) {
      const x = edge.start.x * 480, y = edge.start.y * 1040, x2 = edge.end.x * 480, y2 = edge.end.y * 1040;
      layer.append(svg('line', { x1: x, y1: y, x2, y2, stroke: colour, 'stroke-width': 3, 'stroke-dasharray': 'none', opacity: .8 }));
      const angle = Math.atan2(y2 - y, x2 - x), arm = 10;
      layer.append(svg('path', { d: `M ${x2 - Math.cos(angle - .6) * arm} ${y2 - Math.sin(angle - .6) * arm} L ${x2} ${y2} L ${x2 - Math.cos(angle + .6) * arm} ${y2 - Math.sin(angle + .6) * arm}`, fill: 'none', stroke: colour, 'stroke-width': 3 }));
    } else {
      const style = zoneStyle(proposal ?? { kind, user: edge.source === 'manual', conditional: edge.conditional });
      // Unmeasured recordings retain a point marker, never invented button bounds.
      const rect = edge.rect ?? [edge.start.x - 10 / 480, edge.start.y - 10 / 1040, edge.start.x + 10 / 480, edge.start.y + 10 / 1040];
      const [l, t, r, b] = rect, x = l * 480, y = t * 1040, width = (r-l)*480, height = (b-t)*1040;
      const marker = svg('rect', { x, y, width, height, rx: 0, stroke: colour, fill: `${colour}18`, 'stroke-width': style.width, opacity: style.opacity, 'stroke-dasharray': style.dash, 'stroke-linecap': style.linecap });
      marker.append(svg('title', {}, edge.rect ? edge.label : 'Point enregistré · dimensions du bouton non mesurées'));
      layer.append(marker);
      if (style.double && width > 6 && height > 6) layer.append(svg('rect', { x:x+3, y:y+3, width:width-6, height:height-6, rx:0, stroke:colour, fill:'none', 'stroke-width':1 }));
    }
  }
  regions.sort((a, b) => Number(Boolean(a.forbidden || a.kind === 'forbidden')) - Number(Boolean(b.forbidden || b.kind === 'forbidden')));
  for (const region of regions) {
    const landmark = ['detection', 'scannable', 'screen_identifier'].includes(region.kind);
    if (landmark ? !state.landmarks : !state.overlay) continue;
    if (!Array.isArray(region.rect) || region.rect.length !== 4 || region.rect.some((v) => !Number.isFinite(v))) continue;
    const [l, t, r, b] = region.rect, forbidden = region.forbidden || region.kind === 'forbidden';
    const style = zoneStyle(region);
    const kind = forbidden ? 'forbidden' : region.kind, colour = COLOURS[kind] ?? '#94a3b8';
    const box = svg('rect', { x: l * 480, y: t * 1040, width: (r - l) * 480, height: (b - t) * 1040,
      'data-zone-kind': region.kind === 'action' ? 'action' : kind, 'data-zone-forbidden': String(Boolean(forbidden)), rx: 0, fill: style.hatch ? 'url(#forbidden-action-hatch)' : style.opacity < 1 ? 'none' : `${colour}12`, stroke: colour, 'stroke-width': style.width, opacity: style.opacity,
      'stroke-dasharray': style.dash, 'stroke-linecap': style.linecap });
    if (style.double && (r-l)*480 > 8 && (b-t)*1040 > 8) layer.append(svg('rect', { x:l*480+3, y:t*1040+3, width:(r-l)*480-6, height:(b-t)*1040-6, fill:'none', stroke:colour, 'stroke-width':1 }));
    box.append(svg('title', {}, `${region.label ?? region.id ?? kind}${region.source ? ` · ${region.source}` : ''}`)); layer.append(box);
    if (!forbidden && ['vertical', 'horizontal'].includes(kind)) {
      const x = (l + r) * 240, y = (t + b) * 520;
      const arm = Math.min(7, (r - l) * 120, (b - t) * 260);
      const d = kind === 'vertical'
        ? `M${x-arm} ${t*1040+arm*2} L${x} ${t*1040+arm} L${x+arm} ${t*1040+arm*2} M${x-arm} ${b*1040-arm*2} L${x} ${b*1040-arm} L${x+arm} ${b*1040-arm*2}`
        : `M${l*480+arm*2} ${y-arm} L${l*480+arm} ${y} L${l*480+arm*2} ${y+arm} M${r*480-arm*2} ${y-arm} L${r*480-arm} ${y} L${r*480-arm*2} ${y+arm}`;
      layer.append(svg('path', { d, fill: 'none', stroke: colour, 'stroke-width': 2, opacity: style.opacity }));
    }
  }
}

const secureReviewUrl = fetch(serviceUrl('/api/recording-config'), { cache: 'no-store' })
  .then((response) => response.ok ? response.json() : null)
  .then((config) => config?.secure_review_url ?? null).catch(() => null);
const oral = oralFeedback({ secureReviewUrl, transport: oralTransport(serviceUrl('/api/oral-feedback')), capture: () => {
  const node = current(); if (!node) throw Error('Aucune capture');
  return freezeOralContext({ image: $('screen-image'), layer: $('phone'), svgElement: $('overlay'),
    source: 'review', nodeId: node.id, screen: node.screen, displayName: screenLabel(node),
    regions: node.regions ?? [], enabled: state.overlay || state.landmarks, state: { review: node.review } });
} });
$('feedback-panel').append(oral.element);
async function proposeZone(operation, zone, nodeId) {
  const node = state.nodes.get(nodeId); if (!node) return;
  try {
    const response = await fetch(serviceUrl('/api/zone-feedback'), { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodeId, ...(operation === 'remove' ? { zoneId: zone.id } : {}), screen: node.screen, operation, kind: zone.kind, forbidden: Boolean(zone.forbidden || zone.kind === 'forbidden'), rect: zone.rect, label: zone.label ?? zone.kind }) });
    if (!response.ok) throw Error('Proposition non enregistrée');
    const saved = await response.json();
    if (operation === 'remove') Object.assign(zone, { proposal: 'remove', user: true });
    else { node.regions ??= []; node.regions.push({ ...zone, id: saved.zoneId || saved.id, user: true, source: 'user_feedback', proposal: 'add' }); }
    renderOverlay(); notice(operation === 'remove' ? 'Suppression proposée · à examiner par le développeur' : 'Annotation enregistrée · à examiner par le développeur');
  } catch (error) { notice(error.message, true); }
}
async function follow(gesture) {
  const origin = state.current, result = reviewGesture(outgoing(), gesture, current()?.regions);
  if (result.kind === 'forbidden' || result.kind === 'action') { pulse(gesture.start, result.kind); return; }
  if (result.matches.length !== 1) { pulse(gesture.start, 'unknown', result.matches.length ? 'Destination ambiguë' : 'Aucune transition enregistrée'); return; }
  const edge = result.matches[0];
  if (!safeImage(state.nodes.get(edge.to)?.image)) { pulse(gesture.start, 'unknown', 'Capture de destination absente'); return; }
  const dragging = gesture.end && Math.hypot(gesture.end.x-gesture.start.x,gesture.end.y-gesture.start.y)>=.035;
  // Historical preview Rotate/invalid Confirm taps were labelled navigation.
  // Same-preview taps are visual actions here; this does not repair the ledger
  // or change any live permission. Cancel to another screen and drags remain.
  if (edge.to === origin || !dragging && current()?.screen === 'soul_weapon_engraving_preview'
      && state.nodes.get(edge.to)?.screen === 'soul_weapon_engraving_preview') { pulse(gesture.start, 'action'); return; }
  await visit(edge.to);
}
const phone = $('phone');
function point(event) { const r = phone.getBoundingClientRect(); return {
  x: Math.max(0, Math.min(1, (event.clientX-r.left)/r.width)), y: Math.max(0, Math.min(1, (event.clientY-r.top)/r.height)) }; }
phone.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || !current()) return;
  const gesture = { start: point(event), at: performance.now(), pointerId: event.pointerId, node: state.current, annotation: $('annotation-kind').value }; state.gesture = gesture;
  // Explicit correction panel keeps an annotation hold separate from simulated long navigation.
  if (!$('feedback-panel').hidden && !gesture.annotation) {
    const zone = current().regions?.find((region) => inside(gesture.start, region.rect));
    if (zone) gesture.timer = setTimeout(() => { if (state.gesture === gesture && !gesture.moved) {
      gesture.handled = true; proposeZone('remove', zone, gesture.node); } }, 600);
  }
  phone.setPointerCapture(event.pointerId);
});
phone.addEventListener('pointermove', (event) => { const gesture = state.gesture; if (!gesture || gesture.pointerId !== event.pointerId) return;
  const end = point(event); if (Math.hypot(end.x-gesture.start.x, end.y-gesture.start.y)>.012) { gesture.moved=true; clearTimeout(gesture.timer); }
  if (gesture.annotation) { renderOverlay(); $('overlay').removeAttribute('hidden');
    $('overlay').append(svg('rect', { x:Math.min(end.x,gesture.start.x)*480, y:Math.min(end.y,gesture.start.y)*1040,
      width:Math.abs(end.x-gesture.start.x)*480, height:Math.abs(end.y-gesture.start.y)*1040,
      fill:gesture.annotation === 'forbidden_action' ? 'url(#forbidden-action-hatch)' : 'none',stroke:COLOURS[gesture.annotation === 'forbidden_action' ? 'forbidden' : gesture.annotation],'stroke-width':2,'stroke-dasharray':'1 5','stroke-linecap':'round' })); }
});
phone.addEventListener('pointerup', (event) => { const gesture=state.gesture; state.gesture=null; clearTimeout(gesture?.timer);
  if (!gesture || gesture.handled || gesture.pointerId!==event.pointerId || gesture.node!==state.current) return;
  if (gesture.annotation) { const end=point(event), start=gesture.start;
    $('annotation-kind').value=''; renderOverlay();
    if (Math.hypot(end.x-start.x,end.y-start.y)<.015) { notice('Tracez la zone ou le geste à annoter'); return; }
    const pad=['vertical','horizontal','draggable'].includes(gesture.annotation)?.01:0;
    const rect=[Math.max(0,Math.min(start.x,end.x)-pad),Math.max(0,Math.min(start.y,end.y)-pad),Math.min(1,Math.max(start.x,end.x)+pad),Math.min(1,Math.max(start.y,end.y)+pad)];
    if(rect[2]-rect[0]<.005||rect[3]-rect[1]<.005){notice('Tracez un rectangle couvrant toute la zone');return;}
    proposeZone('add',{kind:gesture.annotation === 'forbidden_action' ? 'action' : gesture.annotation, forbidden: ['forbidden', 'forbidden_action'].includes(gesture.annotation), rect},gesture.node); return;
  }
  follow({ start:gesture.start, end:point(event), duration:performance.now()-gesture.at }); });
phone.addEventListener('pointercancel', () => { clearTimeout(state.gesture?.timer); state.gesture=null; renderOverlay(); });
phone.addEventListener('contextmenu', (event) => event.preventDefault());
let lastWheel=-Infinity;
phone.addEventListener('wheel', (event) => { event.preventDefault(); if (performance.now()-lastWheel<700 || !current()) return;
  lastWheel=performance.now(); const start=point(event), horizontal=event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY);
  const axis=horizontal?'x':'y', delta=(horizontal?event.deltaX||event.deltaY:event.deltaY)>0?-.25:.25;
  follow({ start, end:{...start,[axis]:Math.max(0,Math.min(1,start[axis]+delta))},duration:500 }); },{passive:false});
$('annotation-kind').addEventListener('change',()=>{if($('annotation-kind').value){$('feedback-panel').hidden=true;notice('Tracez la zone sur la capture · annotation seulement');}});
$('overlay-toggle').addEventListener('change',(event)=>{state.overlay=event.target.checked;renderOverlay();});
$('landmarks-toggle').addEventListener('change',(event)=>{state.landmarks=event.target.checked;renderOverlay();});
$('back').addEventListener('click',async()=>{if(state.position>0 && await visit(state.history[state.position-1],{remember:false})) {state.position--; $('back').disabled=state.position<=0;}});
$('home').addEventListener('click',()=>{const node=state.nodes.get('screen:battle')??[...state.nodes.values()].find(n=>n.screen==='battle'&&safeImage(n.image));if(node)visit(node.id);else notice('Capture Combat absente',true);});
$('reload').addEventListener('click',load);
$('options-open').addEventListener('click',()=>{$('options-panel').hidden=!$('options-panel').hidden;$('feedback-panel').hidden=true;});
$('options-close').addEventListener('click',()=>{$('options-panel').hidden=true;});
$('feedback-open').addEventListener('click',()=>{$('options-panel').hidden=true;$('feedback-panel').hidden=false;});
$('feedback-close').addEventListener('click',()=>{$('feedback-panel').hidden=true;});
$('fullscreen').addEventListener('click',async()=>{
  if(document.fullscreenElement){await document.exitFullscreen?.();return;}
  if(document.body.classList.contains('fullscreen-fallback')){document.body.classList.remove('fullscreen-fallback');return;}
  try{if(!document.documentElement.requestFullscreen)throw Error();await document.documentElement.requestFullscreen({navigationUI:'hide'});}
  catch{document.body.classList.add('fullscreen-fallback');}
});
for(const choice of document.querySelectorAll('[name="toolbar-position"]'))choice.addEventListener('change',()=>{document.body.dataset.toolbar=choice.value;});
let barDrag;
$('toolbar-grip').addEventListener('pointerdown',(event)=>{const r=$('toolbar').getBoundingClientRect();barDrag={x:event.clientX,y:event.clientY,left:r.left,top:r.top};event.currentTarget.setPointerCapture(event.pointerId);});
$('toolbar-grip').addEventListener('pointermove',(event)=>{if(!barDrag)return;const r=$('toolbar').getBoundingClientRect();document.body.style.setProperty('--toolbar-x',`${Math.max(0,Math.min(innerWidth-r.width,barDrag.left+event.clientX-barDrag.x))}px`);document.body.style.setProperty('--toolbar-y',`${Math.max(0,Math.min(innerHeight-r.height,barDrag.top+event.clientY-barDrag.y))}px`);});
$('toolbar-grip').addEventListener('pointerup',()=>{barDrag=null;});
$('toolbar-grip').addEventListener('pointercancel',()=>{barDrag=null;});
$('feedback-form').addEventListener('submit',async(event)=>{event.preventDefault();const text=$('feedback-text').value.trim();if(!text||!current())return;
  const body={nodeId:state.current,text};if($('correct-screen').value.trim())body.correctScreen=$('correct-screen').value.trim();
  try{const response=await fetch(serviceUrl('/api/feedback'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!response.ok)throw Error('Retour non enregistré');$('feedback-result').textContent='Retour enregistré';$('feedback-text').value='';}
  catch(error){$('feedback-result').textContent=error.message;}});
window.addEventListener('hashchange',()=>{const id=new URLSearchParams(location.hash.slice(1)).get('node');if(id&&id!==state.current)visit(id);});
load();
setInterval(async()=>{if(document.hidden||state.loading||state.gesture)return;try{const response=await fetch(serviceUrl('/api/revision'),{cache:'no-store'});if(!response.ok)return;const value=await response.json();if(value.revision==null)return;const changed=state.revision!==null&&state.revision!==value.revision;state.revision=value.revision;if(changed)await load();}catch{/* Keep the recorded frame when offline. */}},3000);
