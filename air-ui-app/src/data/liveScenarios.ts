import type { AlertEvent } from './incidents';
import type { LiveAlertRow, LiveIncidentRow, LiveScenario, LiveStatus, ApiSeverity } from '../types/investigation';

export const liveScenarios: LiveScenario[] = [
  {
    key: 'INC-9101',
    title: 'Payment errors spiking',
    service: 'payment-service',
    owner: 'Arunkumar',
    slackChannel: 'air-inc-9101',
    alertSource: 'Prometheus',
    request: {
      incident: {
        incident_id: '8e9c44cd-43ef-4a8e-ae4e-06b05714ca09',
        title: 'Payment errors spiking',
        description: 'payment-service error rate elevated in production',
        severity: 'HIGH',
        detected_at: '2026-08-29T14:20:00Z',
        service_name: 'payment-service',
        environment: 'production',
      },
      repository: 'org/air-services',
      start_time: '2026-08-29T14:00:00Z',
      end_time: '2026-08-29T16:00:00Z',
    },
  },
  {
    key: 'INC-9102',
    title: 'Checkout page failing to load order details',
    service: 'web-ui',
    owner: 'Ragul',
    slackChannel: 'air-inc-9102',
    alertSource: 'Sentry',
    request: {
      incident: {
        incident_id: '2b1c6a4e-9f3d-4c8a-8e2a-1a2b3c4d5e6f',
        title: 'Checkout page failing to load order details',
        description: 'web-ui is throwing response parsing errors when rendering the checkout page; users see a generic error instead of their order',
        severity: 'HIGH',
        detected_at: '2026-08-29T14:20:00Z',
        service_name: 'web-ui',
        environment: 'production',
      },
      repository: 'org/air-services',
      start_time: '2026-08-29T14:00:00Z',
      end_time: '2026-08-29T16:00:00Z',
    },
  },
  {
    key: 'INC-9103',
    title: 'Ledger writes failing',
    service: 'ledger-service',
    owner: 'Rajakumari',
    slackChannel: 'air-inc-9103',
    alertSource: 'Disk monitor',
    request: {
      incident: {
        incident_id: '7d4e5f6a-1b2c-4d3e-9f8a-2c3d4e5f6a7b',
        title: 'Ledger writes failing',
        description: 'ledger-service is failing to append entries to its write-ahead log; the underlying filesystem appears to be nearly full',
        severity: 'CRITICAL',
        detected_at: '2026-08-29T14:20:00Z',
        service_name: 'ledger-service',
        environment: 'production',
      },
      repository: 'org/air-services',
      start_time: '2026-08-29T14:00:00Z',
      end_time: '2026-08-29T16:00:00Z',
      required_metrics: ['cpu_pct', 'memory_pct', 'http_5xx_rate', 'p95_latency_ms', 'disk_usage_pct'],
    },
  },
];

export function severityBadge(severity: ApiSeverity): string {
  return severity === 'CRITICAL' ? 'SEV 1' : severity === 'HIGH' ? 'SEV 2' : 'SEV 3';
}

export function formatUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${months[d.getUTCMonth()]} ${d.getUTCDate()}, ${hh}:${mm} UTC`;
}

export function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds.toString().padStart(2, '0')}s` : `${seconds}s`;
}

export function liveIncidentRow(scenario: LiveScenario, status: LiveStatus, duration: string): LiveIncidentRow {
  return {
    id: scenario.key,
    openedAt: scenario.request.incident.detected_at,
    slackChannel: scenario.slackChannel,
    title: scenario.title,
    service: scenario.service,
    severity: severityBadge(scenario.request.incident.severity),
    status,
    time: formatUtc(scenario.request.incident.detected_at),
    duration,
    owner: scenario.owner,
    summary: scenario.request.incident.description,
  };
}

export function liveAlertRow(scenario: LiveScenario, status: LiveStatus): LiveAlertRow {
  const event: AlertEvent = {
    eventId: `${scenario.key}-ALT`,
    incidentId: scenario.key,
    fingerprint: scenario.key,
    title: scenario.title,
    source: scenario.alertSource,
    service: scenario.service,
    environment: 'Production',
    region: 'us-east-1',
    severity: severityBadge(scenario.request.incident.severity),
    observedAt: formatUtc(scenario.request.incident.detected_at),
    instance: `${scenario.service}-0`,
  };
  return { ...event, id: scenario.key, occurrences: [event], searchText: `${event.eventId} ${event.instance} ${event.observedAt}`, status };
}