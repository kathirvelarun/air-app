import test from 'node:test';
import assert from 'node:assert/strict';
import { filterRows, incidentRows } from '../src/data/incidents.ts';

test('combines severity and status without including unrelated incidents', () => {
 assert.deepEqual(filterRows(incidentRows,'','Declared','SEV 2').map(r=>r.id),['INC-2047']);
});
test('search matches IDs and services, ignoring case and whitespace', () => {
 assert.equal(filterRows(incidentRows,'  INC-2048  ','All','All')[0].service,'checkout-api');
 assert.equal(filterRows(incidentRows,'REFUND-WORKER','All','All')[0].id,'INC-2047');
});
test('unmatched and conflicting filters produce an empty result', () => {
 assert.deepEqual(filterRows(incidentRows,'missing','All','All'),[]);
 assert.deepEqual(filterRows(incidentRows,'checkout','Resolved','All'),[]);
});
test('recovered incident responds to the resolved filter without changing source data', () => {
 const recovered = incidentRows.map(r=>r.id==='INC-2048'?{...r,status:'Resolved'}:r);
 assert.equal(filterRows(recovered,'checkout','Resolved','All').length,1);
 assert.equal(incidentRows[0].status,'Investigating');
});
