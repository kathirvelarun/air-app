import test from 'node:test';
import assert from 'node:assert/strict';
import {leadershipMetrics} from '../src/data/leadership.ts';
const rows=[{id:'a',service:'x',status:'Resolved',openedAt:'2026-08-31T10:00:00Z',resolvedAt:'2026-09-02T10:00:00Z'},{id:'b',service:'x',status:'Investigating',openedAt:'2026-09-01T10:00:00Z',resolvedAt:null}];
test('clearance includes older incidents and backlog reconciles',()=>{const m=leadershipMetrics(rows,'2026-09-01','2026-09-03');assert.equal(m.opened,1);assert.equal(m.cleared,1);assert.equal(m.backlogStart,1);assert.equal(m.backlogEnd,1);assert.equal(m.backlogStart+m.opened-m.cleared,m.backlogEnd);assert.equal(m.clearanceRate,0);assert.equal(m.meanMinutes,2880);});
test('empty cohort has no misleading clearance percentage or resolution time',()=>{const m=leadershipMetrics([],'2026-09-01','2026-09-03');assert.equal(m.clearanceRate,null);assert.equal(m.meanMinutes,null);assert.equal(m.days.length,3);assert.ok(m.days.every(d=>d.backlog===0));});
test('invalid and excessive ranges are rejected',()=>{assert.equal(leadershipMetrics(rows,'2026-09-04','2026-09-03'),null);assert.equal(leadershipMetrics(rows,'2026-01-01','2026-09-03'),null);});
