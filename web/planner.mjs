import {estimateFuel} from './v2calc.mjs';
import {calculate,PHASES} from './calc.mjs';
import {venueSupply,supplySummary} from './supply.mjs';
import {getLanguage,translate as t} from './i18n.mjs';

export const normalizeView=value=>value==='advanced'?'advanced':'basic';
export function groupedUnits(project){
  const groups=new Map();
  for(const unit of project.units||[])groups.set(unit.equipment_id,(groups.get(unit.equipment_id)||0)+1);
  return [...groups].map(([id,quantity])=>({id,quantity}));
}
export function setQuantity(project,catalogue,id,quantity){
  if(!Number.isInteger(quantity)||quantity<0||quantity>300)throw Error('Enter a whole quantity between 0 and 300.');
  if(quantity>0&&![...catalogue,...(project.custom_equipment||[])].some(e=>e.id===id))throw Error('Equipment profile is missing.');
  const current=project.units.filter(u=>u.equipment_id===id).length;
  if(project.units.length-current+quantity>300)throw Error('A project can contain at most 300 cabinets.');
  if(quantity<current){
    let remove=current-quantity;
    for(let i=project.units.length-1;i>=0&&remove;i--)if(project.units[i].equipment_id===id){project.units.splice(i,1);remove--;}
  }
  for(let n=current;n<quantity;n++){
    const result=calculate(project,catalogue);
    const phase=[...PHASES].sort((a,b)=>result.phases[a].design_va-result.phases[b].design_va)[0];
    project.units.push({equipment_id:id,phase});
  }
}
export function inputConfidence(project,catalogue){
  const profiles=new Map([...catalogue,...(project.custom_equipment||[])].map(e=>[e.id,e]));
  const counts={verified:0,mixed:0,estimated:0,missing:0};
  for(const unit of project.units||[]){
    const profile=profiles.get(unit.equipment_id);
    if(!profile)counts.missing++;
    else if(profile.confidence==='verified')counts.verified++;
    else if(profile.confidence==='mixed')counts.mixed++;
    else counts.estimated++;
  }
  return counts;
}
export function supplyRequest(project,catalogue){
  const confidence=inputConfidence(project,catalogue);
  if(!(project.units||[]).length||confidence.missing)throw Error('Add valid equipment profiles before preparing a supply request.');
  const r=calculate(project,catalogue),v=venueSupply(project,r);
  const fmt=(n,d=1)=>Number(n).toLocaleString(getLanguage()==='nl'?'nl-NL':'en-GB',{minimumFractionDigits:d,maximumFractionDigits:d});
  const profiles=new Map([...catalogue,...(project.custom_equipment||[])].map(e=>[e.id,e]));
  const lines=['Power supply request',`Project: ${project.name}`,`Duration: ${r.duration} h`];
  const mode={generator:'Generator-only',battery:'Battery-only',hybrid:'Hybrid'}[project.power_mode]||'Generator-only';
  lines.push(project.setup_mode==='fixed'?`Fallback power source: ${mode}`:`Power source: ${mode}`);
  if(project.power_mode==='hybrid')lines.push('Hybrid operation requires supplier approval; the capacities cannot simply be added.');
  if(project.setup_mode==='fixed')lines.push('Setup: Fixed / venue',supplySummary(project,r)[5],supplySummary(project,r)[6]);
  else{
    lines.push('Setup: Mobile');
    if(project.power_mode!=='battery')lines.push(`Generator request: at least ${r.suggestedKVA} kVA prime rating, subject to supplier confirmation.`);
  }
  lines.push(`Planned electrical load: ${fmt(r.designVA/1000,2)} kVA / ${fmt(r.designKW,2)} kW before reserve.`);
  lines.push(`Dedicated supply including reserve: ${fmt(v.requiredKVA,2)} kVA / ${fmt(v.requiredKW,2)} kW at ${v.voltage} V phase-to-neutral.`);
  lines.push(...PHASES.map(p=>`${p}: ${fmt(v.requiredA[p])} A including planning reserve.`));
  if(r.usesBattery)lines.push(`Battery requirement: ${fmt(r.batteryNominalKWh)} kWh nominal; inverter planning capacity at least ${fmt(r.requiredVA/1000)} kVA. Supplier must confirm phase and transient limits.`);
  if(project.power_mode!=='battery'){
    const fuel=estimateFuel(project,r.averageKW);
    lines.push(r.fuelLitres!==null?`Fuel allowance: ${fmt(r.fuelLitres)} L before reserve at the entered constant rate.`:
      fuel.status==='estimated'?`Fuel allowance: ${fmt(fuel.litres)} L before reserve from the supplier curve.`:
      'Fuel quantity is unconfirmed; obtain the supplier consumption estimate.');
  }
  const c=inputConfidence(project,catalogue);
  lines.push(`Input confidence: ${c.verified} verified, ${c.mixed} partly supported, ${c.estimated} estimated, ${c.missing} missing profiles.`);
  if(project.meter_summary)lines.push('A measured programme log is attached. Confirm that it matches this equipment; high-load values still require verification.');
  lines.push('Equipment:');
  // Keep project and equipment names exactly as entered.
  const translated=lines.map((line,i)=>i===1?'Project: '+project.name:t(line));
  translated.push(...groupedUnits(project).map(g=>`${g.quantity} × ${profiles.get(g.id)?.name||g.id}`));
  translated.push(t('Please confirm dedicated capacity after other loads, connectors, phase allocation, earthing, protection and transient capability. This is a planning request, not installation approval.'));
  return translated.join('\n')+'\n';
}
