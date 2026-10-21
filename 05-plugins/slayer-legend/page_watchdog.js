// The watchdog's part of the mode's État row (page_mode.js): what the
// gateway's watchdog saw at its last look on the selected mode (a French
// template with its parameters, translated with tr) and « Réessayer »
// while a repair backs off. No option rows of its own; debug: the shared
// lease's holder and the watchdog's counters. Asked only while the panel
// shows them, at most every 15 s (the watchdog's own pace).

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
    options: [],
    debug: [
      {
        type: 'status', label: 'Bail',
        value: () => {
          watch();
          const held = watched.answer?.lease;
          if (!watched.answer) return '…';
          return held ? api.tr('{holder} ({reason})', held) : api.tr('libre');
        },
      },
      {
        type: 'status', label: 'Surveillance',
        value: () => {
          watch();
          const counters = watched.answer?.counters;
          if (!counters) return '…';
          return api.tr('{looks} vérifications, {bad} échecs d’affilée, {alerts} alertes',
            { looks: counters.looks, bad: counters.bad_in_a_row, alerts: counters.alerts });
        },
      },
    ],
    // The text after the mode's own (" · OK"), '' when the watchdog has
    // nothing to say for mode: free play, a mode's entry, another mode
    // than its last look's.
    line: (mode) => {
      watch();
      const answer = watched.answer;
      if (!answer?.line || answer.mode !== mode || mode === 'free') return '';
      if (answer.status?.template === 'En pause : entrée dans le mode {mode}') return '';
      return ` · ${api.tr(answer.line.template, answer.line.params)}`;
    },
    // « Réessayer » while a repair backs off: each waiting kind starts over.
    retry: (mode) => {
      const answer = watched.answer;
      if (answer?.mode !== mode || !answer.waiting?.length) return null;
      return {
        label: 'Réessayer',
        run: async () => {
          for (const kind of answer.waiting) {
            const result = await api.post('/watchdog/retry', { kind }).catch(() => null);
            if (result?.ok) Object.assign(watched, { answer: result.body, at: Date.now() });
          }
          api.refresh();
        },
      };
    },
  };
}
