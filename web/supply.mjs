import {PHASES} from './calc.mjs';

// Venue supply is checked directly in amps; generator power factor is unrelated.
export function venueSupply(project,result){
  const margin=1+Math.max(0,Number(project.headroom_pct)||0)/100;
  const voltage=Math.max(1,Number(project.voltage_v)||230);
  const requiredA=Object.fromEntries(PHASES.map(p=>[p,result.phases[p].design_va*margin/voltage]));
  const availableA=Object.fromEntries(PHASES.map(p=>{
    const raw=project.venue_supply?.[p];
    return [p,raw==null||raw===''||!Number.isFinite(Number(raw))||Number(raw)<0?null:Number(raw)];
  }));
  const short=PHASES.some(p=>availableA[p]!==null && availableA[p]<requiredA[p]);
  const unknown=PHASES.some(p=>availableA[p]===null);
  return {requiredA,availableA,voltage,requiredKVA:result.designVA*margin/1000,
    requiredKW:result.designKW*margin,status:short?'insufficient':unknown?'unknown':'covered'};
}
export function supplySummary(project,result){
  if(project.setup_mode!=='fixed')return ['Setup: Mobile'];
  const v=venueSupply(project,result);
  return ['Setup: Fixed / venue',
    `Venue requirement: ${v.requiredKVA.toFixed(2)} kVA / ${v.requiredKW.toFixed(2)} kW including headroom, three-phase with neutral and protective earth at ${v.voltage} V phase-to-neutral.`,
    ...PHASES.map(p=>`${p}: require ${v.requiredA[p].toFixed(1)} A; venue available ${v.availableA[p]===null?'not confirmed':v.availableA[p]+' A'}`),
    `Venue assessment: ${v.status==='covered'?'Entered supply covers the numerical planning envelope; electrician confirmation required.':v.status==='insufficient'?'Venue supply is insufficient. Arrange a generator or reduce/rebalance the load.':'Venue supply is not fully confirmed. Confirm with the venue or arrange a generator.'}`,
    `Generator fallback: ${result.suggestedKVA} kVA minimum suggested class; selected ${result.selectedKVA} kVA ${result.generatorOK?'covers':'is below'} the generator planning envelope.`,
    'Dedicated capacity must remain available after other venue loads. Confirm connectors, distribution, protection and transient capability with the venue electrician. Generator fallback is a separate source; do not parallel with venue mains.'];
}
