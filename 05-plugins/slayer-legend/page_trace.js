// Copy the displayed frame synchronously before Android receives pointerdown.
// Compression and transport happen afterwards; they never delay the gesture.
// Runtime pixels are classified by the backend, not trusted as screen names.
export function captureBefore(video) {
  if (!video?.videoWidth || !video?.videoHeight || video.readyState < 2
    || typeof CompressionStream === 'undefined') return null;
  const width = video.videoWidth; const height = video.videoHeight;
  if (width > 1080 || height > 2340 || width * height > 3000000) return null;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    context.drawImage(video, 0, 0, width, height);
    return (async () => {
      // Yield until the current pointer event has reached Android's input
      // handler. The canvas already holds the immutable pre-input pixels.
      await new Promise((resolve) => setTimeout(resolve, 0));
      const rgba = context.getImageData(0, 0, width, height).data;
      const rgb = new Uint8Array(width * height * 3);
      for (let pixel = 0; pixel < width * height; pixel++) {
        rgb[pixel * 3] = rgba[pixel * 4];
        rgb[pixel * 3 + 1] = rgba[pixel * 4 + 1];
        rgb[pixel * 3 + 2] = rgba[pixel * 4 + 2];
      }
      const compressed = new Uint8Array(await new Response(
        new Blob([rgb]).stream().pipeThrough(new CompressionStream('deflate')),
      ).arrayBuffer());
      let binary = '';
      for (let start = 0; start < compressed.length; start += 16384) {
        binary += String.fromCharCode(...compressed.subarray(start, start + 16384));
      }
      const encoded = btoa(binary);
      return encoded.length <= 900000 ? { width, height, encoding: 'deflate', rgb: encoded } : null;
    })().catch(() => null);
  } catch { return null; }
}

// The resulting observed graph never authorizes replay or changes the guard.

export default function trace(api) {
  const tracing = () => api.setting('traceTaps') !== 'off';
  const device = api.layer?.closest?.('[data-plugin-layer]')?.parentElement;
  const session = Array.from(globalThis.crypto.getRandomValues(new Uint8Array(16)),
    (value) => value.toString(16).padStart(2, '0')).join('');
  let sequence = 0;
  let before = null;
  let sending = Promise.resolve();
  let failed = false;
  let disposed = false;
  const report = (reason) => {
    if (!failed) api.warn?.(`Navigation not recorded: ${reason}`);
    failed = true;
  };
  const starting = () => {
    sequence++;
    before = null;
    if (!tracing()) return;
    const frame = captureBefore(api.video?.());
    const observation = { session, sequence };
    const started = api.post('/trace/start', observation).catch(() => null);
    before = { frame, observation, started };
  };
  const cancelled = () => { before = null; };
  device?.addEventListener('pointerdown', starting, true);
  device?.addEventListener('pointercancel', cancelled, true);
  const stopTrace = api.onTap?.((tap) => {
    const captured = before;
    before = null;
    if (tracing()) {
      sending = sending.then(async () => {
        const frame = await captured?.frame;
        const started = await captured?.started;
        if (disposed || captured && captured.observation.sequence !== sequence) return;
        if (captured && (!started?.ok || started.body?.accepted === false)) {
          report('gesture observation unavailable'); return;
        }
        const answer = await api.post('/trace', { ...tap,
          ...(captured?.observation ?? {}),
          ...(frame ? { before_frame: frame } : {}) });
        if (answer?.body?.queued === false || answer?.ok === false) {
          report(answer.body?.reason ?? answer.body?.error ?? 'capture unavailable');
        } else failed = false;
      }).catch(() => report('capture transport failed'));
    }
  });
  // The counts, asked only while the panel shows them, at most every 5 s.
  const traced = { answer: null, at: 0, busy: false };
  const watchTrace = () => {
    if (traced.busy || Date.now() - traced.at < 5000) return;
    traced.busy = true;
    api.get('/trace').catch(() => null).then((answer) => {
      Object.assign(traced, { answer, at: Date.now(), busy: false });
      api.refresh();
    });
  };

  return {
    options: [],
    debug: [
      {
        type: 'choice', key: 'traceTaps', label: 'Enregistrer mes parcours',
        choices: [{ value: 'on', label: 'Activé' }, { value: 'off', label: 'Désactivé' }],
      },
      {
        type: 'status', label: 'Parcours enregistrés',
        value: () => {
          watchTrace();
          const answer = traced.answer;
          if (!answer) return '…';
          if (!answer.enabled) return api.tr('indisponible (gateway sans dossier de données)');
          return api.tr('{nodes} écrans, {taps} appuis', { nodes: answer.nodes, taps: answer.taps ?? answer.edges });
        },
      },
    ],
    dispose: () => {
      stopTrace?.();
      disposed = true;
      device?.removeEventListener('pointerdown', starting, true);
      device?.removeEventListener('pointercancel', cancelled, true);
      before = null;
    },
  };
}
