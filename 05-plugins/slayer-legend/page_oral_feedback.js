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

// The HTTP review port cannot request a microphone. Its HTTPS proxy is the
// same interface; never substitute a file picker or another recording app.
export function secureRecordingUrl(configuredUrl, location = globalThis.location) {
  if (typeof configuredUrl !== 'string') return null;
  try {
    const url = new URL(configuredUrl);
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash
        || url.pathname !== '/navigation-review/') return null;
    url.hash = location?.hash ?? new URL(location.href).hash;
    return url.href;
  } catch { return null; }
}

async function configuredRecordingUrl() {
  try {
    // The live plugin imports this shared module from the review service too.
    // Resolve its configuration alongside the module, preserving HTTPS proxy prefixes.
    const source = new URL(import.meta.url);
    if (!['http:', 'https:'].includes(source.protocol)) return null;
    const response = await fetch(new URL('api/recording-config', source), { cache: 'no-store' });
    return response.ok ? (await response.json()).secure_review_url ?? null : null;
  } catch { return null; }
}

export default function oralFeedback({ capture, transport, secureReviewUrl = undefined, tr = (value) => value }) {
  const panel = document.createElement('div'); panel.setAttribute('data-oral-feedback', '');
  panel.style.cssText = 'display:flex;flex-wrap:wrap;gap:5px;margin-top:6px;align-items:center;pointer-events:auto';
  const button = document.createElement('button'); button.type = 'button'; button.setAttribute('data-oral-control', 'record');
  const send = document.createElement('button'); send.type = 'button'; send.textContent = tr('Envoyer'); send.setAttribute('data-oral-control', 'send');
  const cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = tr('Annuler'); cancel.setAttribute('data-oral-control', 'cancel');
  const audio = document.createElement('audio'); audio.controls = true; audio.hidden = true;
  audio.setAttribute('data-oral-preview', ''); audio.style.cssText = 'width:100%;max-width:100%;height:38px';
  const status = document.createElement('span'); status.setAttribute('role', 'status'); status.style.cssText = 'font-size:11px;flex-basis:100%';
  const secure = document.createElement('a'); secure.textContent = tr('Ouvrir l’enregistrement sécurisé');
  secure.style.cssText = 'font-size:12px;color:#9bcaff'; secure.hidden = true;
  panel.append(button, send, cancel, audio, status, secure);
  const microphone = Boolean(globalThis.isSecureContext && navigator.mediaDevices?.getUserMedia && globalThis.MediaRecorder);
  let phase = 'idle', generation = 0, disposed = false, recorder = null, stream = null, timer = null;
  let snapshot = null, saved = null, blob = null, started = 0, previewUrl = null;
  const stopTracks = () => { stream?.getTracks().forEach((track) => track.stop()); stream = null; clearInterval(timer); timer = null; };
  const clearPreview = () => { audio.pause?.(); audio.removeAttribute('src'); audio.load?.(); audio.hidden = true;
    if (previewUrl) URL.revokeObjectURL(previewUrl); previewUrl = null; };
  function paint(message = '') {
    button.textContent = tr(phase === 'recording' ? 'Arrêter' : 'Enregistrer un retour vocal');
    button.disabled = !microphone || ['permission', 'stopping', 'uploading', 'preview'].includes(phase) || Boolean(blob);
    send.hidden = !blob || !['preview', 'error'].includes(phase);
    send.textContent = tr(phase === 'error' ? 'Réessayer l’envoi' : 'Envoyer');
    cancel.hidden = phase === 'idle'; cancel.disabled = phase === 'uploading';
    button.style.color = phase === 'recording' ? '#ff5353' : '';
    if (message) status.textContent = tr(message);
  }
  function reset(message = 'Enregistrement annulé.') {
    generation++;
    if (recorder) { recorder.onstop = recorder.onerror = recorder.ondataavailable = null;
      if (recorder.state !== 'inactive') recorder.stop(); recorder = null; }
    stopTracks(); clearPreview(); phase = 'idle'; blob = null; snapshot = null; saved = null; paint(message);
  }
  function stopRecording() {
    if (phase !== 'recording' || recorder?.state !== 'recording') return;
    phase = 'stopping'; paint('Préparation de l’aperçu audio…'); recorder.stop();
  }
  async function begin() {
    const ticket = ++generation; saved = null; blob = null; snapshot = null; clearPreview();
    phase = 'permission'; paint('Autorisation du microphone…');
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (ticket !== generation || disposed) { media.getTracks().forEach((track) => track.stop()); return; }
      stream = media;
      // Freeze exactly what is displayed as recording begins, after permission.
      // No developer write occurs until the user explicitly presses Send.
      snapshot = JSON.parse(JSON.stringify(capture()));
      const mimeType = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4']
        .find((mime) => MediaRecorder.isTypeSupported?.(mime));
      const active = new MediaRecorder(media, mimeType ? { mimeType, audioBitsPerSecond: 64000 } : undefined);
      recorder = active; const pieces = []; let size = 0;
      active.ondataavailable = (event) => {
        if (ticket !== generation || disposed) return;
        if (event.data.size) { pieces.push(event.data); size += event.data.size; }
        if (size > MAX_AUDIO) stopRecording();
      };
      active.onstop = () => {
        if (ticket !== generation || disposed) return;
        stopTracks(); recorder = null;
        blob = new Blob(pieces, { type: active.mimeType || mimeType || 'audio/webm' });
        if (!blob.size || blob.size > MAX_AUDIO) { blob = null; phase = 'error'; paint('Le message vocal est vide ou dépasse 12 Mo.'); return; }
        previewUrl = URL.createObjectURL(blob); audio.src = previewUrl; audio.hidden = false;
        phase = 'preview'; paint('Écouter le message, puis Envoyer ou Annuler.');
      };
      active.onerror = () => {
        if (ticket !== generation || disposed) return;
        generation++; active.onstop = active.ondataavailable = active.onerror = null;
        if (active.state !== 'inactive') active.stop();
        stopTracks(); recorder = null; phase = 'error'; paint('L’enregistrement audio a échoué.');
      };
      active.start(1000); started = performance.now(); phase = 'recording'; paint(); status.textContent = `REC · 0:00 · ${tr('Capture et overlay figés')}`;
      timer = setInterval(() => {
        const seconds = Math.floor((performance.now() - started) / 1000);
        status.textContent = `${tr('REC')} · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} · ${tr('Capture et overlay figés')}`;
        if (seconds >= MAX_SECONDS) stopRecording();
      }, 250);
    } catch (error) {
      if (ticket !== generation || disposed) return;
      stopTracks(); recorder = null; phase = 'error';
      paint(error.name === 'NotAllowedError' ? 'Accès au microphone refusé.' : error.message || 'Microphone indisponible.');
    }
  }
  async function upload() {
    if (!blob || !['preview', 'error'].includes(phase)) return;
    const ticket = generation;
    try {
      phase = 'uploading'; paint('Envoi du retour vocal…');
      if (!saved) {
        const created = await transport.create(snapshot);
        if (ticket !== generation || disposed) return;
        saved = created;
      }
      await transport.attach(saved, blob);
      if (ticket !== generation || disposed) return;
      reset('Retour vocal enregistré avec sa capture et son overlay.');
    } catch (error) {
      if (ticket !== generation || disposed) return;
      phase = 'error'; paint(tr(error.message) + (error.status ? ` (${error.status})` : ''));
    }
  }
  button.onclick = (event) => { event.preventDefault(); event.stopPropagation();
    if (!microphone || disposed) return;
    if (phase === 'recording') stopRecording(); else if (['idle', 'error'].includes(phase) && !blob) begin(); };
  send.onclick = (event) => { event.preventDefault(); event.stopPropagation(); upload(); };
  cancel.onclick = (event) => { event.preventDefault(); event.stopPropagation(); if (phase !== 'uploading') reset(); };
  panel.onpointerdown = panel.onpointerup = (event) => event.stopPropagation();
  if (!microphone) {
    paint(globalThis.isSecureContext ? 'L’enregistrement direct n’est pas disponible dans ce navigateur.'
      : 'Recherche de l’interface HTTPS configurée…');
    if (!globalThis.isSecureContext) {
      Promise.resolve(secureReviewUrl === undefined ? configuredRecordingUrl() : secureReviewUrl).then((configured) => {
        if (disposed) return;
        const url = secureRecordingUrl(configured);
        secure.hidden = !url;
        if (url) secure.href = url;
        paint(url ? 'L’enregistrement direct nécessite la version HTTPS.'
          : 'Enregistrement sécurisé indisponible : aucune origine HTTPS configurée.');
      }).catch(() => { if (!disposed) paint('Enregistrement sécurisé indisponible : aucune origine HTTPS configurée.'); });
    }
  } else paint();
  return { element: panel, cancel: reset, get busy() { return phase !== 'idle'; }, dispose() { disposed = true; reset(); } };
}
