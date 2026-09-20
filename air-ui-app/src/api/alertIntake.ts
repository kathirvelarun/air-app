import type { LiveScenario } from '../types/investigation';
export type IntakeAlert = { eventId: string; source: string; summary: string; description: string; rule: string; observedAt: string; receivedAt: string; severity: 'HIGH' | 'CRITICAL' | 'MEDIUM' | 'LOW'; service: string; environment: string };
export type IntakeIncident = { id: string; uuid: string; title: string; service: string; environment: string; rule: string; severity: IntakeAlert['severity']; description: string; owner: string; repository: string; observedAt: string; openedAt: string; updatedAt: string; slackChannel: string; alertCount: number; alerts: IntakeAlert[]; requiredMetrics: string[] };
export async function fetchChannel(signal: AbortSignal): Promise<IntakeIncident[]> {
  const response = await fetch('/api/v1/channel', { signal });
  if (!response.ok) throw new Error('Alert intake is unavailable. Start the intake API on port 8001.');
  return (await response.json()).incidents;
}
export function toScenario(i: IntakeIncident): LiveScenario {
  const start = new Date(Date.parse(i.observedAt) - 20 * 60 * 1000).toISOString();
  const end = new Date(Date.parse(i.observedAt) + 100 * 60 * 1000).toISOString();
  return { key: i.id, title: i.title, service: i.service, owner: i.owner, slackChannel: i.slackChannel, alertSource: [...new Set(i.alerts.map(a => a.source))].join(', '), request: { incident: { incident_id: i.uuid, title: i.title, description: i.description, severity: i.severity, detected_at: i.observedAt, service_name: i.service, environment: i.environment }, repository: i.repository, start_time: start, end_time: end, ...(i.requiredMetrics.length ? {required_metrics: i.requiredMetrics} : {}) } };
}
