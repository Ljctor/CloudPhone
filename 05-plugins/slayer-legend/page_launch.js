// "Lancer le jeu": the gateway starts the game and brings it to the battle
// screen (TAP TO START, then Confirm on the latest save). Its state is
// followed every 2 s while a launch runs. The row always shows a sentence:
// the gateway's message, else the one of its state (never the state's key).

const SENTENCES = {
  starting: 'Ouverture du jeu', loading: 'Chargement du jeu', done: 'Le jeu est sur l’écran de combat',
  blocked: 'Lancement arrêté : termine-le à la main', deferred: 'Lancement différé', failed: 'Le lancement a échoué',
};

export default function launch(api) {
  const status = { state: 'idle', message: '' };
  let poll = null;
  const follow = async () => {
    const answer = await api.get('/launch').catch(() => null);
    if (answer) Object.assign(status, answer);
    api.refresh();
    const running = ['starting', 'loading'].includes(status.state);
    if (running && !poll) poll = window.setInterval(follow, 2000);
    if (!running && poll) {
      window.clearInterval(poll);
      poll = null;
    }
  };
  follow();

  return {
    options: [
      {
        type: 'action', label: 'Lancer le jeu', button: 'Lancer',
        disabled: () => ['starting', 'loading'].includes(status.state),
        run: async () => {
          const result = await api.post('/launch');
          if (!result.ok) {
            Object.assign(status, {
              state: 'failed', message: result.status === 409 ? 'Un lancement est déjà en cours' : result.body.error ?? `HTTP ${result.status}`,
            });
          }
          await follow();
        },
      },
      {
        type: 'status', label: 'Lancement',
        visible: () => status.state !== 'idle',
        value: () => api.tr(status.message || SENTENCES[status.state] || 'Lancement en cours'),
      },
    ],
    dispose: () => {
      if (poll) window.clearInterval(poll);
    },
  };
}
