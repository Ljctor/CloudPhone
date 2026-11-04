import assert from 'node:assert/strict';
import { matchGesture, battlefieldLabel, screenLabel } from './model.js';
const tap = { id: 'tap', kind: 'tap', from: 'before', to: 'after', start: { x: .5, y: .5 } };
const swipe = { id: 'slide', kind: 'swipe', from: 'before', to: 'lower',
  start: { x: .5, y: .7 }, end: { x: .5, y: .3 } };
const drag = { ...swipe, id: 'drag', annotationKind: 'draggable', to: 'placed' };
assert.deepEqual(matchGesture([tap, swipe], { start: swipe.start, end: swipe.end, duration: 800 }).matches, [swipe]);
assert.equal(matchGesture([swipe], { start: swipe.start, end: { x: .5, y: .9 }, duration: 800 }).matches.length, 0);
assert.equal(matchGesture([swipe], { start: swipe.start, duration: 80 }).matches.length, 0);
assert.deepEqual(matchGesture([drag], { start: drag.start, end: drag.end, duration: 800 }).matches, [drag]);
assert.equal(matchGesture([tap], { start: tap.start, duration: 80 }, [{ kind: 'forbidden', rect: [.4, .4, .6, .6] }]).forbidden, true);
assert.equal(matchGesture([tap, { ...tap, id: 'alternative', to: 'other' }], { start: tap.start, duration: 80 }).matches.length, 2);
assert.equal(matchGesture([{ ...tap, annotationKind: 'action' }], { start: tap.start, duration: 80 }).matches.length, 0);
assert.equal(matchGesture([tap], { start: { x: NaN, y: .5 }, duration: 80 }).matches.length, 0);
assert.equal(screenLabel({ screen: 'battle', scan: { plain: false } }), 'Vue avec combat');
assert.equal(screenLabel({ screen: 'battle', scan: { plain: true } }), 'Combat Interface');
assert.equal(battlefieldLabel({ battleViewport: { size: 'small' } }), 'Petit');
console.log('Recorded gesture matching, ambiguity, forbidden zones and distinct screen/battlefield labels: OK');

const {zoneStyle} = await import('../page_zone_style.js');
assert.equal(zoneStyle({kind:'detection'}).dash, 'none');
assert.equal(zoneStyle({user:true}).dash, '1 5');
assert.equal(zoneStyle({conditional:true}).double, true);
assert.equal(zoneStyle({proposal:'remove',user:true}).dash, '10 7');
assert.equal(zoneStyle({proposal:'remove',user:true}).opacity, .28);
assert.equal(matchGesture([tap], {start:tap.start,duration:80}, [{kind:'forbidden',user:true,source:'user_feedback',proposal:'add',rect:[.4,.4,.6,.6]}]).matches.length,1);
console.log('Shared proposal styling and no gesture policy changes: OK');

const {reviewGesture} = await import('./model.js');
const wholeButton = {kind:'navigation',rect:[.1,.4,.9,.6]};
assert.equal(reviewGesture([tap],{start:{x:.11,y:.5},duration:50},[wholeButton]).matches[0],tap,
  'whole navigation rectangles work beyond the recorded centre');
assert.equal(reviewGesture([tap],{start:tap.start,duration:50},[wholeButton,{kind:'action',rect:[.4,.4,.6,.6]}]).kind,'action');
assert.equal(reviewGesture([tap],{start:tap.start,duration:50},[
  wholeButton,{kind:'action',rect:[.4,.4,.6,.6]},{kind:'forbidden',user:true,rect:[.4,.4,.6,.6]}]).kind,'forbidden');
assert.equal(reviewGesture([{...tap,annotationKind:'action'}],{start:tap.start,duration:50},[]).kind,'action');
assert.equal(reviewGesture([swipe],{start:swipe.start,end:swipe.end,duration:800},[]).matches[0],swipe);
assert.equal(reviewGesture([drag],{start:drag.start,end:drag.end,duration:800},[]).matches[0],drag);
console.log('Inert phone: forbidden/action priority, whole navigation hotspots and recorded slides/drags: OK');

for (const kind of ['progression_value', 'resource_value', 'screen_identifier']) {
  const roleEdge = { ...tap, annotationKind: kind };
  assert.equal(matchGesture([roleEdge], { start: tap.start, duration: 80 }).matches.length, 0);
  assert.equal(reviewGesture([roleEdge], { start: tap.start, duration: 80 }, [{ kind, rect: [.4,.4,.6,.6] }]).matches.length, 0);
}
console.log('Value and identifier annotations never become navigation edges: OK');

const {servicePath} = await import('./model.js');
for (const prefix of ['/', '/navigation-review/']) {
  const moduleUrl = `https://review.example${prefix}app.js`;
  for (const path of ['/api/graph', '/api/image/example:battle', '/api/recording-config', '/api/oral-feedback', '/api/zone-feedback'])
    assert.equal(servicePath(path, moduleUrl), prefix + path.slice(1));
}
assert.throws(() => servicePath('/api/../../outside', 'https://review.example/navigation-review/app.js'));
console.log('Review service API, image and recording URLs preserve the HTTPS proxy mount: OK');
