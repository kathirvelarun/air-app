export type AirRole = 'SRE Engineer' | 'Incident Commander';
export const canManage = (role: AirRole) => role === 'Incident Commander';
export type SystemConfig = {id:string;name:string;owner:string;environment:string;slackPrefix:string};
export const defaultSystems:SystemConfig[] = [
 {id:'checkout-api',name:'Checkout API',owner:'Payments platform',environment:'Production',slackPrefix:'air-inc'},
 {id:'refund-worker',name:'Refund worker',owner:'Payments platform',environment:'Production',slackPrefix:'air-refund'},
 {id:'payment-gateway',name:'Payment gateway',owner:'Payments platform',environment:'Production',slackPrefix:'air-payments'},
 {id:'inventory-api',name:'Inventory API',owner:'Commerce platform',environment:'Production',slackPrefix:'air-inventory'},
];
export type ReportingIncident = {id:string;service:string;status:string;openedAt:string;severity:string;title:string;owner:string};
export function reportRows<T extends ReportingIncident>(rows:T[], system:string, status:string, from:string, to:string):T[] {
 if(from&&to&&from>to) return [];
 return rows.filter(r=>(system==='All'||r.service===system)&&(status==='All'||r.status===status)&&(!from||r.openedAt.slice(0,10)>=from)&&(!to||r.openedAt.slice(0,10)<=to));
}
export function groupReport(rows:ReportingIncident[],groupBy:'System'|'Status'|'Date') {
 const groups=new Map<string,{label:string;total:number;resolved:number;open:number}>();
 for(const row of rows){const label=groupBy==='System'?row.service:groupBy==='Status'?row.status:row.openedAt.slice(0,10);const group=groups.get(label)||{label,total:0,resolved:0,open:0};group.total++;if(row.status==='Resolved')group.resolved++;else group.open++;groups.set(label,group);}
 return [...groups.values()].sort((a,b)=>a.label.localeCompare(b.label));
}
export function csvCell(value:string){const safe=/^[=+\-@\t\r]/.test(value)?`'${value}`:value;return '"'+safe.replaceAll('"','""')+'"';}
