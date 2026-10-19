// The stream's statistics as numbers, from the browser's WebRTC report and
// two samples a second apart. No React, no DOM.

// The page samples the stream once a second (useStreamStats.ts):
// - ping: ICE round-trip time when the browser reports it, otherwise the time
//   of an HTTP request to the gateway (same network path);
// - server: video frames received from the emulator per second;
// - phone: frames this browser actually displayed per second;
// - network details for the connectivity panel.
// Frame rates are 0 while the Android screen does not change: the emulator
// sends a frame only when something moves.
export const EMPTY_STATS = {
  ping: null, pingSource: null, server: null, phone: null, video: null,
  bitrate: null, packetsLost: null, jitter: null, bufferDelay: null,
  framesDropped: null, codec: null, path: null, connection: null,
};

// What one sample reads: frames and bytes received, the ICE round trip
// (ms) when the browser reports one, and the details for the panel.
export function emptySample() {
  return { received: null, bytes: null, ping: null, details: {} };
}

// Reads a getStats() report (anything with forEach over its entries) into
// sampleData, as it goes.
export function readReport(report, connectionState, sampleData) {
  const byId = new Map();
  report.forEach((entry) => byId.set(entry.id, entry));
  report.forEach((entry) => {
    if (entry.type === 'inbound-rtp' && (entry.kind ?? entry.mediaType) === 'video') {
      sampleData.received = entry.framesReceived ?? entry.framesDecoded ?? null;
      sampleData.bytes = entry.bytesReceived ?? null;
      sampleData.details.packetsLost = entry.packetsLost ?? null;
      sampleData.details.jitter = typeof entry.jitter === 'number' ? entry.jitter * 1000 : null;
      sampleData.details.framesDropped = entry.framesDropped ?? null;
      if (entry.jitterBufferEmittedCount) {
        sampleData.details.bufferDelay = entry.jitterBufferDelay / entry.jitterBufferEmittedCount * 1000;
      }
      sampleData.details.codec = byId.get(entry.codecId)?.mimeType?.replace('video/', '') ?? null;
    } else if (entry.type === 'candidate-pair' && entry.state === 'succeeded'
      && (entry.nominated || entry.selected)) {
      if (typeof entry.currentRoundTripTime === 'number') {
        sampleData.ping = entry.currentRoundTripTime * 1000;
      }
      const local = byId.get(entry.localCandidateId);
      const remote = byId.get(entry.remoteCandidateId);
      if (local && remote) {
        sampleData.details.path = `${local.candidateType ?? '?'} → ${remote.candidateType ?? '?'} (${(local.protocol ?? '?').toUpperCase()})`;
      }
    }
  });
  sampleData.details.connection = connectionState;
  return sampleData;
}

// The statistics shown, from the previous sample (null for the first) and
// this one: { time (ms), received, shown, bytes }, the counters so far.
// values: what is shown as read (details, ping, pingSource, video).
export function statsFrom(previous, current, values) {
  const rate = (now, before, seconds) => (
    now !== null && before !== null && now >= before ? (now - before) / seconds : null);
  const seconds = previous ? (current.time - previous.time) / 1000 : 0;
  return {
    ...EMPTY_STATS,
    ...values,
    server: previous ? rate(current.received, previous.received, seconds) : null,
    phone: previous ? rate(current.shown, previous.shown, seconds) : null,
    bitrate: previous && rate(current.bytes, previous.bytes, seconds) !== null
      ? rate(current.bytes, previous.bytes, seconds) * 8 / 1000 : null,
  };
}
