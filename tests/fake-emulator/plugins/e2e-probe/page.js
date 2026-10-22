// Test plugin for the e2e suite, page side: one option of each type, a
// drawing in the plugin's layer, calls to its gateway routes, a warning
// in the page's log; two dialog
// rows sharing a radio group, the second with nothing to configure and
// chosen only once the first's toggle is on.
import { FRAME_COLOUR } from './helper.js';

export default function activate(api) {
  api.addTranslations({
    'Dessiner un cadre': 'Draw a frame',
    'Limite': 'Limit',
    'Compter': 'Count',
    'Compteur': 'Counter',
    'Vidéo vue': 'Video seen',
    'Choix A': 'Choice A',
    'Choix B': 'Choice B',
    'Réglages du choix A': 'Choice A settings',
    'Autoriser B': 'Allow B',
    'Avertir': 'Warn',
  });
  const state = { count: null };
  let frame = null;
  const draw = (on) => {
    if (on && !frame) {
      frame = document.createElement('div');
      frame.dataset.e2eProbe = 'frame';
      frame.style.cssText = `position:absolute;left:0;top:0;width:${api.screenWidth()}px;height:20px;background:${FRAME_COLOUR}`;
      api.layer.appendChild(frame);
    }
    if (!on && frame) {
      frame.remove();
      frame = null;
    }
  };
  draw(Boolean(api.setting('draw')));
  api.get('/count').then((answer) => { state.count = answer?.count ?? null; api.refresh(); });
  return {
    options: [
      { type: 'toggle', key: 'draw', label: 'Dessiner un cadre' },
      { type: 'number', key: 'limit', label: 'Limite', placeholder: '10' },
      {
        type: 'action', label: 'Compter', button: 'Compter',
        run: async () => {
          const result = await api.post('/count', { by: 1 });
          state.count = result.ok ? result.body.count : `HTTP ${result.status}`;
          api.refresh();
        },
      },
      { type: 'status', label: 'Compteur', value: () => (state.count === null ? '–' : String(state.count)) },
      // A warning record in the page's log (api.warn): nothing pops up.
      { type: 'action', label: 'Avertir', button: 'Avertir', run: () => api.warn('Probe warning') },
      {
        type: 'status', label: 'Vidéo vue',
        value: () => { const v = api.video(); return v && v.videoWidth ? `${v.videoWidth}×${v.videoHeight}` : '–'; },
      },
      {
        type: 'dialog', label: 'Choix A', title: 'Réglages du choix A',
        select: { key: 'pick', value: 'a', default: 'a' },
        options: [{ type: 'toggle', key: 'allowB', label: 'Autoriser B' }],
      },
      {
        type: 'dialog', label: 'Choix B',
        select: { key: 'pick', value: 'b', default: 'a', disabled: () => !api.setting('allowB') },
        options: [],
      },
    ],
    onSetting: (key, value) => { if (key === 'draw') draw(Boolean(value)); },
    dispose: () => draw(false),
  };
}
