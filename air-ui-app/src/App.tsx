import { readInvestigation, publishInvestigation, subscribeInvestigations } from './utils/investigationSync';
import { fetchChannel, toScenario, type IntakeIncident } from './api/alertIntake';
import { SlackChannelPage } from './pages/SlackChannelPage';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import { useEffect, useRef, useState } from 'react';
import { Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions, TextField, LinearProgress, MenuItem } from '@mui/material';
import { ArrowForwardRounded, CheckRounded, BoltRounded, HubOutlined, NotificationsNoneRounded, ArrowOutwardRounded, CloseRounded, ShieldOutlined, TimelineRounded, DescriptionOutlined, GraphicEqRounded } from '@mui/icons-material';
import './styles/base.css';
import './styles/referenceTheme.css';
import './styles/amexTheme.css';
import { PostmortemReview } from './components/PostmortemReview';
import { LeadershipPage } from './pages/LeadershipPage';
import { CommanderPage } from './pages/CommanderPage';
import { canManage, defaultSystems } from './utils/access';
import type { AirRole } from './utils/access';
import { OperationsPage } from './pages/OperationsPage';
import { LiveIncidentPage } from './pages/LiveIncidentPage';
import { investigateIncident } from './api/investigationApi';
import { liveIncidentRow, liveAlertRow, formatElapsed, formatUtc } from './data/liveScenarios';
import type { InvestigationResponse, LiveStatus } from './types/investigation';

const prototypeTheme = createTheme({ palette: { mode: 'light', primary: { main: '#006fcf' } }, typography: { fontFamily: '"Helvetica Neue", Helvetica, Arial, sans-serif', button: { textTransform: 'none' } } });

const stages = ['Investigation', 'Root Cause Analysis', 'Remediation Plan', 'Post-Incident Review'];
const evidence = [
  { id: 'E01', type: 'METRICS', title: 'Connection pool reaches capacity', source: 'Prometheus · checkout-api · 09:42 UTC', detail: 'Active connections: 100 / 100. Wait time increased from 12 ms to 4.2 s after the deployment. Database CPU remained at 34%.', state: 'Supports hypothesis' },
  { id: 'E02', type: 'CHANGE', title: 'Pool configuration changed in v2.18.0', source: 'Deployment event · 09:38 UTC', detail: 'checkout-api v2.18.0 reduced maxPoolSize from 200 to 100. Error onset follows the deployment by four minutes. Temporal correlation requires validation.', state: 'Supports hypothesis' },
  { id: 'E03', type: 'LOGS', title: 'Requests time out acquiring connections', source: 'Application logs · 09:43 UTC', detail: 'ConnectionTimeoutException: no connection available after 4000 ms. 842 matching events in the five-minute sample; no credential or DNS errors observed.', state: 'Supports hypothesis' },
  { id: 'E04', type: 'TRACES', title: 'Latency concentrates before database calls', source: 'OpenTelemetry · 09:44 UTC', detail: 'Sampled checkout traces show 82% of duration waiting for a connection. Database execution duration is near baseline. Sampling may miss other failure modes.', state: 'Alternative weakened' },
];
export default function App() {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = 'AIR — Agentic Incident Response';
    const context = (document as Document & { modelContext?: { registerTool: (tool: { name: string; description: string; inputSchema: object; annotations: object; execute: (input: unknown) => unknown }, options: { signal: AbortSignal }) => void | Promise<void> } }).modelContext;
    const lifecycle = new AbortController();
    if (context?.registerTool) {
      try {
        void Promise.resolve(context.registerTool({
          name: 'read_air_demo_evidence',
          description: 'Read synthetic evidence for AIR incident INC-2048. Returns provenance and findings; does not access production systems.',
          inputSchema: { type: 'object', properties: { evidenceId: { type: 'string', enum: ['E01', 'E02', 'E03', 'E04'] } }, required: ['evidenceId'], additionalProperties: false },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute(input: unknown) {
            if (!input || typeof input !== 'object' || Object.keys(input).length !== 1 || !('evidenceId' in input)) throw new Error('Provide exactly one evidenceId.');
            const record = evidence.find(item => item.id === input.evidenceId);
            if (!record) throw new Error('Unknown evidence ID.');
            return { incidentId: 'INC-2048', simulated: true, evidence: record };
          },
        }, { signal: lifecycle.signal })).catch(() => console.warn('Optional AIR evidence tool could not be registered.'));
      } catch { console.warn('Optional AIR evidence tool unavailable.'); }
    }
    return () => { lifecycle.abort(); document.title = previousTitle; };
  }, []);
  const [route, setRoute] = useState(window.location.pathname);
  useEffect(() => {
    const sync = () => setRoute(window.location.pathname);
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  const goTo = (path: string) => { window.history.pushState({}, '', path); setRoute(path); };
  const [role, setRole] = useState<AirRole>('SRE Engineer');
  const [systems, setSystems] = useState(defaultSystems);
  const [stage, setStage] = useState(0);
  const [unlocked, setUnlocked] = useState(0);
  const [nav, setNav] = useState('Overview');
  const [detail, setDetail] = useState(false);
  const incidentHeading = useRef<HTMLHeadingElement>(null);
  const [analysisStep, setAnalysisStep] = useState(0);
  useEffect(() => {
    if (!detail) return;
    if (analysisStep >= 4) { incidentHeading.current?.focus(); return; }
    const timer = window.setTimeout(() => setAnalysisStep(step => Math.min(4, step + 1)), 1500);
    return () => window.clearTimeout(timer);
  }, [detail, analysisStep]);
  const [selectedEvidence, setSelectedEvidence] = useState<number | null>(null);
  const [approved, setApproved] = useState(false);
  const [recovered, setRecovered] = useState(false);
  const [approvalOpen, setApprovalOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [report, setReport] = useState('Checkout requests failed when the connection pool saturated following deployment v2.18.0. Rolling back the pool configuration restored service in this simulated incident. Add configuration validation and pool-wait alerting to prevent recurrence.');
  const [reviewed, setReviewed] = useState(false);
  const [note, setNote] = useState('');
  const advance = (n: number) => { setStage(n); setUnlocked(Math.max(unlocked, n)); setNav('Incidents'); };
  const [intake, setIntake] = useState<IntakeIncident[]>([]);
  const [intakeError, setIntakeError] = useState('');
  const liveScenarios = intake.map(toScenario);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try { const items = await fetchChannel(controller.signal); setIntake(items); setIntakeError(''); }
      catch (error) { if (!controller.signal.aborted) setIntakeError(error instanceof Error ? error.message : 'Unable to load alerts.'); }
      if (!controller.signal.aborted) timer = setTimeout(refresh, 2000);
    };
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  const [liveStatus, setLiveStatus] = useState<Record<string, LiveStatus>>({});
  const [liveResults, setLiveResults] = useState<Record<string, InvestigationResponse>>({});
  const [liveErrors, setLiveErrors] = useState<Record<string, string>>({});
  const [liveTiming, setLiveTiming] = useState<Record<string, { startedAt: number; finishedAt?: number }>>({});
  const [openLiveKey, setOpenLiveKey] = useState<string | null>(null);
  useEffect(() => {
    const refresh = () => {
      const snapshots = intake.map(i => ({ key: i.id, snapshot: readInvestigation(i.uuid) })).filter(i => i.snapshot);
      setLiveStatus(Object.fromEntries(snapshots.map(({ key, snapshot }) => [key, snapshot!.status])));
      setLiveResults(Object.fromEntries(snapshots.filter(i => i.snapshot!.result).map(({ key, snapshot }) => [key, snapshot!.result!])));
      setLiveErrors(Object.fromEntries(snapshots.filter(i => i.snapshot!.error).map(({ key, snapshot }) => [key, snapshot!.error!])));
      setLiveTiming(Object.fromEntries(snapshots.map(({ key, snapshot }) => [key, { startedAt: snapshot!.startedAt, finishedAt: snapshot!.finishedAt }])));
    };
    refresh();
    return subscribeInvestigations(refresh);
  }, [intake]);

  useEffect(() => {
    if (!Object.values(liveStatus).includes('Investigating')) return;
    const timer = window.setInterval(() => setLiveTiming(current => ({ ...current })), 1000);
    return () => window.clearInterval(timer);
  }, [liveStatus]);
  const runInvestigation = async (key: string) => {
    const scenario = liveScenarios.find(s => s.key === key);
    if (!scenario) return;
    const uuid = scenario.request.incident.incident_id;
    const startedAt = Date.now();
    try {
      publishInvestigation({ uuid, status: 'Investigating', startedAt });
    } catch {
      setLiveErrors(current => ({ ...current, [key]: 'Browser storage is unavailable. Enable site storage to synchronize investigation tabs.' }));
      return;
    }
    try {
      const result = await investigateIncident(scenario.request);
      const status: LiveStatus = result.status === 'COMPLETED' ? 'Investigated' : result.status === 'INCONCLUSIVE' ? 'Inconclusive' : 'Failed';
      publishInvestigation({ uuid, status, startedAt, finishedAt: Date.now(), result,
        ...(status === 'Failed' ? { error: result.terminal_reason || result.status } : {}) });
    } catch (err) {
      const error = err instanceof Error ? err.message : 'Investigation request failed.';
      try { publishInvestigation({ uuid, status: 'Failed', startedAt, finishedAt: Date.now(), error }); }
      catch { setLiveErrors(current => ({ ...current, [key]: error + ' Unable to save the update to browser storage.' })); }
    }
  };
  const openLiveIncident = (key: string) => {
    setDetail(false);
    setNav('Incidents');
    setOpenLiveKey(key);
    goTo(`/incidents/${key}/investigation`);
  };
  const liveDuration = (key: string): string => {
    const timing = liveTiming[key];
    if (!timing) return '—';
    return formatElapsed((timing.finishedAt ?? Date.now()) - timing.startedAt);
  };
  const liveIncidentRows = liveScenarios.map(s => liveIncidentRow(s, liveStatus[s.key] ?? 'Open', liveDuration(s.key)));
  const liveAlertRows = liveScenarios.map(s => {
    const row = liveAlertRow(s, liveStatus[s.key] ?? 'Open');
    const incident = intake.find(i => i.id === s.key)!;
    row.environment = incident.environment;
    row.occurrences = incident.alerts.map(a => ({ ...row, eventId: `${a.source}:${a.eventId}`, source: a.source, title: a.summary, environment: a.environment, observedAt: formatUtc(a.observedAt) }));
    return row;
  });
  const openLiveScenario = liveScenarios.find(s => s.key === openLiveKey) ?? null;
  useEffect(() => {
    const match = /^\/incidents\/(INC-\d+)\/investigation$/.exec(route);
    if (match) { setOpenLiveKey(match[1]); setDetail(false); setNav('Incidents'); }
    else setOpenLiveKey(null);
  }, [route]);
  if (route === '/slack') return <SlackChannelPage incidents={intake} loadError={intakeError} statuses={liveStatus} results={liveResults} errors={liveErrors} onPortal={() => goTo('/')} />;
  return <ThemeProvider theme={prototypeTheme}><div className="air-prototype">
    <aside className="air-sidebar">
      <a className="air-brand" href="/prototype"><span className="air-brand-icon"><GraphicEqRounded /></span> AIR<span className="air-brand-dot">●</span></a>
      <div className="air-workspace"><span className="air-avatar">N</span><div>Northstar<span>Production workspace</span></div><span>⌄</span></div>
      <span className="air-eyebrow nav-label">WORKSPACE</span>
      <nav><button onClick={() => goTo('/slack')}><NotificationsNoneRounded />Slack channel</button>{[{ label: 'Overview', icon: <HubOutlined /> }, { label: 'Alerts', icon: <NotificationsNoneRounded /> }, { label: 'Incidents', icon: <BoltRounded /> }, { label: 'Post-mortems', icon: <DescriptionOutlined /> }, ...(canManage(role) ? [{label:'Analytics',icon:<TimelineRounded/>},{label:'System configuration',icon:<ShieldOutlined/>}] : [])].map(item => <button key={item.label} className={nav === item.label ? 'active' : ''} onClick={() => { goTo('/'); setNav(item.label); setDetail(false); setOpenLiveKey(null); }} >{item.icon}{item.label}{item.label === 'Incidents' && <span className="nav-count">{liveIncidentRows.length}</span>}</button>)}</nav>
      <div className="air-sidebar-bottom"><div className="air-agent-health"><span className="green-dot" /> Agent systems operational<span>4 evidence sources connected</span></div><div className="air-profile"><span className="air-avatar">SC</span><div>Sam Chen<span>{role}</span></div></div></div>
    </aside>
    <div className="air-workarea">
      <header className="air-topbar"><div>Workspace <span>/</span> <strong>{nav}</strong></div><div className="air-top-actions"><TextField select size="small" label="Demo role" className="air-role-switch" value={role} onChange={e=>{const next=e.target.value as AirRole;setRole(next);if(!canManage(next)&&['Analytics','System configuration'].includes(nav)){setNav('Overview');setDetail(false);}setApprovalOpen(false);}}>{(['SRE Engineer','Incident Commander'] as const).map(r=><MenuItem key={r} value={r}>{r}</MenuItem>)}</TextField><Chip label="Demo workspace" size="small" variant="outlined" /><span className="air-avatar small">SC</span></div></header>
      <main>
        {intakeError && <p role="alert">{intakeError}</p>}
        {openLiveScenario ? <LiveIncidentPage key={openLiveScenario.key} scenario={openLiveScenario} status={liveStatus[openLiveScenario.key] ?? 'Open'} result={liveResults[openLiveScenario.key]} error={liveErrors[openLiveScenario.key]} onBack={() => { goTo('/'); setOpenLiveKey(null); }} onRun={() => runInvestigation(openLiveScenario.key)} /> : !detail && nav==='Analytics' && canManage(role) ? <LeadershipPage recovered={recovered} systems={systems}/> : !detail && nav==='System configuration' ? <CommanderPage key={nav+role} role={role} page={nav} recovered={recovered} systems={systems} onSave={config=>{if(canManage(role))setSystems(current=>current.some(s=>s.id===config.id)?current.map(s=>s.id===config.id?config:s):[...current,config]);}} /> : !detail ? <OperationsPage key={nav} page={nav} recovered={recovered} reviewed={reviewed} openIncident={n=>{if(n===0&&!recovered)setAnalysisStep(0);setStage(n);setNav('Incidents');setDetail(true);}} liveIncidentRows={liveIncidentRows} liveAlertRows={liveAlertRows} onOpenLive={openLiveIncident} /> : analysisStep < 4 ? <div className="air-investigation-wait" aria-hidden="true" /> : <>
        <div className="air-breadcrumb"><button onClick={()=>setDetail(false)}>← All incidents</button> <span>/</span> INC-2048 <span className="air-demo-label">SIMULATED SCENARIO</span></div>
        <div className="air-page-heading"><div><div className="air-title-line"><span className="air-severity">SEV 1</span><span className="air-status"><span className="green-dot" />{recovered ? 'Resolved · recovery verified' : 'In progress · investigating'}</span><span className="air-secondary">Opened Sep 7, 09:43 UTC</span></div><h1 ref={incidentHeading} tabIndex={-1}>Elevated error rate on checkout-api</h1><p>Checkout failures are affecting customers in us-east-1.</p></div><div className="air-owner"><span className="air-avatar">SC</span><div><span>COMMANDER</span>Sam Chen</div></div></div>
        <div className="air-metadata"><span><i /> checkout-api</span><span>Production</span><span>us-east-1</span><span>4 alert groups · 8 occurrences</span><span>Payments platform</span><span>#air-inc-2048 · Slack ready (demo)</span></div>
        <div className="air-steps" aria-label="Incident lifecycle">{stages.map((s,i) => <button key={s} className={`${stage === i ? 'selected' : ''} ${i < unlocked ? 'done' : ''}`} disabled={analysisStep < 4 && i > 0} onClick={() => setStage(i)} aria-current={stage === i ? 'step' : undefined}><span>{i < unlocked ? <CheckRounded fontSize="small" /> : `0${i + 1}`}</span>{s}{i < 3 && <span className="step-line" />}</button>)}</div>

        <div className={`air-content-grid ${stage===3?'air-report-layout':''}`}><section className="air-primary">
          <div className="air-section-title"><div><div className="air-eyebrow">{['AGENT WORKSPACE', 'CAUSAL ASSESSMENT', 'RECOVERY PLAN', 'INCIDENT LEARNING'][stage]}</div><h2>{['Investigation', 'Root Cause Analysis', 'Remediation Plan', 'Post-Incident Review'][stage]}</h2></div><span className="air-live-tag"><span className="green-dot" />{stage === 0 ? analysisStep < 4 ? 'Analyzing' : 'Analysis ready' : 'Demo data'}</span></div>
          {stage === 0 && analysisStep < 4 && <div className="air-card"><h3>Analyzing checkout-api</h3><p>AIR is checking deployment history, connection-pool metrics, application logs, and trace timing. The example analysis will appear here after the simulated checks complete.</p><p>Scope: Production · us-east-1 · 09:30–10:00 UTC. No production changes are made.</p></div>}
          {stage === 0 && analysisStep === 4 && <><div className="air-completed-analysis"><span className="air-success">✓ Investigation analysis complete</span>{!recovered&&<Button size="small" onClick={()=>{setAnalysisStep(0);setStage(0);}}>Replay analysis</Button>}</div><div className="air-insight"><div className="air-insight-icon"><GraphicEqRounded /></div><div><span className="air-eyebrow">AIR FINDING</span><h3>A deployment change points to connection exhaustion.</h3><p>Error rate rose four minutes after v2.18.0. Database execution is healthy; requests are waiting for a free connection.</p><div className="air-inline-tags"><span>4 evidence sources</span><span>1 hypothesis to validate</span><span>Read-only investigation</span></div></div></div><div className="air-card air-analysis-example"><div className="air-section-title"><h3>Worked example · checkout investigation</h3><span className="ops-status investigating">Evidence-backed assessment</span></div><dl><div><dt>Observation</dt><dd>Errors reached 12.8% four minutes after deployment. All 100 pool connections were occupied; database CPU stayed at 34%. <button onClick={()=>setSelectedEvidence(0)}>E01 ↗</button></dd></div><div><dt>Change examined</dt><dd>v2.18.0 reduced maxPoolSize from 200 to 100. The request timeout remained 4 seconds. <button onClick={()=>setSelectedEvidence(1)}>E02 ↗</button></dd></div><div><dt>Alternative tested</dt><dd>A database-wide slowdown is less supported: sampled traces spend most time waiting for connections, with database execution near baseline. <button onClick={()=>setSelectedEvidence(3)}>E04 ↗</button></dd></div><div><dt>Key finding</dt><dd>Reduced pool capacity is the leading explanation for checkout timeouts. A connection leak remains unverified; correlation alone does not establish causation.</dd></div><div><dt>Next validation</dt><dd>Verify database headroom before a canary rollback, then observe errors and connection wait against the recovery gate.</dd></div></dl></div><div className="air-section-title evidence-heading"><h3>Evidence trail <span className="air-number">04</span></h3><span className="air-secondary">Window · 09:30–10:00 UTC</span></div><div className="air-evidence-list">{evidence.map((e,i) => <button key={e.id} className="air-evidence" onClick={() => setSelectedEvidence(i)}><span className="air-evidence-icon">{i === 0 ? <TimelineRounded /> : i === 1 ? <HubOutlined /> : i === 2 ? <DescriptionOutlined /> : <GraphicEqRounded />}</span><div><span className="air-eyebrow">{e.type} <span> / {e.id}</span></span><h3>{e.title}</h3><p className="air-evidence-summary">{e.detail}</p><p>{e.source}</p></div><ArrowOutwardRounded fontSize="small" /></button>)}</div><div className="air-bottom-action"><span><ShieldOutlined fontSize="small" /> No production changes made</span><Button variant="contained" endIcon={<ArrowForwardRounded />} onClick={() => advance(1)}>Review root cause analysis</Button></div></>}
          {stage === 1 && <><div className="air-insight"><div className="air-insight-icon"><HubOutlined /></div><div><span className="air-eyebrow">PROBABLE CAUSE · STRONG EVIDENCE</span><h3>Reduced pool capacity under sustained traffic</h3><p>v2.18.0 reduced the connection pool from 200 to 100. Pool saturation caused acquisition timeouts and downstream checkout failures.</p><div className="air-inline-tags">{[0,1,2].map(i => <button key={i} onClick={() => setSelectedEvidence(i)}>{evidence[i].id} ↗</button>)}</div></div></div><div className="air-card air-code-card"><div className="air-section-title"><h3>Configuration change</h3><button className="air-code-link" onClick={()=>setSelectedEvidence(1)}>E02 · View evidence ↗</button></div><p>Deployment v2.18.0 · illustrative configuration diff</p><div className="air-code-file">checkout-api / application.yaml</div><pre aria-label="Pool configuration diff"><code><span>  datasource:</span><span>    pool:</span><span className="removed">−     maxPoolSize: 200</span><span className="added">+     maxPoolSize: 100</span><span>      connectionTimeoutMs: 4000</span></code></pre></div><div className="air-card"><h3>Causal chain</h3><ol className="air-causal"><li>Configuration change reduces available connections.</li><li>Request concurrency exceeds pool capacity.</li><li>Waiting requests exceed the acquisition timeout.</li><li>Checkout responds with errors.</li></ol><div className="air-callout">Still unverified: whether a slow connection release amplified the saturation. Recovery after rollback supports this hypothesis but does not prove it alone.</div></div><div className="air-card"><h3>Alternative considered</h3><p><strong>Database resource saturation</strong> · Less supported</p><p>CPU and query duration remain near baseline (E01, E04). No evidence of a database-wide bottleneck in this window.</p></div><Button variant="contained" endIcon={<ArrowForwardRounded />} onClick={() => advance(2)}>Review remediation plan</Button></>}
          {stage === 2 && <><div className="air-card"><div className="air-section-title"><span className="air-eyebrow">RECOMMENDED · REVERSIBLE</span><Chip label="Approval required" size="small" variant="outlined" /></div><h2>Restore the previous pool configuration</h2><p>Roll checkout-api back to v2.17.4 in us-east-1 after confirming database connection headroom.</p><div className="air-key-values"><span>Risk<strong>Medium</strong></span><span>Scope<strong>Checkout · one region</strong></span><span>Expected recovery<strong>5–10 minutes</strong></span></div><ol className="air-causal"><li>Verify the previous artifact and database connection budget.</li><li>Apply to one canary replica; monitor for five minutes.</li><li>Expand only if errors and connection wait return to baseline.</li></ol><div className="air-callout">Abort if error rate increases or database connections exceed 80% of the approved budget. Restore v2.18.0 and escalate to the incident commander.</div></div><div className="air-card"><h3>Verification gate</h3><p>5xx below 2%, p95 below 500 ms, and no new dependency errors for 10 consecutive minutes.</p>{approved && <p className="air-success">✓ Sam Chen approved the simulation. Reason: {reason}</p>}{recovered && <p className="air-success">✓ Simulated recovery verified: 0.3% errors · 240 ms p95 · 10-minute window.</p>}</div><div className="air-button-row">{!approved ? <Button variant="contained" onClick={() => setApprovalOpen(true)}>Review & approve simulation</Button> : !recovered ? <Button variant="contained" onClick={() => { setRecovered(true); setNote('Demo recovery completed. No external system was changed.'); }}>Simulate rollback & verification</Button> : <Button variant="contained" endIcon={<ArrowForwardRounded />} onClick={() => advance(3)}>Prepare post-incident review</Button>}</div></>}
          {stage === 3 && (!recovered ? <div className="air-card"><h3>Recovery evidence is required</h3><p>Complete the remediation simulation before preparing the full incident review.</p><Button onClick={()=>advance(2)}>Go to remediation plan</Button></div> : <PostmortemReview summary={report} reason={reason} evidence={evidence} reviewed={reviewed} onSummary={value=>{setReport(value);setReviewed(false);}} onReview={()=>setReviewed(true)}/>)}
        </section><aside className="air-context"><div className="air-card"><div className="air-section-title"><h3>Service health</h3><span className={recovered ? 'air-success' : 'air-error'}>{recovered ? 'Recovered' : 'Degraded'}</span></div><div className="air-health-value">{recovered ? '0.3' : '12.8'}<span>%</span><small>5xx error rate</small></div><svg className="air-chart" viewBox="0 0 280 90" role="img" aria-label={recovered ? 'Simulated error rate returned to baseline' : 'Simulated error rate rose after deployment'}><defs><linearGradient id="air-chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#e38366" stopOpacity=".25"/><stop offset="100%" stopColor="#e38366" stopOpacity="0"/></linearGradient></defs><path d={recovered ? 'M0 15L30 20L60 12L90 38L120 65L150 72L180 73L210 70L240 74L280 73L280 90L0 90Z' : 'M0 77L30 76L60 78L85 73L102 76L120 30L137 45L155 17L176 26L194 12L215 19L234 10L256 16L280 12L280 90L0 90Z'} fill="url(#air-chart-fill)"/><path d={recovered ? 'M0 15L30 20L60 12L90 38L120 65L150 72L180 73L210 70L240 74L280 73' : 'M0 77L30 76L60 78L85 73L102 76L120 30L137 45L155 17L176 26L194 12L215 19L234 10L256 16L280 12'} fill="none" stroke={recovered ? '#16846d' : '#cc6749'} strokeWidth="2.5"/><path d="M0 65H280" stroke="#9ba9ac" strokeDasharray="4 4" /></svg><div className="air-chart-labels"><span>09:30</span><span>2% threshold</span><span>10:00</span></div><div className="air-health-footer"><span>Latency p95<strong>{recovered ? '240 ms' : '4.2 s'}</strong></span><span>Error budget burn<strong>{recovered ? '0.6×' : '25.6×'}</strong></span></div></div>
        <div className="air-card air-timeline"><div className="air-section-title"><h3>Activity</h3><span className="air-secondary">UTC</span></div>{[['09:38', 'Deployment v2.18.0', 'Configuration updated'], ['09:42', 'Error threshold breached', '8 related alerts grouped'], ['09:43', 'Incident and Slack channel created', '#air-inc-2048 · simulated provisioning'], ['09:44', analysisStep < 4 ? 'Investigation in progress' : 'Evidence collected', analysisStep < 4 ? `${analysisStep}/4 simulated checks complete` : '4 sources investigated'], ...(unlocked >= 1 ? [['09:46', 'RCA reviewed', 'Pool saturation suspected']] : []), ...(approved ? [['09:49', 'Simulation approved', 'Sam Chen · approval recorded']] : []), ...(recovered ? [['10:00', 'Recovery verified', 'Simulation · checks passed']] : [])].map(([time,title,desc]) => <div className="air-event" key={time}><span className="air-event-dot"/><div><time>{time}</time><strong>{title}</strong><p>{desc}</p></div></div>)}</div><div className="air-trust"><ShieldOutlined /><p><strong>Evidence before action.</strong><br/>AIR recommends. Your team stays in control.</p></div></aside></div>
        </>}
        <footer className="air-footer">AIR / Agentic Incident Response<span>Prototype · synthetic data · no production access</span></footer>
      </main>
    </div>
    <Dialog open={detail && analysisStep < 4} disableRestoreFocus aria-labelledby="analysis-dialog-title" maxWidth="md" fullWidth slotProps={{paper:{className:'air-prototype air-analysis-modal',sx:{minHeight:0}}}}><DialogTitle component="div" id="analysis-dialog-title"><span className="air-eyebrow">INC-2048 · INVESTIGATION</span><h2>Investigation analysis in progress</h2></DialogTitle><DialogContent><p>AIR is analyzing checkout-api. The incident workspace will open automatically when the checks finish.</p><section className="air-run-panel" aria-label="Investigation progress"><div className="air-section-title"><h3>{['Reviewing incident context','Collecting telemetry evidence','Evaluating competing causes','Preparing key findings'][analysisStep] || 'Analysis complete'}</h3><span className="ops-status investigating">{analysisStep}/4 complete</span></div><LinearProgress variant="determinate" value={analysisStep*25} aria-label="Investigation completion"/><ol className="air-run-steps">{['Review incident context','Collect telemetry evidence','Evaluate competing causes','Prepare key findings'].map((label,i)=><li key={label} className={i<analysisStep?'complete':i===analysisStep?'running':''}><span>{i<analysisStep?'✓':i+1}</span><div>{label}<small>{i<analysisStep?'Complete':i===analysisStep?'In progress':'Pending'}</small></div></li>)}</ol><div className="air-run-footer" role="status">{analysisStep} of 4 checks complete · Simulated read-only analysis</div></section></DialogContent><DialogActions><Button onClick={()=>{setDetail(false);setNav('Incidents');}}>Back to incidents</Button></DialogActions></Dialog>
    <Dialog open={selectedEvidence !== null} onClose={() => setSelectedEvidence(null)} maxWidth="sm" fullWidth><DialogTitle>{selectedEvidence !== null && evidence[selectedEvidence].title}</DialogTitle><DialogContent>{selectedEvidence !== null && <><Chip label={`${evidence[selectedEvidence].id} · ${evidence[selectedEvidence].type}`} size="small"/><p>{evidence[selectedEvidence].source}</p><p>{evidence[selectedEvidence].detail}</p><p><strong>{evidence[selectedEvidence].state}</strong></p><p>Synthetic evidence for product demonstration. Production evidence must include the source query, immutable capture, and freshness.</p></>}</DialogContent><DialogActions><Button onClick={() => setSelectedEvidence(null)}>Close evidence</Button></DialogActions></Dialog>
    <Dialog open={approvalOpen} onClose={() => setApprovalOpen(false)} maxWidth="sm" fullWidth><DialogTitle>Approve simulated recovery</DialogTitle><DialogContent><p>Restore checkout-api v2.17.4 in us-east-1. Medium risk; one canary before regional rollout. This prototype performs no infrastructure changes.</p><TextField autoFocus fullWidth multiline minRows={2} label="Approval reason" value={reason} onChange={e => setReason(e.target.value)} /><p>Approval applies only to this simulated plan. A production plan change must invalidate approval.</p></DialogContent><DialogActions><Button onClick={() => setApprovalOpen(false)}>Cancel</Button><Button variant="contained" disabled={!reason.trim()} onClick={() => { setApproved(true); setApprovalOpen(false); }}>Approve simulation</Button></DialogActions></Dialog>
    {note && <div className="air-toast" role="status">{note}<button aria-label="Dismiss notification" onClick={() => setNote('')}><CloseRounded fontSize="small" /></button></div>}
  </div></ThemeProvider>;
}
