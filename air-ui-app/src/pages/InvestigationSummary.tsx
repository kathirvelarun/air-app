import type { InvestigationResponse } from '../types/investigation';

function Items({ title, items }: { title: string; items?: string[] }) {
  return <section><h4>{title}</h4>{items?.length ? <ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul> : <p className="air-chat-muted">Not available yet.</p>}</section>;
}

export function InvestigationSummary({ result }: { result: InvestigationResponse }) {
  const rca = result.rca;
  const remediation = rca?.suggestion_plan;
  return <div aria-label="Investigation summary">
    <h4>Investigation summary</h4>
    <p><strong>Outcome:</strong> {result.status.replaceAll('_', ' ')}</p>
    {result.terminal_reason && <p>{result.terminal_reason}</p>}
    <p>{result.planning?.plan?.reasoning || 'Planning details are not available.'}</p>
    <h4>Evidence</h4>
    {result.evidence?.evidence?.length ? result.evidence.evidence.map((e, i) => <div className="air-chat-evidence" key={i}><strong>{e.agent_name} · {e.source_system}</strong><p>{e.summary}</p></div>) : <p>No evidence collected.</p>}
    {!!result.evidence?.missing_agents?.length && <p>Unavailable agents: {result.evidence.missing_agents.join(', ')}</p>}
    <h4>Key findings</h4>
    {rca?.key_findings?.length ? rca.key_findings.map(f => <div className="air-chat-evidence" key={f.finding_id}><p>{f.finding}</p><small>Sources: {f.source_refs.join(', ') || 'Not provided'}</small></div>) : <p>No key findings available.</p>}
    <h4>Root cause assessment</h4><p>{rca?.rca?.root_cause || 'Root cause has not been established.'}</p>
    {rca?.rca?.uncertainty && <p><strong>Uncertainty:</strong> {rca.rca.uncertainty}</p>}
    <Items title="Contributing factors" items={rca?.rca?.contributing_factors}/>
    <h4>Remediation recommendations</h4>
    {remediation?.immediate_actions?.length ? remediation.immediate_actions.map(action => <div className="air-chat-evidence" key={action.suggestion_id}><strong>{action.action}</strong><p>{action.rationale}</p><small>Priority: {action.priority} · Risk: {action.risk}{action.requires_human_approval ? ' · Human approval required' : ''}</small></div>) : <p>No remediation recommendations available.</p>}
    <p className="air-chat-muted">Recommendations only. No remediation is executed from this channel.</p>
    <Items title="Verification steps" items={remediation?.verification_steps}/>
    <Items title="Rollback plan" items={remediation?.rollback_plan}/>
    <Items title="Follow-up actions" items={remediation?.follow_up_actions}/>
    <Items title="Missing information" items={rca?.missing_information}/>
  </div>;
}
