export type LeadershipIncident={id:string;service:string;status:string;openedAt:string;resolvedAt:string|null};
export function leadershipMetrics(rows:LeadershipIncident[],from:string,to:string){
 const start=Date.parse(from+'T00:00:00Z'),end=Date.parse(to+'T00:00:00Z')+86400000;
 if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start||end-start>93*86400000)return null;
 const opened=rows.filter(r=>Date.parse(r.openedAt)>=start&&Date.parse(r.openedAt)<end);
 const cleared=rows.filter(r=>r.resolvedAt&&Date.parse(r.resolvedAt)>=start&&Date.parse(r.resolvedAt)<end);
 const backlogAt=(at:number)=>rows.filter(r=>Date.parse(r.openedAt)<at&&(!r.resolvedAt||Date.parse(r.resolvedAt)>=at)).length;
 const days=[];for(let time=start;time<end;time+=86400000){days.push({date:new Date(time).toISOString().slice(0,10),opened:rows.filter(r=>Date.parse(r.openedAt)>=time&&Date.parse(r.openedAt)<time+86400000).length,cleared:rows.filter(r=>r.resolvedAt&&Date.parse(r.resolvedAt)>=time&&Date.parse(r.resolvedAt)<time+86400000).length,backlog:backlogAt(time+86400000)});}
 const resolvedCohort=opened.filter(r=>r.resolvedAt&&Date.parse(r.resolvedAt)<end).length;
 const durations=cleared.map(r=>(Date.parse(r.resolvedAt!)-Date.parse(r.openedAt))/60000);
 return {opened:opened.length,cleared:cleared.length,backlogStart:backlogAt(start),backlogEnd:backlogAt(end),clearanceRate:opened.length?resolvedCohort/opened.length*100:null,meanMinutes:durations.length?durations.reduce((a,b)=>a+b,0)/durations.length:null,days};
}
