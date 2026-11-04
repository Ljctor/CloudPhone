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
