// The displayed switch follows gateway acknowledgement. A local preference
// cannot confirm that automation stopped.
import { withDeadline } from './page_request_deadline.js';
const ENGLISH = {
  "État du serveur inconnu": "Server state unknown",
  "Serveur : plugin activé": "Server: plugin enabled",
  "Serveur : plugin désactivé": "Server: plugin disabled",
  "Vérification impossible · état du serveur non confirmé": "Verification failed · server state unconfirmed",
  "Activation non confirmée": "Activation unconfirmed",
  "Arrêt non confirmé": "Stop unconfirmed",
  "Vérification du serveur impossible": "Server verification failed",
  "Vérification…": "Checking…",
  "Contrôle du plugin": "Plugin control",
  "Activation demandée…": "Activation requested…",
  "Arrêt demandé…": "Stop requested…",
  "Vérifier": "Check",
  "État du serveur indisponible": "Server state unavailable",
  "Délai dépassé · résultat non confirmé": "Request timed out · outcome unconfirmed"
};

export default function power(api, { changed }) {
  api.addTranslations?.(ENGLISH);
  const state = { confirmed: null, desired: null, busy: false, reading: false, error: '', uncertain: false, awaiting: null, commandError: false, revision: 0, disposed: false };
  const text = (value) => api.tr(value);
  const confirmedText = () => state.confirmed === null ? text('État du serveur inconnu')
    : text(state.confirmed ? 'Serveur : plugin activé' : 'Serveur : plugin désactivé');
  const publish = () => {
    if (state.disposed) return;
    if (state.confirmed !== null) api.adopt?.('power', state.confirmed ? 'on' : 'off');
    changed(); api.refresh();
  };
  const accept = (answer) => {
    if (typeof answer?.enabled !== 'boolean') return false;
    state.confirmed = answer.enabled;
    return true;
  };
  const refresh = async () => {
    if (state.disposed || state.busy || state.reading) return;
    state.reading = true;
    const revision = state.revision;
    try {
      const answer = await withDeadline(api.get('/enabled'));
      if (state.disposed || revision !== state.revision || state.busy) return;
      if (!accept(answer)) throw Error('État du serveur indisponible');
      state.uncertain = false;
      if (state.awaiting !== null && state.confirmed === state.awaiting) {
        state.awaiting = null; state.commandError = false; state.error = '';
      }
      if (!state.commandError) state.error = '';
    } catch {
      if (revision === state.revision && !state.busy && !state.commandError) state.error = text('Vérification impossible · état du serveur non confirmé');
    } finally { state.reading = false; publish(); }
  };
  const send = async () => {
    if (state.busy || state.disposed) return;
    state.busy = true; publish();
    try {
      while (state.desired !== null && (state.uncertain || state.desired !== state.confirmed) && !state.disposed) {
        const enabled = state.desired;
        const revision = state.revision;
        let timedOut = false;
        const result = await withDeadline(api.post('/enabled', { enabled }), { onLate: refresh })
          .catch((error) => { timedOut = error?.code === 'deadline'; return null; });
        if (state.disposed) return;
        if (result?.ok && typeof result.body?.enabled === 'boolean') state.uncertain = false;
        if (!result?.ok || !accept(result.body) || state.confirmed !== enabled) {
          // A failed response can still follow a successful server mutation.
          // Re-read before reporting the last confirmed state; never invent it.
          const answer = await withDeadline(api.get('/enabled')).catch(() => null);
          if (state.disposed) return;
          const reconciled = accept(answer);
          if (revision === state.revision) {
            state.error = reconciled && state.confirmed === enabled ? '' : text(enabled ? 'Activation non confirmée' : 'Arrêt non confirmé');
            state.uncertain = !reconciled || (timedOut && state.confirmed !== enabled);
            if (timedOut && !(reconciled && state.confirmed === enabled)) state.error = `${text('Délai dépassé · résultat non confirmé')} · ${state.error || confirmedText()}`;
            if (!reconciled) state.error += ` · ${text('Vérification du serveur impossible')}`;
            state.commandError = Boolean(state.error);
            state.awaiting = state.error ? enabled : null;
            state.desired = null;
          }
        }
        publish();
      }
    } finally {
      state.busy = false;
      if (state.desired === state.confirmed) state.desired = null;
      publish();
    }
  };
  refresh();
  const timer = window.setInterval(refresh, 5000);
  window.addEventListener?.('online', refresh);
  window.addEventListener?.('focus', refresh);
  return {
    on: () => state.confirmed === true,
    options: [
      { type: 'choice', key: 'power', label: 'Plugin',
        value: () => state.confirmed === null || state.uncertain ? '' : state.confirmed ? 'on' : 'off',
        disabled: () => state.busy,
        choices: () => [...(state.confirmed === null || state.uncertain ? [{ value: '', label: state.uncertain ? 'État du serveur inconnu' : 'Vérification…' }] : []),
          { value: 'on', label: 'Activé' }, { value: 'off', label: 'Désactivé' }] },
      { type: 'status', label: 'Contrôle du plugin',
        visible: () => state.busy || state.confirmed === null || state.uncertain || Boolean(state.error),
        value: () => state.busy ? `${text(state.desired ? 'Activation demandée…' : 'Arrêt demandé…')} · ${confirmedText()}`
          : state.error ? `${state.error} · ${confirmedText()}` : confirmedText(),
        button: () => state.error ? { label: 'Vérifier', run: () => { state.commandError = false; return refresh(); } } : null },
    ],
    onSetting: (key, value) => {
      if (key !== 'power') return;
      state.revision += 1; state.desired = value !== 'off'; state.error = ''; state.commandError = false; state.awaiting = null;
      send();
    },
    dispose: () => {
      state.disposed = true; window.clearInterval(timer);
      window.removeEventListener?.('online', refresh); window.removeEventListener?.('focus', refresh);
    },
  };
}
