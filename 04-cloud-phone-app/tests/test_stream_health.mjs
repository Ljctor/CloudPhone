import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const dir = new URL('../src/overlay/js/example/src/', import.meta.url);
const source = readFileSync(new URL('streamHealth.ts', dir), 'utf8');
const { mediaStall, resetMediaWindow } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const sample = (time, extra = {}) => ({ time, visible: true, connected: true, paused: false,
  framesReceived: 10, framesDecoded: 10, presented: 10, bytesReceived: 1000, packetsReceived: 100, ...extra });
function run(kind, overrides = () => ({})) {
  let memory, result;
  for (let i = 0; i <= 25; i++) {
    const progress = i <= 5 || kind === 'healthy';
    const frame = sample(i * 1000, {
      framesReceived: 10 + (kind === 'static' ? Math.min(i, 5) : i),
      framesDecoded: 10 + (progress || kind === 'presentation' ? i : Math.min(i, 5)),
      presented: 10 + (progress ? i : 5),
      bytesReceived: 1000 + i * 100, packetsReceived: 100 + i,
      ...overrides(i),
    });
    result = mediaStall(memory, frame); memory = result.state;
  }
  return result;
}
assert.equal(run('healthy').evidence, null);
let staticMemory;
for (let i = 0; i < 650; i++) {
  // Real presentation progress first, then ten minutes static, then a burst
  // of three received frames with delayed decoding. No elapsed static debt.
  const frame = sample(i * 1000, { framesReceived: 10 + Math.min(i, 5) + (i >= 605 ? 3 : 0),
    framesDecoded: 10 + Math.min(i, 5), presented: 10 + Math.min(i, 5),
    bytesReceived: 1000 + i * 100, packetsReceived: 100 + i });
  const result = mediaStall(staticMemory, frame); staticMemory = result.state;
  assert.equal(result.evidence, null, 'long static then small burst cannot reconnect');
}

assert.equal(run('static').evidence, null, 'static Android plus packet/byte traffic alone is not a frozen decoder');
assert.equal(run('decode').evidence.state, 'decode-stalled');
assert.equal(run('presentation').evidence.state, 'presentation-stalled');
assert.equal(run('decode', () => ({ visible: false })).evidence, null);
assert.equal(run('decode', () => ({ paused: true })).evidence, null);
assert.equal(run('decode', () => ({ connected: false })).evidence, null);
assert.equal(run('decode', () => ({ packetsReceived: null })).evidence, null);
assert.equal(run('presentation', () => ({ presented: 0 })).evidence, null, 'quality counter stuck at zero is not presentation evidence');
assert.equal(run('decode', (i) => ({ framesReceived: 10 + Math.min(i, 5) + (i > 20 ? 1 : 0) })).evidence, null,
  'one arriving frame in a long window is insufficient');
assert.equal(run('healthy', (i) => ({ framesReceived: 10 + Math.floor(i / 4),
  framesDecoded: 10 + Math.floor(i / 4), presented: 10 + Math.floor(i / 4) })).evidence, null, 'low FPS progressing video stays connected');
let memory = run('decode').state;
for (const frame of [sample(26000, { visible: false }), sample(27000), sample(28000)]) {
  const result = mediaStall(memory, frame); assert.equal(result.evidence, null); memory = result.state;
}
assert.equal(mediaStall(run('decode').state, sample(50000)).evidence, null, 'large sampling gap resets evidence');
// Exact incident: presentation worked before background, then never progresses
// after resume while independent arriving media continues on the same peer/video.
let resumed = resetMediaWindow(run('healthy').state), resumeResult;
for (let i = 0; i <= 25; i++) {
  resumeResult = mediaStall(resumed, sample(60000 + i * 1000, {
    framesReceived: 40 + i, framesDecoded: 35, presented: 35,
    bytesReceived: 5000 + i * 100, packetsReceived: 500 + i,
  }));
  resumed = resumeResult.state;
  if (i < 19) assert.equal(resumeResult.evidence, null, 'resume has a fresh grace and evidence window');
}
assert.equal(resumeResult.evidence?.state, 'decode-stalled', 'same-video counter proof survives background freeze');
let replaced, replacementResult;
for (let i = 0; i <= 25; i++) {
  replacementResult = mediaStall(replaced, sample(60000 + i * 1000, {
    framesReceived: 40 + i, framesDecoded: 35, presented: 35,
    bytesReceived: 5000 + i * 100, packetsReceived: 500 + i,
  })); replaced = replacementResult.state;
}
assert.equal(replacementResult.evidence, null, 'new connection/video must establish its own reliable presentation counter');

assert.equal(mediaStall(run('decode').state, sample(26000, { framesDecoded: 0 })).evidence, null, 'counter reset invalidates evidence');

// Exercise the actual useStream callback and reconnect path with inert React
// primitives; no server, WebRTC stream, reset request or browser is contacted.
let hook = readFileSync(new URL('useStream.ts', dir), 'utf8')
  .replace(/import[\s\S]*?from ['"][^'"]+['"];\n/g, '').replace('export function useStream', 'function useStream');
function harness(healthy = true) {
  let now = 0, active = {}, disconnected = 0;
  const posts = [], diagnostics = [], timers = new Map(); let next = 0;
  const context = { useRef: (current) => ({ current }), useState: (initial) => [initial, () => {}], useEffect: () => {},
    document: { hidden: false, visibilityState: 'visible' }, performance: { now: () => now },
    activePeerConnection: () => active, disconnectActiveStream: () => { disconnected++; },
    postFetch: async (...args) => { posts.push(args); return { ok: true }; }, postHeaders: () => ({}), VIEWER_ID: 'this-viewer',
    streamDiagnostic: (...args) => diagnostics.push(args), english: (s) => s, pageLog() {},
    serverHealthy: (server) => healthy, MEDIA_RECONNECT_COOLDOWN_MS: 60000,
    AUTO_RECONNECT_DELAY_MS: 2000, RECONNECT_FEEDBACK_MS: 45000, REMOUNT_DELAY_MS: 1000, STUCK_AFTER_S: 20,
    autoReconnectDue: () => false, secondsSince: () => 0, streamStateLine: () => ['state'], AbortController,
    window: { setTimeout: (fn, delay) => { const id = ++next; timers.set(id, { fn, delay }); return id; },
      clearTimeout: (id) => timers.delete(id) },
  };
  vm.createContext(context);
  const stream = vm.runInContext(hook + '\nuseStream({server:{connection:"reachable",value:{}},input:{pointerDown:{current:false}}})', context);
  stream.handleState('connected', 0);
  const evidence = run('decode').evidence;
  return { stream, posts, diagnostics, context, proof: (generation = 0, connection = active) => ({ generation, connection, evidence }),
    time: (value) => { now = value; }, disconnected: () => disconnected,
    remount: () => { const timer = [...timers.values()].find((t) => t.delay === 1000); assert.ok(timer); timer.fn(); } };
}
const h = harness();
h.stream.recoverMediaStall(h.proof(1));
h.stream.recoverMediaStall(h.proof(0, {}));
h.context.document.hidden = true; h.stream.recoverMediaStall(h.proof()); h.context.document.hidden = false;
assert.equal(h.posts.length, 0, 'stale generation/foreign peer/hidden page cannot reconnect');
h.stream.recoverMediaStall(h.proof()); await new Promise(setImmediate);
assert.equal(h.posts.length, 1);
assert.equal(h.posts[0][0], '/api/v1/stream/reset');
assert.deepEqual(JSON.parse(h.posts[0][1].body), { viewer: 'this-viewer' });
assert.equal(h.disconnected(), 1);
h.remount(); h.stream.handleState('connected', 1);
h.time(30000); h.stream.recoverMediaStall(h.proof(1)); assert.equal(h.posts.length, 1, 'cooldown survives remount');
h.time(61000); h.stream.recoverMediaStall(h.proof(1)); await new Promise(setImmediate); assert.equal(h.posts.length, 2);
const unhealthy = harness(false); unhealthy.stream.recoverMediaStall(unhealthy.proof()); assert.equal(unhealthy.posts.length, 0);
console.log('Foreground media evidence, static/low-FPS exclusions, stale peers, viewer reset and cooldown: OK');
