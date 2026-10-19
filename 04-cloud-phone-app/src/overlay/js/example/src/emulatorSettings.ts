// Choices offered for Android's renderer, cores and memory, from the limits
// the gateway reports (GET /api/v1/emulator-settings). Each change restarts
// Android, so the page offers a few sensible values rather than free input.

// Labels and hints are French source text for tr().
export const RENDERER_INFO = {
  lavapipe: { label: 'Lavapipe (recommandé)', hint: 'Couleurs justes, le plus rapide sans carte graphique.' },
  swiftshader: { label: 'SwiftShader', hint: 'Rapide, mais certaines couleurs du jeu peuvent être fausses.' },
  swangle: { label: 'SwANGLE', hint: 'Couleurs justes, mais lent et très gourmand.' },
  software: { label: 'Logiciel (défaut de l’émulateur)', hint: 'Rendu logiciel par défaut de l’émulateur.' },
};

export function rendererOptions(limits) {
  return (limits?.renderers ?? []).map((id) => ({ id, ...(RENDERER_INFO[id] ?? { label: id, hint: '' }) }));
}

// Even core counts up to the host's threads, plus the current value.
export function coreOptions(maxCores, current) {
  const values = new Set();
  for (let n = 2; n <= (maxCores ?? 0); n += 2) values.add(n);
  if (current) values.add(Number(current));
  return [...values].filter((n) => n >= 1).sort((a, b) => a - b);
}

// Whole GiB from 2 GiB up to the limit, every 2 GiB above 8, plus the
// current value; in MiB.
export function memoryOptions(maxMemoryMb, current) {
  const values = new Set();
  for (let gib = 2; gib * 1024 <= (maxMemoryMb ?? 0); gib += gib < 8 ? 1 : 2) values.add(gib * 1024);
  if (current) values.add(Number(current));
  return [...values].sort((a, b) => a - b);
}

export function sameSettings(a, b) {
  return Boolean(a && b) && a.renderer === b.renderer
    && Number(a.cores) === Number(b.cores) && Number(a.memoryMb) === Number(b.memoryMb);
}

// A settings change (GET /api/v1/emulator-settings' request) still waiting
// or being applied: the screen size is then followed more closely.
export function changeInProgress(settings) {
  return ['pending', 'applying'].includes(settings?.request?.state);
}
