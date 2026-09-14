export const incidentRows = [
  {id:'INC-2048',openedAt:'2026-09-07T09:43:00Z',slackChannel:'air-inc-2048',title:'Elevated error rate on checkout-api',service:'checkout-api',severity:'SEV 1',status:'Investigating',time:'Today, 09:43',duration:'3 min',owner:'Sam Chen',summary:'Pool saturation followed a deployment configuration change. Four sources are available for causal assessment.'},
  {id:'INC-2047',openedAt:'2026-09-07T09:31:00Z',slackChannel:'air-inc-2047',title:'Refund webhook backlog above threshold',service:'refund-worker',severity:'SEV 2',status:'Declared',time:'Today, 09:31',duration:'15 min',owner:'Maya Patel',summary:'3,412 refund webhooks are pending delivery. The worker owner is reviewing queue age and retry volume; cause is not yet established.'},
  {id:'INC-2045',openedAt:'2026-09-07T09:02:00Z',slackChannel:'air-inc-2045',title:'Payment provider response latency',service:'payment-gateway',severity:'SEV 2',status:'Monitoring',time:'Today, 09:02',duration:'44 min',owner:'Alex Rivera',summary:'Provider latency returned to baseline after traffic was rebalanced. The team is observing the recovery window before resolution.'},
  {id:'INC-2039',openedAt:'2026-09-06T16:20:00Z',slackChannel:'air-inc-2039',title:'Inventory cache refresh failure',service:'inventory-api',severity:'SEV 3',status:'Resolved',time:'Yesterday, 16:20',duration:'12 min',owner:'Alex Rivera',summary:'A cache refresh job failed following a scheduler change. Restoring the schedule recovered freshness. The reviewed sample report assigns a scheduler contract test to Platform and a freshness alert to the service owner.'},
];
export function filterRows<T extends {severity:string;status:string}>(rows:T[], query:string, status:string, severity:string):T[] {
  const search=query.trim().toLowerCase();
  return rows.filter(row=>(status==='All'||row.status===status)&&(severity==='All'||row.severity===severity)&&(!search||Object.values(row).some(value=>String(value).toLowerCase().includes(search))));
}

export type AlertEvent = {eventId:string;incidentId:string;fingerprint:string;title:string;source:string;service:string;environment:string;region:string;severity:string;observedAt:string;instance:string};
export function groupAlertEvents(events:AlertEvent[]) {
  const seen = new Set<string>();
  const groups = new Map<string, AlertEvent & {id:string;occurrences:AlertEvent[];searchText:string}>();
  for (const event of events) {
    const eventKey = `${event.source}:${event.eventId}`;
    if (seen.has(eventKey)) continue;
    seen.add(eventKey);
    const key = JSON.stringify([event.incidentId,event.fingerprint,event.service,event.environment,event.region,event.source]);
    const existing = groups.get(key);
    if (existing) { existing.occurrences.push(event); existing.searchText += ` ${event.eventId} ${event.instance} ${event.observedAt}`; }
    else groups.set(key,{...event,id:key,occurrences:[event],searchText:`${event.eventId} ${event.instance} ${event.observedAt}`});
  }
  return [...groups.values()];
}
export const alertEvents:AlertEvent[] = [
  ['ALT-8101','checkout-5xx','Checkout 5xx error rate above 2%','Prometheus','SEV 1','09:42:00','checkout-01'],
  ['ALT-8105','checkout-5xx','Checkout 5xx error rate above 2%','Prometheus','SEV 1','09:42:30','checkout-02'],
  ['ALT-8102','connection-timeout','Connection acquisition timeout','Application logs','SEV 1','09:42:10','checkout-01'],
  ['ALT-8106','connection-timeout','Connection acquisition timeout','Application logs','SEV 1','09:43:10','checkout-02'],
  ['ALT-8103','checkout-p95','Checkout p95 latency above 500 ms','OpenTelemetry','SEV 2','09:42:15','checkout-01'],
  ['ALT-8107','checkout-p95','Checkout p95 latency above 500 ms','OpenTelemetry','SEV 2','09:43:15','checkout-02'],
  ['ALT-8108','checkout-p95','Checkout p95 latency above 500 ms','OpenTelemetry','SEV 2','09:44:15','checkout-03'],
  ['ALT-8104','pool-capacity','Connection pool at capacity','Prometheus','SEV 2','09:42:20','checkout-01'],
].map(([eventId,fingerprint,title,source,severity,observedAt,instance])=>({eventId,fingerprint,title,source,severity,observedAt,instance,incidentId:'INC-2048',service:'checkout-api',environment:'Production',region:'us-east-1'}));
