import { useEffect, useState, type ReactNode } from 'react';
import { Button, Chip, LinearProgress, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import { CheckCircleOutlineRounded, DescriptionOutlined, GraphicEqRounded, HubOutlined, ReportProblemOutlined, ShieldOutlined, TimelineRounded } from '@mui/icons-material';
import { INVESTIGATE_URL } from '../api/investigationApi';
import { formatUtc } from '../data/liveScenarios';
import type { EvidenceItem, InvestigationResponse, LiveScenario, LiveStatus } from '../types/investigation';

type Props = {
  scenario: LiveScenario;
  status: LiveStatus;
  result?: InvestigationResponse;
  error?: string;
  onBack: () => void;
  onRun: () => void;
};

const progressStages = ['Planning investigation', 'Collecting evidence', 'Identifying root cause', 'Preparing suggestions'];
const tabs = ['Evidence Details', 'Key Findings', 'RCA', 'Suggestion'] as const;

function idNumber(id: string): string {
  const match = id.match(/\d+/);
  return match ? match[0] : id;
}

function KeyValue({ pairs }: { pairs: [string, ReactNode][] }) {
  return <dl>{pairs.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>;
}

function Chips({ items }: { items: ReactNode[] }) {
  if (!items.length) return null;
  return <div className="air-inline-tags">{items.map((item, i) => <span key={i}>{item}</span>)}</div>;
}

function evidenceIcon(type: string) {
  if (type === 'LOG') return <DescriptionOutlined />;
  if (type === 'METRIC') return <TimelineRounded />;
  if (type === 'DEPLOYMENT') return <HubOutlined />;
  return <GraphicEqRounded />;
}

function GenericFindings({ findings, depth = 0 }: { findings: Record<string, unknown>; depth?: number }) {
  const entries = Object.entries(findings);
  if (!entries.length) return null;
  return <dl>{entries.map(([key, value]) => {
    const label = key.replaceAll('_', ' ');
    if (Array.isArray(value)) {
      if (value.every(v => typeof v !== 'object' || v === null)) return <div key={key}><dt>{label}</dt><dd>{value.length ? <Chips items={value.map(v => String(v))} /> : '—'}</dd></div>;
      if (depth >= 1) return <div key={key}><dt>{label}</dt><dd>{value.length} item(s)</dd></div>;
      return <div key={key}><dt>{label}</dt><dd>{value.map((item, i) => <div key={i} className="air-callout" style={{ marginTop: i ? 8 : 0 }}><GenericFindings findings={item as Record<string, unknown>} depth={depth + 1} /></div>)}</dd></div>;
    }
    if (value !== null && typeof value === 'object') {
      if (depth >= 1) return <div key={key}><dt>{label}</dt><dd>{Object.keys(value).length} field(s)</dd></div>;
      return <div key={key}><dt>{label}</dt><dd><GenericFindings findings={value as Record<string, unknown>} depth={depth + 1} /></dd></div>;
    }
    return <div key={key}><dt>{label}</dt><dd>{String(value)}</dd></div>;
  })}</dl>;
}

function LogFindings({ findings }: { findings: Record<string, unknown> }) {
  const f = findings as { total_events?: number; error_count?: number; warning_count?: number; first_error_at?: string; last_error_at?: string; exceptions?: Record<string, number>; http_statuses?: Record<string, number>; affected_pods?: string[]; affected_classes?: string[] };
  return <>
    <KeyValue pairs={[
      ['Total events', f.total_events ?? '—'],
      ['Error count', f.error_count ?? '—'],
      ['Warning count', f.warning_count ?? '—'],
      ['First error', f.first_error_at ? formatUtc(f.first_error_at) : '—'],
      ['Last error', f.last_error_at ? formatUtc(f.last_error_at) : '—'],
    ]} />
    {f.exceptions && Object.keys(f.exceptions).length > 0 && <Chips items={Object.entries(f.exceptions).map(([name, count]) => `${name} × ${count}`)} />}
    {f.http_statuses && <Chips items={Object.entries(f.http_statuses).map(([code, count]) => `${code} × ${count}`)} />}
    {f.affected_pods && f.affected_pods.length > 0 && <Chips items={f.affected_pods} />}
  </>;
}

type MetricStat = { baseline_avg: number; current_avg: number; percent_change: number; health: string; min?: number; max?: number };

function formatMetricValue(v: number): string {
  return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(v >= 10 ? 1 : 3);
}

function MetricBulletChart({ name, m }: { name: string; m: MetricStat }) {
  const width = 220, height = 54, padX = 6, barY = 20, barH = 14;
  const hasRange = m.min !== undefined && m.max !== undefined;
  const lo = Math.min(0, m.min ?? m.baseline_avg, m.baseline_avg, m.current_avg);
  const hi = Math.max(m.max ?? m.current_avg, m.baseline_avg, m.current_avg);
  const span = hi - lo || Math.abs(hi) * 0.1 || 1;
  const domainMax = hi + span * 0.1;
  const x = (v: number) => padX + (Math.max(0, v - lo) / (domainMax - lo || 1)) * (width - padX * 2);
  const good = m.health === 'HEALTHY';
  return <div className="air-metric-spark-card">
    <div className="air-metric-spark-head"><strong>{name.replaceAll('_', ' ')}</strong><span className={good ? 'air-success' : 'air-error'}>{m.health}</span></div>
    <svg className="air-metric-spark" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${name.replaceAll('_', ' ')} bullet chart: current ${formatMetricValue(m.current_avg)} against baseline ${formatMetricValue(m.baseline_avg)}${hasRange ? `, observed range ${formatMetricValue(m.min!)} to ${formatMetricValue(m.max!)}` : ''}`}>
      <rect x={padX} y={barY} width={width - padX * 2} height={barH} rx={4} fill="#eef1f6" />
      {hasRange && <rect x={x(m.min!)} y={barY} width={Math.max(2, x(m.max!) - x(m.min!))} height={barH} rx={4} fill="#dde3ea" />}
      <rect x={padX} y={barY} width={Math.max(3, x(m.current_avg) - padX)} height={barH} rx={4} fill="var(--accent)" />
      <line x1={x(m.baseline_avg)} y1={barY - 5} x2={x(m.baseline_avg)} y2={barY + barH + 5} stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" />
      <text x={padX} y={barY + barH + 16} fontSize="9" fill="currentColor" opacity={0.7}>Current {formatMetricValue(m.current_avg)}</text>
      <text x={width - padX} y={barY + barH + 16} textAnchor="end" fontSize="9" fill="currentColor" opacity={0.7}>Baseline {formatMetricValue(m.baseline_avg)}</text>
    </svg>
  </div>;
}

function MetricFindings({ findings }: { findings: Record<string, unknown> }) {
  const rows = Object.entries(findings) as [string, MetricStat][];
  return <>
    <div className="air-metric-charts-grid">{rows.map(([name, m]) => <MetricBulletChart key={name} name={name} m={m} />)}</div>
    <TableContainer className="ops-table-panel"><Table size="small"><TableHead><TableRow>{['Metric', 'Baseline', 'Current', 'Change', 'Health'].map(h => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead><TableBody>{rows.map(([name, m]) => <TableRow key={name}><TableCell>{name.replaceAll('_', ' ')}</TableCell><TableCell>{Number(m.baseline_avg).toLocaleString(undefined, { maximumFractionDigits: 3 })}</TableCell><TableCell>{Number(m.current_avg).toLocaleString(undefined, { maximumFractionDigits: 3 })}</TableCell><TableCell>{m.percent_change > 0 ? '+' : ''}{Number(m.percent_change).toFixed(1)}%</TableCell><TableCell><span className={m.health === 'HEALTHY' ? 'air-success' : 'air-error'}>{m.health}</span></TableCell></TableRow>)}</TableBody></Table></TableContainer>
  </>;
}

function DeploymentFindings({ findings }: { findings: Record<string, unknown> }) {
  const f = findings as { deployment_detected?: boolean; latest_deployment?: { version: string; commit_sha: string; branch: string; timestamp: string }; minutes_before_incident?: number; rollback_detected?: boolean; changed_files?: string[]; commits?: { commit_sha: string; actor: string; timestamp: string }[] };
  return <>
    <KeyValue pairs={[
      ['Deployment detected', f.deployment_detected ? 'Yes' : 'No'],
      ['Version', f.latest_deployment?.version ?? '—'],
      ['Branch', f.latest_deployment?.branch ?? '—'],
      ['Commit', f.latest_deployment?.commit_sha ?? '—'],
      ['Deployed at', f.latest_deployment?.timestamp ? formatUtc(f.latest_deployment.timestamp) : '—'],
      ['Minutes before incident', f.minutes_before_incident ?? '—'],
      ['Rollback detected', f.rollback_detected ? 'Yes' : 'No'],
    ]} />
    {f.changed_files && f.changed_files.length > 0 && <Chips items={f.changed_files} />}
    {f.commits && f.commits.length > 0 && <ul className="air-causal">{f.commits.map(c => <li key={c.commit_sha}>{c.commit_sha} · {c.actor} · {formatUtc(c.timestamp)}</li>)}</ul>}
  </>;
}

function Findings({ type, findings }: { type: string; findings: Record<string, unknown> }) {
  if (type === 'LOG') return <LogFindings findings={findings} />;
  if (type === 'METRIC') return <MetricFindings findings={findings} />;
  if (type === 'DEPLOYMENT') return <DeploymentFindings findings={findings} />;
  return <GenericFindings findings={findings} />;
}

function ConfidenceMeter({ value, size = 72 }: { value: number; size?: number }) {
  const pct = Math.round(value * 100);
  const good = pct >= 75;
  const tone = good ? '#237c5a' : '#c69240';
  const cx = size / 2, cy = size * 0.56, r = size * 0.42, strokeWidth = size * 0.08;
  const svgHeight = size * 0.62;
  const angleFor = (p: number) => Math.PI - (Math.min(100, Math.max(0, p)) / 100) * Math.PI;
  const point = (angle: number, radius: number) => ({ x: cx + radius * Math.cos(angle), y: cy - radius * Math.sin(angle) });
  const start = point(Math.PI, r);
  const trackEnd = point(0, r);
  const valueEnd = point(angleFor(pct), r);
  const needle = point(angleFor(pct), r * 0.72);
  return <div className="air-confidence-meter">
    <svg width={size} height={svgHeight} viewBox={`0 0 ${size} ${svgHeight}`} role="img" aria-label={`Confidence ${pct}%, ${good ? 'high' : 'needs review'}`}>
      <path d={`M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${trackEnd.x} ${trackEnd.y}`} fill="none" stroke="#e5e9ed" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path d={`M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${valueEnd.x} ${valueEnd.y}`} fill="none" stroke={tone} strokeWidth={strokeWidth} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={needle.x} y2={needle.y} stroke={tone} strokeWidth={1.75} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={2.5} fill={tone} />
    </svg>
    <span className="air-confidence-value">{pct}%</span>
    <span className="air-confidence-caption" style={{ color: tone }}>{good ? <CheckCircleOutlineRounded fontSize="inherit" /> : <ReportProblemOutlined fontSize="inherit" />}{good ? 'High' : 'Review'}</span>
  </div>;
}

function EvidenceCard({ item }: { item: EvidenceItem }) {
  return <div className="air-card air-analysis-example">
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
      <span className="air-evidence-icon">{evidenceIcon(item.evidence_type)}</span>
      <div style={{ flex: 1 }}>
        <span className="air-eyebrow">{item.evidence_type} <span>/ {item.agent_name}</span></span>
        <h3>{item.title}</h3>
      </div>
      <ConfidenceMeter value={item.confidence} />
    </div>
    <p className="air-evidence-summary">{item.summary}</p>
    <p className="air-secondary">{item.source_system} · {formatUtc(item.observed_from)} – {formatUtc(item.observed_to)}</p>
    <Findings type={item.evidence_type} findings={item.findings} />
  </div>;
}

function priorityTone(priority: string) {
  return priority === 'CRITICAL' || priority === 'HIGH' ? 'air-error' : 'air-success';
}

function InvestigationProgress({ step }: { step: number }) {
  return <div className="air-run-panel" aria-label="Investigation progress">
    <div className="air-section-title"><h3>{progressStages[step] ?? 'Finishing up'}</h3><span className="ops-status investigating">{Math.min(step + 1, progressStages.length)}/{progressStages.length}</span></div>
    <LinearProgress variant="determinate" value={(Math.min(step + 1, progressStages.length) / progressStages.length) * 100} aria-label="Investigation completion" />
    <ol className="air-run-steps">{progressStages.map((label, i) => <li key={label} className={i < step ? 'complete' : i === step ? 'running' : ''}><span>{i < step ? '✓' : i + 1}</span><div>{label}<small>{i < step ? 'Complete' : i === step ? 'In progress' : 'Pending'}</small></div></li>)}</ol>
    <div className="air-run-footer" role="status">Calling {INVESTIGATE_URL}</div>
  </div>;
}

export function LiveIncidentPage({ scenario, status, result, error, onBack, onRun }: Props) {
  const incident = scenario.request.incident;
  const environment = incident.environment.charAt(0).toUpperCase() + incident.environment.slice(1);
  const plan = result?.planning.plan;
  const evidence = result?.evidence;
  const rca = result?.rca;
  const ready = Boolean(result && plan && evidence && rca);
  const [progressStep, setProgressStep] = useState(0);
  const [tab, setTab] = useState(0);
  useEffect(() => {
    if (status !== 'Investigating' || ready) { setProgressStep(0); return; }
    if (progressStep >= progressStages.length - 1) return;
    const timer = window.setTimeout(() => setProgressStep(s => Math.min(progressStages.length - 1, s + 1)), 1300);
    return () => window.clearTimeout(timer);
  }, [status, ready, progressStep]);

  return <>
    <div className="air-breadcrumb"><button onClick={onBack}>← All incidents</button> <span>/</span> {scenario.key} <span className="air-demo-label">LIVE · INVESTIGATE API</span></div>
    <div className="air-page-heading">
      <div>
        <div className="air-title-line"><span className="air-severity">{incident.severity}</span><span className={`ops-status ${status.toLowerCase()}`}><i />{status}</span><span className="air-secondary">Detected {formatUtc(incident.detected_at)}</span></div>
        <h1>{incident.title}</h1>
        <p>{incident.description}</p>
      </div>
      <div className="air-owner"><span className="air-avatar">{scenario.owner.split(' ').map(n => n[0]).join('')}</span><div><span>OWNER</span>{scenario.owner}</div></div>
    </div>
    <div className="air-metadata"><span><i /> {incident.service_name}</span><span>{environment}</span><span>{scenario.request.repository}</span><span>Window {formatUtc(scenario.request.start_time)} – {formatUtc(scenario.request.end_time)}</span><span>#{scenario.slackChannel}</span></div>

    {(status === 'Open' || status === 'Acknowledged') && !ready && <div className="air-card">
      <h3>Investigation not started</h3>
      <p>Planning, evidence collection, root cause analysis, and suggestions run server-side in a single request. This can take up to a minute.</p>
      <Button variant="contained" onClick={onRun}>Start investigation</Button>
    </div>}

    {status === 'Investigating' && !ready && <InvestigationProgress step={progressStep} />}

    {status === 'Failed' && <div className="air-card">
      <h3>Investigation request failed</h3>
      <p className="air-error">{error}</p>
      <p>Confirm the AIR API is running at {INVESTIGATE_URL} and reachable from this browser.</p>
      <Button variant="contained" onClick={onRun}>Retry investigation</Button>
    </div>}

    {result && !ready && <div className="air-card">
      <h3>Investigation did not return a full result</h3>
      <p>Status: {result.status}{result.terminal_reason ? ` · ${result.terminal_reason}` : ''}</p>
      <Button variant="contained" onClick={onRun}>Run again</Button>
    </div>}

    {ready && plan && evidence && rca && <div className="air-content-grid">
      <section className="air-primary">
        <div className="air-section-title"><div><div className="air-eyebrow">AGENT PLAN</div><h2>{plan.investigationType}</h2></div><span className="air-live-tag"><span className="green-dot" /> Priority {plan.priority} · confidence {(plan.confidence * 100).toFixed(0)}%</span></div>
        <div className="air-insight">
          <div className="air-insight-icon"><GraphicEqRounded /></div>
          <div>
            <span className="air-eyebrow">PLANNER REASONING</span>
            <p>{plan.reasoning}</p>
            <Chips items={plan.parallelAgents.map(a => `Agent: ${a}`)} />
            <Chips items={plan.requiredEvidence.map(e => `Evidence: ${e}`)} />
          </div>
        </div>

        <div className="air-steps" aria-label="Investigation results">{tabs.map((label, i) => <button key={label} className={tab === i ? 'selected' : ''} onClick={() => setTab(i)} aria-current={tab === i ? 'step' : undefined}><span>{i + 1}</span>{label}{i < tabs.length - 1 && <span className="step-line" />}</button>)}</div>

        {tab === 0 && <>
          <div className="air-card">
            <h3>Hypotheses</h3>
            <ol className="air-causal">{plan.hypotheses.map(h => <li key={h}>{h}</li>)}</ol>
            {plan.missingContext.length > 0 && <div className="air-callout">Missing context: {plan.missingContext.join('; ')}</div>}
          </div>
          <div className="air-section-title evidence-heading"><h3>Evidence trail <span className="air-number">{evidence.evidence.length.toString().padStart(2, '0')}</span></h3><span className="air-secondary">{evidence.duplicate_count} duplicate(s) removed</span></div>
          {evidence.missing_agents.length > 0 && <div className="air-callout">No evidence returned from: {evidence.missing_agents.join(', ')}.</div>}
          <div style={{ display: 'grid', gap: 16 }}>{evidence.evidence.map(item => <EvidenceCard key={`${item.agent_name}-${item.evidence_type}`} item={item} />)}</div>
        </>}

        {tab === 1 && <div className="air-card air-analysis-example">
          <div className="air-section-title"><h3>Key findings</h3></div>
          <dl>{rca.key_findings.map(kf => <div key={kf.finding_id}><dt>{idNumber(kf.finding_id)}</dt><dd>{kf.finding} <em style={{ color: 'var(--muted)' }}>({(kf.confidence * 100).toFixed(0)}% confidence)</em><br /><Chips items={kf.source_refs} /></dd></div>)}</dl>
        </div>}

        {tab === 2 && <>
          <div className="air-insight">
            <div className="air-insight-icon"><HubOutlined /></div>
            <div>
              <span className="air-eyebrow">ROOT CAUSE · confidence {(rca.overall_confidence * 100).toFixed(0)}%</span>
              <h3>{rca.rca.root_cause}</h3>
              <p>{rca.rca.uncertainty}</p>
              <Chips items={rca.rca.source_refs} />
            </div>
          </div>
          {rca.rca.contributing_factors.length > 0 && <div className="air-card"><h3>Contributing factors</h3><ul className="air-causal">{rca.rca.contributing_factors.map(f => <li key={f}>{f}</li>)}</ul></div>}
          {rca.missing_information.length > 0 && <div className="air-callout">Missing information: {rca.missing_information.join(' · ')}</div>}
        </>}

        {tab === 3 && <>
          {rca.suggestion_plan.immediate_actions.map(s => <div className="air-card" key={s.suggestion_id}>
            <div className="air-section-title"><span className="air-eyebrow">{idNumber(s.suggestion_id)}</span>{s.requires_human_approval && <Chip label="Approval required" size="small" variant="outlined" />}</div>
            <h3>{s.action}</h3>
            <p>{s.rationale}</p>
            <div className="air-key-values"><span>Priority<strong className={priorityTone(s.priority)}>{s.priority}</strong></span><span>Risk<strong>{s.risk}</strong></span></div>
            <Chips items={s.source_refs} />
          </div>)}
          <div className="air-card">
            <h3>Verification steps</h3>
            <ol className="air-causal">{rca.suggestion_plan.verification_steps.map(v => <li key={v}>{v}</li>)}</ol>
            {rca.suggestion_plan.rollback_plan.length > 0 && <><h3>Rollback plan</h3><ol className="air-causal">{rca.suggestion_plan.rollback_plan.map(v => <li key={v}>{v}</li>)}</ol></>}
            {rca.suggestion_plan.follow_up_actions.length > 0 && <><h3>Follow-up actions</h3><ul className="air-causal">{rca.suggestion_plan.follow_up_actions.map(v => <li key={v}>{v}</li>)}</ul></>}
          </div>
        </>}

        <details className="air-card"><summary style={{ cursor: 'pointer', fontWeight: 600 }}>View raw API response</summary><pre className="air-raw-response">{JSON.stringify(result, null, 2)}</pre></details>
      </section>
      <aside className="air-context">
        <div className="air-card">
          <div className="air-section-title"><h3>Investigation</h3><span className="air-success">{result?.status}</span></div>
          <div className="air-key-values"><span>Evidence sources<strong>{evidence.evidence.length}</strong></span><span>Suggested actions<strong>{rca.suggestion_plan.immediate_actions.length}</strong></span></div>
        </div>
        <div className="air-card air-timeline">
          <div className="air-section-title"><h3>Activity</h3><span className="air-secondary">UTC</span></div>
          {evidence.timeline.map((t, i) => <div className="air-event" key={i}><span className="air-event-dot" /><div><time>{formatUtc(t.timestamp)}</time><strong>{t.title}</strong><p>{t.agent_name} · {t.evidence_type}</p></div></div>)}
        </div>
        <div className="air-trust"><ShieldOutlined /><p><strong>Read-only investigation.</strong><br />AIR recommends actions; nothing here changes production.</p></div>
      </aside>
    </div>}
    <footer className="air-footer">AIR / Agentic Incident Response<span>Live investigation · {INVESTIGATE_URL}</span></footer>
  </>;
}