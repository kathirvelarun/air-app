import test from 'node:test';
import assert from 'node:assert/strict';
import { groupAlertEvents, alertEvents, filterRows } from '../src/data/incidents.ts';

test('similar alerts form four groups with all eight distinct occurrences',()=>{
 const groups=groupAlertEvents(alertEvents);
 assert.equal(groups.length,4);
 assert.deepEqual(groups.map(g=>g.occurrences.length),[2,2,3,1]);
 assert.equal(new Set(groups.flatMap(g=>g.occurrences.map(e=>e.eventId))).size,8);
 assert.ok(groups.every(g=>g.incidentId==='INC-2048'));
});
test('duplicate deliveries do not create extra parent or child rows',()=>{
 const groups=groupAlertEvents([...alertEvents,alertEvents[0],alertEvents[1]]);
 assert.equal(groups.length,4);
 assert.equal(groups.flatMap(g=>g.occurrences).length,8);
});
test('similar fingerprints across regions or incidents remain separate',()=>{
 const original=alertEvents[0];
 assert.equal(groupAlertEvents([original,{...original,eventId:'new-region',region:'eu-west-1'},{...original,eventId:'new-incident',incidentId:'INC-2100'}]).length,3);
});
test('searching for a child event or incident retains the correct parent',()=>{
 const groups=groupAlertEvents(alertEvents).map(g=>({...g,status:'Firing'}));
 assert.equal(filterRows(groups,'ALT-8108','All','All')[0].fingerprint,'checkout-p95');
 assert.equal(filterRows(groups,'INC-2048','All','All').length,4);
});
