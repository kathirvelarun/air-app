import test from 'node:test';
import assert from 'node:assert/strict';
import { liveScenarios, liveIncidentRow, liveAlertRow, severityBadge, formatElapsed } from '../src/data/liveScenarios.ts';

test('three live scenarios are configured with distinct incidents and repository/window fields', () => {
  assert.equal(liveScenarios.length, 3);
  assert.equal(new Set(liveScenarios.map(s => s.request.incident.incident_id)).size, 3);
  for (const s of liveScenarios) {
    assert.equal(s.request.repository, 'org/air-services');
    assert.equal(s.request.start_time, '2026-08-29T14:00:00Z');
    assert.equal(s.request.end_time, '2026-08-29T16:00:00Z');
  }
});

test('ledger scenario carries the required_metrics list for disk usage', () => {
  const ledger = liveScenarios.find(s => s.service === 'ledger-service');
  assert.ok(ledger);
  assert.deepEqual(ledger.request.required_metrics, ['cpu_pct', 'memory_pct', 'http_5xx_rate', 'p95_latency_ms', 'disk_usage_pct']);
});

test('live incidents and alerts start life Acknowledged and carry through status changes', () => {
  const scenario = liveScenarios[0];
  const row = liveIncidentRow(scenario, 'Acknowledged', '—');
  assert.equal(row.status, 'Acknowledged');
  assert.equal(row.id, scenario.key);
  const investigated = liveIncidentRow(scenario, 'Investigated', '12s');
  assert.equal(investigated.status, 'Investigated');
  assert.equal(investigated.duration, '12s');
  const alert = liveAlertRow(scenario, 'Acknowledged');
  assert.equal(alert.status, 'Acknowledged');
  assert.equal(alert.incidentId, scenario.key);
  assert.equal(alert.occurrences.length, 1);
});

test('severity maps CRITICAL and HIGH onto the existing SEV badge scale', () => {
  assert.equal(severityBadge('CRITICAL'), 'SEV 1');
  assert.equal(severityBadge('HIGH'), 'SEV 2');
});

test('elapsed duration formats as minutes and seconds, or seconds alone', () => {
  assert.equal(formatElapsed(45000), '45s');
  assert.equal(formatElapsed(75000), '1m 15s');
  assert.equal(formatElapsed(0), '0s');
});