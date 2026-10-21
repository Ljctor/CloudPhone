// The watchdog's part of the mode's État row (page_mode.js): what the
// gateway's watchdog saw at its last look on the selected mode (a French
// template with its parameters, translated with tr), the shared lease's
// holder while someone other than the plugin holds it, and « Réessayer »
// while a repair backs off. No option rows of its own. Asked only while
// the panel shows the row, at most every 15 s (the watchdog's own pace).

// The plugin's own holders of the lease (not shown).
const OWN = ['watchdog', 'stage_change', 'mine', 'launch'];

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
    // The text after the mode's own (" · OK"), '' when the watchdog has
    // nothing to say for mode: free play, a mode's entry, another mode
    // than its last look's.
    line: (mode) => {
      watch();
      const answer = watched.answer;
      if (!answer?.line || answer.mode !== mode || mode === 'free') return '';
      if (answer.status?.template === 'En pause : entrée dans le mode {mode}') return '';
      const parts = [api.tr(answer.line.template, answer.line.params)];
      const held = answer.lease;
      if (held && !OWN.includes(held.holder)) parts.push(api.tr('bail : {holder} ({reason})', held));
      return ` · ${parts.join(' · ')}`;
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
