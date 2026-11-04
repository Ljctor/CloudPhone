// Pure bounded media-stall evidence. Zero FPS alone is valid on static Android.
export const MEDIA_STALL_MS = 15000;
export const MEDIA_FOREGROUND_GRACE_MS = 5000;
export const MEDIA_SAMPLE_GAP_MS = 3000;
export const MEDIA_RECONNECT_COOLDOWN_MS = 60000;
const counters = ['framesReceived', 'framesDecoded', 'presented', 'bytesReceived', 'packetsReceived'];
const fresh = () => ({ last: null, foregroundSince: null, presentationProven: false, window: null });

export function resetMediaWindow(previous) {
  // Counter reliability belongs to this connection/video, not to a visible
  // interval. Keep the last counters to detect a reset when sampling resumes.
  return previous ? { ...previous, foregroundSince: null, window: null } : fresh();
}

export function mediaStall(previous, sample) {
  let state = previous ?? fresh();
  const valid = sample.visible && sample.connected && !sample.paused
    && counters.every((key) => Number.isFinite(sample[key]) && sample[key] >= 0);
  if (!valid) return { state: resetMediaWindow(state), evidence: null };
  const last = state.last;
  if (last && counters.some((key) => sample[key] < last[key])) {
    return { state: { ...fresh(), last: sample, foregroundSince: sample.time }, evidence: null };
  }
  if (!last || state.foregroundSince === null || sample.time <= last.time
      || sample.time - last.time > MEDIA_SAMPLE_GAP_MS) {
    return { state: { ...fresh(), presentationProven: state.presentationProven,
      last: sample, foregroundSince: sample.time }, evidence: null };
  }
  state = { ...state, last: sample,
    presentationProven: state.presentationProven || sample.presented > last.presented };
  if (sample.time - state.foregroundSince < MEDIA_FOREGROUND_GRACE_MS) {
    return { state, evidence: null };
  }
  // The presentation counter must previously have advanced on this connection.
  // Some browsers expose quality counters stuck at zero for live WebRTC.
  if (!state.presentationProven || sample.presented > last.presented) {
    return { state: { ...state, window: null }, evidence: null };
  }
  const kind = sample.framesDecoded > last.framesDecoded ? 'presentation-stalled' : 'decode-stalled';
  // A decoder that occasionally advances is slow, not frozen. Presentation
  // evidence may span decoded frames; decode evidence needs a constant decoder.
  const arrival = (sample.framesReceived > last.framesReceived || sample.framesDecoded > last.framesDecoded)
    && sample.bytesReceived > last.bytesReceived && sample.packetsReceived > last.packetsReceived;
  let window = state.window;
  if (window?.kind === 'decode-stalled' && sample.framesDecoded > last.framesDecoded) window = null;
  if (!window) {
    // Static time is never accumulated as decoder failure time. A small burst
    // after a long still screen starts a new window, with time to decode it.
    if (!arrival) return { state: { ...state, window: null }, evidence: null };
    window = { kind, start: last, arrivalSamples: 1, lastArrival: sample.time };
  } else if (arrival) {
    window = { ...window, arrivalSamples: window.arrivalSamples + 1, lastArrival: sample.time };
  }
  state.window = window;
  const elapsedMs = sample.time - window.start.time;
  const delta = Object.fromEntries(counters.map((key) => [key, sample[key] - window.start[key]]));
  // Require continuing media on separate samples, not one delayed packet/frame
  // burst followed by another legitimate static interval.
  const receiving = delta.bytesReceived > 0 && delta.packetsReceived > 0
    && window.arrivalSamples >= 3 && sample.time - window.lastArrival <= MEDIA_SAMPLE_GAP_MS;
  const decodeStuck = delta.framesDecoded === 0 && delta.framesReceived >= 3;
  const presentationStuck = delta.framesDecoded >= 3;
  const evidence = elapsedMs >= MEDIA_STALL_MS && receiving && delta.presented === 0
    && (decodeStuck || presentationStuck)
    ? { state: decodeStuck ? 'decode-stalled' : 'presentation-stalled', elapsedMs, ...delta } : null;
  return { state, evidence };
}
