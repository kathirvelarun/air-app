import test from 'node:test';
import assert from 'node:assert/strict';
import { readInvestigation, publishInvestigation, subscribeInvestigations } from '../src/utils/investigationSync.ts';

test('investigation updates survive reload, notify listeners, and isolate incident UUIDs', () => {
  const records = new Map();
  globalThis.localStorage = { getItem: key => records.get(key) ?? null, setItem: (key, value) => records.set(key, value) };
  globalThis.window = new EventTarget();
  let calls = 0;
  const unsubscribe = subscribeInvestigations(() => calls++);
  publishInvestigation({ uuid: 'first-uuid', status: 'Investigating', startedAt: 100 });
  assert.equal(calls, 1);
  assert.equal(readInvestigation('first-uuid').status, 'Investigating');
  assert.equal(readInvestigation('new-uuid-with-reused-incident-number'), null);
  const result = { status: 'COMPLETED', rca: { key_findings: [{ finding: 'Config changed' }] } };
  publishInvestigation({ uuid: 'first-uuid', status: 'Investigated', startedAt: 100, finishedAt: 200, result });
  assert.deepEqual(readInvestigation('first-uuid').result, result);
  const storage = new Event('storage');
  Object.defineProperty(storage, 'key', { value: 'air.investigation.v1.first-uuid' });
  window.dispatchEvent(storage);
  assert.equal(calls, 3);
  unsubscribe();
  window.dispatchEvent(storage);
  assert.equal(calls, 3);
  records.set('air.investigation.v1.first-uuid', '{bad json');
  assert.equal(readInvestigation('first-uuid'), null);
});

test('unavailable browser storage fails explicitly instead of claiming synchronization', () => {
  globalThis.localStorage = { setItem: () => { throw new Error('storage blocked'); }, getItem: () => { throw new Error('storage blocked'); } };
  assert.equal(readInvestigation('id'), null);
  assert.throws(() => publishInvestigation({ uuid: 'id', status: 'Investigating', startedAt: 100 }), /storage blocked/);
});
