// Coalesce consumers of the fast, read-only screen classification. Numeric
// readers are not involved; concurrent overlay/debug requests share one call.
const cached = new WeakMap();
// Gateway wall time can differ from the browser's. Age the received
// classification on this browser's monotonic clock. The server's age
// already includes capture/processing time; add elapsed time after receipt.
const observed = new WeakMap();
export function screenObservationAge(scan, now = performance.now() / 1000) {
  const observation = scan && observed.get(scan);
  return observation ? observation.age + now - observation.started : null;
}
export function getScreen(api) {
  let state = cached.get(api);
  if (!state) { state = { at: 0, value: null, pending: null, observations: new Map() }; cached.set(api, state); }
  if (state.pending) return state.pending;
  if (state.value && Date.now() - state.at < 250) return Promise.resolve(state.value);
  const started = performance.now() / 1000;
  state.pending = Promise.resolve().then(() => api.get('/screen?quick=1')).then((value) => {
    if (Number.isFinite(value?.scan?.at)) {
      const received = performance.now() / 1000;
      // A cached response carrying the same source timestamp does not renew
      // its lifetime, even when fetch parsed a new JavaScript object.
      if (!state.observations.has(value.scan.at)) state.observations.set(value.scan.at, started);
      if (state.observations.size > 32) state.observations.delete(state.observations.keys().next().value);
      const age = Object.hasOwn(value.scan, 'age') ? value.scan.age : 0;
      observed.set(value.scan, {
        age: Number.isFinite(age) && age >= 0 && received - started <= 2 ? age : Infinity,
        started: Object.hasOwn(value.scan, 'age') ? received : state.observations.get(value.scan.at),
      });
    }
    state.value = value;
    state.at = Date.now();
    return value;
  }).finally(() => { state.pending = null; });
  return state.pending;
}
