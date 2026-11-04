import assert from 'node:assert/strict';
import oralFeedback, { secureRecordingUrl } from './page_oral_feedback.js';
class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.attrs = {}; this.style = {}; this.hidden = false; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; if (name === 'src') this.src = ''; }
  append(...items) { this.children.push(...items); }
  pause() {}
}
globalThis.document = { createElement: (tag) => new Element(tag) };
globalThis.location = { href: 'http://phone.example:7890/#node=screen%3Abattle', port: '7890', pathname: '/' };
globalThis.isSecureContext = true;
let stopped = 0;
const media = () => ({ getTracks: () => [{ stop: () => stopped++ }] });
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia: async () => media() } } });
class Recorder {
  static isTypeSupported(mime) { return mime.startsWith('audio/webm'); }
  constructor(stream, options) { this.state = 'inactive'; this.mimeType = options?.mimeType ?? 'audio/webm'; }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['fake audio'], { type: this.mimeType }) }); this.onstop?.(); }
}
globalThis.MediaRecorder = Recorder;
const flush = () => new Promise((resolve) => setImmediate(resolve));
const click = (element) => element.onclick({ preventDefault() {}, stopPropagation() {} });
const control = (ui, name) => ui.element.children.find((node) => node.attrs['data-oral-control'] === name);
const status = (ui) => ui.element.children.find((node) => node.attrs.role === 'status');
const preview = (ui) => ui.element.children.find((node) => node.tagName === 'audio');
let captureCount = 0, creates = [], attached = [];
const context = { capture: { base64: 'start-frame' }, overlay: { state: { name: 'start-overlay' } } };
const ui = oralFeedback({ capture: () => { captureCount++; return context; }, transport: {
  create: async (value) => { creates.push(value); return { id: 'same-context', contextSha256: 'hash' }; },
  attach: async (saved, blob) => { attached.push({ saved, blob }); },
} });
click(control(ui, 'record')); await flush();
assert.equal(control(ui, 'record').textContent, 'Arrêter');
assert.equal(captureCount, 1); assert.equal(creates.length, 0);
assert.match(status(ui).textContent, /REC/);
context.capture.base64 = 'newer-frame'; context.overlay.state.name = 'newer-overlay';
click(control(ui, 'record')); await flush();
assert.equal(preview(ui).hidden, false); assert.ok(preview(ui).src.startsWith('blob:'));
assert.equal(control(ui, 'send').hidden, false); assert.equal(creates.length, 0, 'Stop never sends feedback');
assert.equal(stopped, 1, 'the microphone closes before replay');
click(control(ui, 'send')); await flush();
assert.equal(creates.length, 1); assert.equal(attached.length, 1); assert.ok(attached[0].blob.size > 0);
assert.equal(creates[0].capture.base64, 'start-frame');
assert.equal(creates[0].overlay.state.name, 'start-overlay');
assert.equal(captureCount, 1, 'sending cannot replace the recording-time capture');
assert.equal(preview(ui).hidden, true); assert.match(status(ui).textContent, /Retour vocal enregistré/); ui.dispose();

// Cancelling permission creates neither evidence nor an audio upload. A late
// microphone result is closed, never allowed to start a recording afterwards.
let allow;
navigator.mediaDevices.getUserMedia = () => new Promise((resolve) => { allow = resolve; });
let canceledCaptures = 0;
const canceled = oralFeedback({ capture: () => { canceledCaptures++; return context; }, transport: {
  create: () => assert.fail('cancelled recording cannot send evidence'), attach: () => assert.fail('cancelled audio cannot upload'),
} });
click(control(canceled, 'record')); click(control(canceled, 'cancel')); allow(media()); await flush();
assert.equal(canceledCaptures, 0); assert.equal(stopped, 2); assert.equal(control(canceled, 'send').hidden, true); canceled.dispose();

// Retrying the upload keeps the original audio/context and does not recapture.
navigator.mediaDevices.getUserMedia = async () => media();
let retries = 0, saved = 0, retryCaptures = 0;
const retry = oralFeedback({ capture: () => { retryCaptures++; return context; }, transport: {
  create: async () => { saved++; return { id: 'retry-context' }; },
  attach: async (value) => { assert.equal(value.id, 'retry-context'); if (++retries === 1) throw Error('upload unavailable'); },
} });
click(control(retry, 'record')); await flush(); click(control(retry, 'record')); await flush();
click(control(retry, 'send')); await flush(); assert.match(status(retry).textContent, /upload unavailable/);
assert.equal(preview(retry).hidden, false); assert.equal(control(retry, 'send').hidden, false);
click(control(retry, 'send')); await flush(); assert.equal(saved, 1); assert.equal(retries, 2); assert.equal(retryCaptures, 1); retry.dispose();

// HTTP gives a truthful link to the existing HTTPS review interface, never a
// file picker or an external recorder, and never pretends recording has begun.
globalThis.isSecureContext = false;
let insecureCapture = 0;
const insecure = oralFeedback({ capture: () => { insecureCapture++; }, transport: {}, secureReviewUrl: 'https://configured.example/navigation-review/' });
await flush();
assert.equal(secureRecordingUrl('https://configured.example/navigation-review/'), 'https://configured.example/navigation-review/#node=screen%3Abattle');
assert.equal(insecure.element.children.some((node) => node.tagName === 'input'), false);
assert.equal(control(insecure, 'record').disabled, true); click(control(insecure, 'record'));
assert.equal(insecureCapture, 0); assert.match(status(insecure).textContent, /HTTPS/);
assert.equal(insecure.element.children.find((node) => node.tagName === 'a').hidden, false); insecure.dispose();
const unavailable = oralFeedback({ capture: () => assert.fail('no configured HTTPS'), transport: {}, secureReviewUrl: null });
await flush();
assert.equal(unavailable.element.children.find((node) => node.tagName === 'a').hidden, true);
assert.match(status(unavailable).textContent, /aucune origine HTTPS configurée/);
assert.equal(secureRecordingUrl(), null);
for (const candidate of ['http://configured.example/navigation-review/', 'https://user:password@configured.example/navigation-review/', 'https://configured.example/other/']) assert.equal(secureRecordingUrl(candidate), null);
unavailable.dispose();
console.log('Direct voice recording: immutable start frame, explicit send/replay/cancel, retry and truthful HTTPS fallback: OK');
