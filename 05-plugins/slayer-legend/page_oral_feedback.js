// Spoken developer feedback. Capturing evidence never sends input to Android.
const MAX_AUDIO = 12 * 1024 * 1024;
const MAX_SECONDS = 120;
const NS = 'http://www.w3.org/2000/svg';
const STYLE = ['position', 'left', 'top', 'right', 'bottom', 'width', 'height', 'display', 'visibility',
  'opacity', 'transform', 'transform-origin', 'color', 'background-color', 'background-image',
  'font-family', 'font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing',
  'text-align', 'text-shadow', 'white-space', 'overflow', 'border', 'border-radius', 'outline',
  'outline-offset', 'padding', 'margin', 'box-sizing', 'z-index', 'flex-direction', 'align-items', 'justify-content'];

function renderedDom(layer) {
  const clone = layer.cloneNode(true);
  const originals = [layer, ...layer.querySelectorAll('*')];
  const copies = [clone, ...clone.querySelectorAll('*')];
  originals.forEach((original, index) => {
    let copy = copies[index];
    if (['SCRIPT', 'IFRAME', 'AUDIO', 'VIDEO'].includes(original.tagName)) { copy.remove(); return; }
    for (const attribute of [...copy.attributes]) if (attribute.name.startsWith('on')) copy.removeAttribute(attribute.name);
    const computed = getComputedStyle(original);
    copy.setAttribute('style', STYLE.map((key) => `${key}:${computed.getPropertyValue(key)}`).join(';'));
    if (original.tagName === 'CANVAS') {
      const image = document.createElement('img');
      image.src = original.toDataURL('image/png'); image.setAttribute('style', copy.getAttribute('style'));
      image.width = original.width; image.height = original.height; copy.replaceWith(image);
    } else if (original.tagName === 'INPUT') copy.setAttribute('value', original.value);
    else if (original.tagName === 'TEXTAREA') copy.textContent = original.value;
    else if (original.tagName === 'SELECT') {
      [...copy.options].forEach((option) => { option.toggleAttribute('selected', option.value === original.value); });
    }
  });
  const result = clone.outerHTML;
  if (new TextEncoder().encode(result).length > 512 * 1024) throw Error('L’overlay est trop volumineux pour enregistrer ce retour.');
  return result;
}

// Read actual computed geometry/styles, rather than reconstructing the overlay
// from a newer server catalogue. The full DOM snapshot retains other counters.
function renderedSvg(layer, width, height) {
  const bounds = layer.getBoundingClientRect();
  const root = document.createElementNS(NS, 'svg');
  root.setAttribute('xmlns', NS); root.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const sx = width / bounds.width, sy = height / bounds.height;
  for (const box of layer.querySelectorAll('[data-zone-source]')) {
    const rect = box.getBoundingClientRect(), css = getComputedStyle(box);
    if (css.display === 'none' || css.visibility === 'hidden') continue;
    const x = (rect.left - bounds.left) * sx, y = (rect.top - bounds.top) * sy;
    const w = rect.width * sx, h = rect.height * sy;
    const group = document.createElementNS(NS, 'g'); group.setAttribute('opacity', css.opacity);
    const background = document.createElementNS(NS, 'rect');
    for (const [key, value] of Object.entries({ x, y, width: w, height: h, fill: css.backgroundColor,
      stroke: css.borderTopColor, 'stroke-width': parseFloat(css.borderTopWidth) * sx || 0 })) background.setAttribute(key, value);
    group.append(background);
    if (parseFloat(css.outlineWidth)) {
      const outline = background.cloneNode();
      for (const [key, value] of Object.entries({ x: x + 4 * sx, y: y + 4 * sy, width: Math.max(0, w - 8 * sx),
        height: Math.max(0, h - 8 * sy), fill: 'none', stroke: css.outlineColor, 'stroke-width': parseFloat(css.outlineWidth) * sx })) outline.setAttribute(key, value);
      group.append(outline);
    }
    for (const child of box.querySelectorAll(':scope > svg')) {
      const copy = child.cloneNode(true); copy.removeAttribute('style');
      for (const [key, value] of Object.entries({ x, y, width: w, height: h })) copy.setAttribute(key, value);
      group.append(copy);
    }
    for (const span of box.querySelectorAll(':scope > span')) {
      const position = span.getBoundingClientRect(), style = getComputedStyle(span);
      const text = document.createElementNS(NS, 'text'); text.textContent = span.textContent;
      for (const [key, value] of Object.entries({ x: (position.left - bounds.left) * sx,
        y: (position.top - bounds.top + parseFloat(style.fontSize)) * sy,
        fill: style.color, 'font-size': parseFloat(style.fontSize) * sy, 'font-family': style.fontFamily,
        'font-weight': style.fontWeight })) text.setAttribute(key, value);
      group.append(text);
    }
    root.append(group);
  }
  return new XMLSerializer().serializeToString(root);
}

export function freezeOralContext({ image, layer, source, nodeId, screen, displayName, regions, state = {}, enabled = true, svgElement = null }) {
  const width = image?.videoWidth || image?.naturalWidth, height = image?.videoHeight || image?.naturalHeight;
  if (!width || !height || width * height > 3000000 || image.videoWidth && image.readyState < 2) throw Error('Aucune image affichée à associer au retour vocal.');
  const startedAt = Date.now() / 1000;
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
  canvas.getContext('2d').drawImage(image, 0, 0, width, height);
  const base64 = canvas.toDataURL('image/png').split(',')[1];
  const bounds = layer.getBoundingClientRect();
  const overlay = { svg: !enabled ? `<svg xmlns="${NS}" viewBox="0 0 ${width} ${height}"/>`
    : svgElement ? new XMLSerializer().serializeToString(svgElement.cloneNode(true)) : renderedSvg(layer, width, height), dom: renderedDom(layer),
    regions: JSON.parse(JSON.stringify(regions)), enabled, displayName,
    state: JSON.parse(JSON.stringify(state)) };
  return { source, nodeId, screen: screen ?? 'unknown', startedAt,
    capture: { mimeType: 'image/png', base64, width, height }, overlay,
    view: { width: bounds.width, height: bounds.height, left: bounds.left, top: bounds.top,
      devicePixelRatio: window.devicePixelRatio, videoTime: image.currentTime ?? null },
    assets: { rendererVersion: 'oral-context-v1', overlaySnapshotFormat: 1 } };
}

export function oralTransport(base, { token = null } = {}) {
  async function request(path, options = {}) {
    const headers = { ...(options.headers ?? {}) };
    if (token) headers['X-CloudPhone-Token'] = await token();
    const response = await fetch(base + path, { ...options, headers });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) { const error = Error('Retour vocal non enregistré.'); error.status = response.status; throw error; }
    return body;
  }
  return {
    create: (context) => request('/contexts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(context) }),
    attach: (context, blob) => request(`/${context.id}/audio`, { method: 'POST',
      headers: { 'Content-Type': blob.type, 'X-Context-SHA256': context.contextSha256 }, body: blob }),
  };
}

export function liveOralTransport(api) {
  let selected = null;
  async function choose() {
    if (selected) return selected;
    selected = (async () => {
      const available = await api.get('/navigation/oral-feedback').catch(() => null);
      if (Array.isArray(available?.items)) return oralTransport(api.url('/navigation/oral-feedback'), {
        token: async () => {
          const response = await fetch(new URL('/api/v1/session/token', api.url('/')).href, { cache: 'no-store' });
          if (!response.ok) throw Error('Enregistrement du retour indisponible.');
          return (await response.json()).token;
        },
      });
      // The separate review service can receive evidence while the game
      // gateway stays running. Only explicitly configured frontend origins
      // are accepted there; this never opens an Android control channel.
      const url = new URL(api.url('/'));
      if (url.protocol === 'https:') url.pathname = '/navigation-review/api/oral-feedback';
      else { url.port = '7890'; url.pathname = '/api/oral-feedback'; }
      url.search = ''; url.hash = '';
      return oralTransport(url.href);
    })();
    selected.catch(() => { selected = null; });
    return selected;
  }
  return { create: async (context) => (await choose()).create(context),
    attach: async (context, blob) => (await choose()).attach(context, blob) };
}

export default function oralFeedback({ capture, transport, tr = (value) => value }) {
  const panel = document.createElement('div'); panel.setAttribute('data-oral-feedback', '');
  panel.style.cssText = 'display:flex;flex-wrap:wrap;gap:5px;margin-top:6px;align-items:center;pointer-events:auto';
  const button = document.createElement('button'); button.type = 'button'; button.setAttribute('data-oral-control', 'record');
  const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = tr('Annuler'); cancel.hidden = true;
  cancel.setAttribute('data-oral-control', 'cancel');
  const status = document.createElement('span'); status.setAttribute('role', 'status'); status.style.cssText = 'font-size:11px;flex-basis:100%';
  const file = document.createElement('input'); file.type = 'file'; file.accept = 'audio/*'; file.setAttribute('capture', 'microphone'); file.hidden = true;
  panel.append(button, cancel, status, file);
  const microphone = Boolean(globalThis.isSecureContext && navigator.mediaDevices?.getUserMedia && globalThis.MediaRecorder);
  let phase = 'idle', generation = 0, disposed = false, recorder = null, stream = null, timer = null;
  let snapshot = null, saved = null, blob = null, started = 0, contextPromise = null;
  const stopTracks = () => { stream?.getTracks().forEach((track) => track.stop()); stream = null; clearInterval(timer); timer = null; };
  function paint(message = '') {
    button.textContent = tr(phase === 'recording' ? 'Terminer et envoyer' : phase === 'error' && blob ? 'Réessayer l’envoi'
      : microphone ? 'Enregistrer un retour vocal' : 'Joindre un retour vocal');
    button.disabled = ['saving', 'permission', 'uploading', 'choosing'].includes(phase);
    cancel.hidden = !['recording', 'permission', 'error', 'choosing'].includes(phase);
    button.style.color = phase === 'recording' ? '#ff5353' : '';
    if (message) status.textContent = tr(message);
  }
  async function upload(ticket) {
    try {
      if (!blob?.size || blob.size > MAX_AUDIO) { blob = null; throw Error('Le message vocal est vide ou dépasse 12 Mo.'); }
      phase = 'uploading'; paint('Envoi du retour vocal…');
      saved = saved ?? await contextPromise;
      if (ticket !== generation || disposed) return;
      await transport.attach(saved, blob);
      if (ticket !== generation || disposed) return;
      phase = 'idle'; blob = null; paint('Retour vocal enregistré avec sa capture et son overlay.');
    } catch (error) {
      if (ticket !== generation || disposed) return;
      phase = 'error'; paint(tr(error.message) + (error.status ? ` (${error.status})` : ''));
    }
  }
  function reset() {
    generation++;
    if (recorder) {
      recorder.onstop = recorder.onerror = recorder.ondataavailable = null;
      if (recorder.state !== 'inactive') recorder.stop();
      recorder = null;
    }
    stopTracks(); phase = 'idle'; blob = null; snapshot = null; saved = null; contextPromise = null; file.value = '';
    paint('Enregistrement annulé.');
  }
  function begin() {
    const ticket = ++generation;
    try { snapshot = capture(); } catch (error) { phase = 'idle'; paint(error.message); return; }
    saved = null; blob = null;
    contextPromise = transport.create(snapshot); contextPromise.catch(() => {});
    if (!microphone) {
      phase = 'choosing'; paint('Capture et overlay figés pour ce message vocal.'); file.value = ''; file.click(); return;
    }
    phase = 'permission'; paint('Autorisation du microphone…');
    navigator.mediaDevices.getUserMedia({ audio: true }).then(async (media) => {
      if (ticket !== generation || disposed) { media.getTracks().forEach((track) => track.stop()); return; }
      stream = media;
      const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'].find((mime) => MediaRecorder.isTypeSupported(mime));
      recorder = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 64000 } : undefined);
      const pieces = []; let size = 0;
      recorder.ondataavailable = (event) => { if (event.data.size) { pieces.push(event.data); size += event.data.size; }
        if (size > MAX_AUDIO && recorder.state === 'recording') recorder.stop(); };
      recorder.onstop = () => {
        const mime = recorder?.mimeType ?? mimeType ?? 'audio/webm'; stopTracks();
        if (ticket !== generation || disposed) return;
        blob = new Blob(pieces, { type: mime }); upload(ticket);
      };
      recorder.onerror = () => {
        if (ticket !== generation) return;
        generation++; recorder.onstop = recorder.ondataavailable = null;
        if (recorder.state !== 'inactive') recorder.stop();
        stopTracks(); phase = 'error'; paint('L’enregistrement audio a échoué.');
      };
      recorder.start(1000); started = performance.now(); phase = 'recording'; paint('Enregistrement en cours…');
      timer = setInterval(() => {
        const seconds = Math.floor((performance.now() - started) / 1000);
        status.textContent = `${tr('Enregistrement en cours…')} ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} · ${tr('Capture et overlay figés')}`;
        if (seconds >= MAX_SECONDS && recorder.state === 'recording') recorder.stop();
      }, 250);
    }).catch((error) => { stopTracks(); if (ticket === generation) { phase = 'error'; paint(error.name === 'NotAllowedError' ? 'Accès au microphone refusé.' : 'Microphone indisponible.'); } });
  }
  button.onclick = (event) => {
    event.preventDefault(); event.stopPropagation();
    if (phase === 'recording') { phase = 'uploading'; paint('Envoi du retour vocal…'); recorder.stop(); }
    else if (phase === 'error' && blob) { if (!saved) contextPromise = transport.create(snapshot); upload(generation); }
    else begin();
  };
  cancel.onclick = (event) => { event.preventDefault(); event.stopPropagation(); reset(); };
  file.onchange = () => { blob = file.files?.[0] ?? null; if (blob) upload(generation); else reset(); };
  file.addEventListener?.('cancel', reset);
  panel.onpointerdown = panel.onpointerup = (event) => event.stopPropagation();
  paint();
  return { element: panel, cancel: reset, get busy() { return phase !== 'idle'; }, dispose() { disposed = true; reset(); } };
}
