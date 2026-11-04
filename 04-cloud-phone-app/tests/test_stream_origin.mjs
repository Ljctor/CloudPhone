// Evaluate the actual App URI binding, without connecting to any server.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../src/overlay/js/example/src/App.tsx', import.meta.url), 'utf8');
const bindings = ['gateway', 'gatewayUrl'].map((name) => {
  const declaration = source.match(new RegExp(`const ${name} = [^;]+;`));
  assert.ok(declaration, `App gateway declaration missing: ${name}`);
  return declaration[0];
}).join('\n');
const uri = source.match(/<Emulator\b[\s\S]*?\buri=\{([^}]+)\}/)?.[1];
assert.ok(uri, 'Actual Emulator URI binding is required');
for (const page of ['http://127.0.0.1:8100/', 'https://phone.example/', 'https://phone.example:8443/']) {
  const location = new URL(page);
  const props = vm.runInNewContext(`${bindings}\n({uri: ${uri}})`, { window: { location } });
  assert.equal(props.uri, location.origin, `${page}: rendered URI must preserve scheme and explicit port`);
  // SDK getUrls: absent scheme defaults to http, then http(s) becomes ws(s).
  const sdkBase = /^https?:\/\//i.test(props.uri) ? props.uri : `http://${props.uri}`;
  assert.equal(sdkBase.replace(/^http/i, 'ws') + '/api/v1/emulator/ws-jsep',
    `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/emulator/ws-jsep`);
}
console.log('Actual Emulator URI binding preserves HTTP/HTTPS and explicit ports: OK');
