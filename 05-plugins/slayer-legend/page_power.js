// The plugin's on/off switch, at the top of its block: kept by the gateway
// (GET /enabled, POST /enabled); while off, the gateway taps nothing (no
// watchdog, no mode switch, no mine) and the page draws nothing over the
// game. This browser's choice follows the gateway's on load (adopt).
// changed(): called when it changes, for the parts that draw.

export default function power(api, { changed }) {
  const on = () => api.setting('power') !== 'off';
  api.get('/enabled').catch(() => null).then((answer) => {
    if (!answer || answer.enabled === on()) return;
    api.adopt?.('power', answer.enabled ? 'on' : 'off');
    changed();
    api.refresh();
  });

  return {
    on,
    options: [
      {
        type: 'choice', key: 'power', label: 'Plugin',
        choices: [{ value: 'on', label: 'Activé' }, { value: 'off', label: 'Désactivé' }],
      },
    ],
    onSetting: (key, value) => {
      if (key !== 'power') return;
      api.post('/enabled', { enabled: value !== 'off' }).catch(() => null);
      changed();
    },
  };
}
