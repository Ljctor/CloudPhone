// Navigation trace: each tap on the game goes to the gateway, which
// records the screens before and after it (screen name and a small grey
// thumbnail, never a screenshot), building a graph of the game's screens
// (never replayed). On unless the user turned it off. Fire and forget: a
// lost tap is only a missing edge. Options: the "Navigation" section.

export default function trace(api) {
  const tracing = () => api.setting('traceTaps') !== 'off';
  const stopTrace = api.onTap?.((tap) => {
    if (tracing()) api.post('/trace', tap).catch(() => null);
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
    options: [
      { type: 'section', key: 'navigation', label: 'Navigation', folded: true },
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
    },
  };
}
