import type { AlertEvent } from '../data/incidents';

export type ApiSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';

export type InvestigateRequest = {
  incident: {
    incident_id: string;
    title: string;
    description: string;
    severity: ApiSeverity;
    detected_at: string;
    service_name: string;
    environment: string;
  };
  repository: string;
  start_time: string;
  end_time: string;
  required_metrics?: string[];
};

export type EvidenceItem = {
  investigation_id: string;
  agent_name: string;
  evidence_type: string;
  source_system: string;
  title: string;
  summary: string;
  confidence: number;
  findings: Record<string, unknown>;
  references: unknown[];
  observed_from: string;
  observed_to: string;
  collected_at: string;
};

export type TimelineEntry = { timestamp: string; agent_name: string; evidence_type: string; title: string };

export type InvestigationPlan = {
  plannerVersion: string;
  status: string;
  confidence: number;
  investigationType: string;
  priority: string;
  parallelAgents: string[];
  requiredEvidence: string[];
  hypotheses: string[];
  missingContext: string[];
  contextRequests: unknown[];
  reasoning: string;
};

export type KeyFinding = { finding_id: string; finding: string; source_refs: string[]; confidence: number };
export type Suggestion = { suggestion_id: string; action: string; rationale: string; priority: string; risk: string; requires_human_approval: boolean; source_refs: string[] };
export type SuggestionPlan = { immediate_actions: Suggestion[]; verification_steps: string[]; rollback_plan: string[]; follow_up_actions: string[] };
export type RcaBody = { root_cause: string; contributing_factors: string[]; source_refs: string[]; confidence: number; uncertainty: string };
export type RcaSection = {
  investigation_id: string;
  investigation_status: string;
  key_findings: KeyFinding[];
  rca: RcaBody;
  suggestion_plan: SuggestionPlan;
  overall_confidence: number;
  source_refs_used: string[];
  missing_information: string[];
};

export type InvestigationResponse = {
  investigation_id: string;
  incident_id: string;
  status: string;
  terminal_reason: string | null;
  planning: {
    investigation_id: string;
    incident_id: string;
    status: string;
    terminal_reason: string | null;
    plan: InvestigationPlan;
    evidence_ready: boolean;
  };
  evidence: {
    investigation_id: string;
    evidence: EvidenceItem[];
    missing_agents: string[];
    duplicate_count: number;
    timeline: TimelineEntry[];
  };
  rca: RcaSection;
};

export type LiveStatus = 'Inconclusive' | 'Open' | 'Acknowledged' | 'Investigating' | 'Investigated' | 'Failed';

export type LiveScenario = {
  key: string;
  title: string;
  service: string;
  owner: string;
  slackChannel: string;
  alertSource: string;
  request: InvestigateRequest;
};

export type LiveIncidentRow = { id: string; openedAt: string; slackChannel: string; title: string; service: string; severity: string; status: LiveStatus; time: string; duration: string; owner: string; summary: string };

export type LiveAlertRow = AlertEvent & { id: string; occurrences: AlertEvent[]; searchText: string; status: LiveStatus };