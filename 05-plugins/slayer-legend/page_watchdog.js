// "Surveillance mpw18": what the gateway's mpw18 watchdog saw at its last
// look (a French template with its parameters, translated with tr), and
// the shared lease's holder while someone other than the plugin holds it.
// Asked only while the panel shows the row, at most every 15 s (the
// watchdog's own pace), as the trace's counts are.

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
        type: 'status', label: 'Bail',
        visible: () => Boolean(watched.answer?.lease),
        value: () => api.tr('{holder} : {reason}', watched.answer.lease),
      },
    ],
  };
}
