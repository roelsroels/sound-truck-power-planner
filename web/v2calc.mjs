/** V2 pure planning helpers. No cable sizing or generator transient certification. */
const numeric=value=>Number.isFinite(Number(value))?Number(value):NaN;
const rounded=(value,digits=3)=>Number(value.toFixed(digits));

/** CSV schema: timestamp,l1_kw,l2_kw,l3_kw; positive real-power meter readings. */
export function parseMeterCSV(csv){
  if(typeof csv!=='string'||csv.length>1000000)throw Error('CSV exceeds 1 MB');
  const lines=csv.replace(/^\uFEFF/,'').trim().split(/\r?\n/).filter(x=>x.trim());
  if(lines.length<3||lines.length>5001)throw Error('CSV requires 2–5000 readings');
  const header=lines.shift().split(',').map(s=>s.trim().toLowerCase());
  if(header.join(',')!=='timestamp,l1_kw,l2_kw,l3_kw')
    throw Error('Required header: timestamp,l1_kw,l2_kw,l3_kw');
  let first=null,last=null,previous=null,energy=0,peak=0,phasePeak=[0,0,0],largestGap=0;
  for(const [i,line] of lines.entries()){
    const fields=line.split(',').map(x=>x.trim());
    if(fields.length!==4)throw Error('Row '+(i+2)+': expected four columns');
    // Require explicit timezone to avoid browser-local ambiguity.
    if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:Z|[+-]\d\d:\d\d)$/.test(fields[0]))
      throw Error('Row '+(i+2)+': timestamp needs ISO 8601 timezone');
    const t=Date.parse(fields[0]);
    if(!Number.isFinite(t))throw Error('Row '+(i+2)+': invalid timestamp');
    const p=fields.slice(1).map(numeric);
    if(p.some(x=>!Number.isFinite(x)||x<0||x>1000))
      throw Error('Row '+(i+2)+': phase kW must be between 0 and 1000');
    if(previous){
      const h=(t-previous.t)/3600000;
      if(h<=0)throw Error('Readings must be strictly chronological');
      largestGap=Math.max(largestGap,h);
      if(h>1)throw Error('More than one hour between samples; split measurement files');
      energy+=h*(p.reduce((a,b)=>a+b,0)+previous.total)/2;
    } else first=t;
    const total=p.reduce((a,b)=>a+b,0);
    peak=Math.max(peak,total);
    p.forEach((v,j)=>phasePeak[j]=Math.max(phasePeak[j],v));
    previous={t,total};last=t;
  }
  const hours=(last-first)/3600000;
  if(hours<=0)throw Error('Measurements need more than one unique timestamp');
  return {
    samples:lines.length,minutes:rounded(hours*60,1),average_kw:rounded(energy/hours),
    observed_peak_kw:rounded(peak),energy_kwh:rounded(energy),
    phase_peak_kw:phasePeak.map(x=>rounded(x)),largest_gap_min:rounded(largestGap*60,1),
    start:new Date(first).toISOString(),end:new Date(last).toISOString(),
    kind:'measured-ac-real-power',source:'user-uploaded-csv'
  };
}

export function estimateFuel(project,averageKW){
  const points=[25,50,75,100],curve=project.generator_fuel_curve;
  if(!curve)return {status:'missing'};
  const values=points.map(p=>numeric(curve['p'+p]));
  if(values.some(v=>!Number.isFinite(v)||v<=0||v>1000))return {status:'incomplete'};
  if(values.some((v,i)=>i>0&&v<values[i-1]))return {status:'non-monotonic'};
  const genKW=numeric(project.generator_kva)*numeric(project.generator_pf);
  if(!Number.isFinite(genKW)||genKW<=0)return {status:'invalid-rating'};
  const percentage=100*numeric(averageKW)/genKW;
  if(!Number.isFinite(percentage)||percentage<25)return {status:'below-25',load_pct:rounded(percentage,1)};
  if(percentage>100)return {status:'overload',load_pct:rounded(percentage,1)};
  let j=1;while(j<points.length-1 && percentage>points[j])j++;
  const ratio=(percentage-points[j-1])/(points[j]-points[j-1]);
  const lph=values[j-1]+ratio*(values[j]-values[j-1]);
  const duration=numeric(project.duration_h);
  return {
    status:'estimated',load_pct:rounded(percentage,1),lph:rounded(lph,2),
    litres:rounded(lph*Math.max(0,duration),1),method:'linear interpolation',
    source:String(curve.source||'User-entered generator fuel data').slice(0,180)
  };
}

/** Advisory only: source assembly approval, cable ampacity and fault protection remain external. */
export function provisionalCircuits(project,catalogue){
  const profiles=new Map([...catalogue,...(project.custom_equipment||[])].map(e=>[e.id,e]));
  return (project.units||[]).map((u,i)=>{
    const e=profiles.get(u.equipment_id)||{};
    const voltage=Number(project.voltage_v)||230;
    return {index:i,name:e.name||'Missing equipment',phase:u.phase||'L1',
      estimated_a:rounded(Math.max(0,Number(e.design_va)||0)/voltage,1)};
  });
}
