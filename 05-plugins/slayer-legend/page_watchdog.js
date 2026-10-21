// "Surveillance mpw18": what the gateway's mpw18 watchdog saw at its last
// look (a French template with its parameters, translated with tr), and
// the shared lease's holder while someone other than the plugin holds it.
// Asked only while the panel shows the row, at most every 15 s (the
// watchdog's own pace), as the trace's counts are.

// The watchdog's repairs (watchdog_rules.REPAIR_NAMES).
const REPAIRS = {
  relaunch: 'relance du jeu', back_to_battle: 'retour au combat', stage_change: 'changement de stage',
  select_preset: 'choix du préréglage de combat', loadout: 'rééquipement', auto_on: 'remise en marche d’AUTO',
};

export default function watchdog(api) {
  const watched = { answer: null, at: 0, busy: false };
  const watch = () => {
    if (watched.busy || Date.now() - watched.at < 15000) return;
    watched.busy = true;
    api.get('/watchdog').catch(() => null).then((answer) => {
      Object.assign(watched, { answer: answer ?? watched.answer, at: Date.now(), busy: false });
      api.refresh();
    });
  };

  return {
    options: [
      {
        type: 'status', label: 'Surveillance mpw18',
        value: () => {
          watch();
          const status = watched.answer?.status;
          return status ? api.tr(status.template, status.params) : '…';
        },
      },
      {
        type: 'status', label: 'Préréglage et AUTO',
        visible: () => Boolean(watched.answer?.controls),
        value: () => api.tr(watched.answer.controls.template, watched.answer.controls.params),
      },
      {
        // Each repair backing off: when its next attempt is allowed, and
        // a button to try now.
        type: 'status', label: 'Prochains essais',
        visible: () => Object.keys(watched.answer?.counters?.next_attempt ?? {}).length > 0,
        value: () => Object.values(watched.answer.counters.next_attempt).map(({ repair, next }) => {
          const at = new Date(next * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          return `${api.tr(repair)} : ${next * 1000 > Date.now() ? at : api.tr('maintenant')}`;
        }).join(' · '),
      },
      // « Réessayer maintenant », one row per repair backing off.
      ...Object.entries(REPAIRS).map(([kind, repair]) => ({
        type: 'action', label: repair, button: 'Réessayer maintenant',
        visible: () => Boolean(watched.answer?.counters?.next_attempt?.[kind]),
        run: async () => {
          const result = await api.post('/watchdog/retry', { kind }).catch(() => null);
          if (result?.ok) Object.assign(watched, { answer: result.body, at: Date.now() });
          api.refresh();
        },
      })),
      {
        type: 'status', label: 'Bail',
        visible: () => Boolean(watched.answer?.lease),
        value: () => api.tr('{holder} : {reason}', watched.answer.lease),
      },
    ],
  };
}
