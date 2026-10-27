// Coalesce consumers of the fast, read-only screen classification. Numeric
// readers are not involved; concurrent overlay/debug requests share one call.
const cached = new WeakMap();
export function getScreen(api) {
  let state = cached.get(api);
  if (!state) { state = { at: 0, value: null, pending: null }; cached.set(api, state); }
  if (state.pending) return state.pending;
  if (state.value && Date.now() - state.at < 250) return Promise.resolve(state.value);
  state.pending = Promise.resolve().then(() => api.get('/screen?quick=1')).then((value) => {
    state.value = value;
    state.at = Date.now();
    return value;
  }).finally(() => { state.pending = null; });
  return state.pending;
}
