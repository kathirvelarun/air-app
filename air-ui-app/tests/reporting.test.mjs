import test from 'node:test';
import assert from 'node:assert/strict';
import { canManage, reportRows, groupReport, csvCell } from '../src/utils/access.ts';
import { incidentRows } from '../src/data/incidents.ts';
test('only commander has configuration and analytics privileges',()=>{assert.equal(canManage('SRE Engineer'),false);assert.equal(canManage('Incident Commander'),true);});
test('date filtering includes the entire UTC end date',()=>{const rows=reportRows(incidentRows,'All','All','2026-09-07','2026-09-07');assert.equal(rows.length,3);assert.ok(rows.every(r=>r.openedAt.startsWith('2026-09-07')));});
test('system, status and dates compose; inverted dates return no records',()=>{assert.equal(reportRows(incidentRows,'inventory-api','Resolved','2026-09-06','2026-09-07').length,1);assert.equal(reportRows(incidentRows,'checkout-api','Resolved','','').length,0);assert.equal(reportRows(incidentRows,'All','All','2026-09-08','2026-09-07').length,0);});
test('grouped totals reconcile with matching incidents',()=>{for(const field of ['System','Status','Date']){const groups=groupReport(incidentRows,field);assert.equal(groups.reduce((n,g)=>n+g.total,0),4);assert.equal(groups.reduce((n,g)=>n+g.resolved,0),1);assert.ok(groups.every(g=>g.open+g.resolved===g.total));}});
test('CSV escapes quotes and neutralizes formula prefixes',()=>{assert.equal(csvCell('A "test"'),'"A ""test"""');assert.equal(csvCell('=1+1'),'"\'=1+1"');});
