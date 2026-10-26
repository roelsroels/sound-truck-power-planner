/** Pure, auditable planning arithmetic. NOT an electrical certification or protection design. */
export const PHASES=['L1','L2','L3'];
export const GENERATORS=[10,15,20,25,30,40,50,60,80,100,125,150,200,250,300,400,500];
export const finite=(n,fallback=0)=>Number.isFinite(Number(n)) ? Number(n) : fallback;
export const nonnegative=(n,fallback=0)=>Math.max(0,finite(n,fallback));

export function calculate(project,catalogue){
  const byId=new Map([...catalogue,...(project.custom_equipment||[])].map(e=>[e.id,e]));
  const phases={L1:{reference_va:0,design_va:0,units:[]},L2:{reference_va:0,design_va:0,units:[]},L3:{reference_va:0,design_va:0,units:[]}};
  const unknown=[];
  let referenceVA=0,designVA=0, referenceKW=0, designKW=0, weight=0, unknownWeights=0,knownFootprint=0,unknownFootprint=0;
  for (const [i,u] of (project.units||[]).entries()) {
    const e=byId.get(u.equipment_id);
    if(!e){unknown.push(`Equipment missing from catalogue: ${u.equipment_id}`);continue;}
    const phase=PHASES.includes(u.phase)?u.phase:'L1';
    const ref=nonnegative(e.reference_va),peak=nonnegative(e.design_va),pf=Math.min(1,Math.max(.01,finite(e.power_factor,.95)));
    referenceVA+=ref; designVA+=peak; referenceKW+=ref*pf/1000;designKW+=peak*pf/1000;
    phases[phase].reference_va+=ref;phases[phase].design_va+=peak;
    phases[phase].units.push({index:i, equipment:e});
    if(e.weight_kg==null || e.weight_kg===''){unknownWeights++;} else {weight+=nonnegative(e.weight_kg);}
    if(e.width_m==null||e.depth_m==null){unknownFootprint++;}else{knownFootprint+=nonnegative(e.width_m)*nonnegative(e.depth_m);}
    if (peak<ref) unknown.push(`${e.name}: high-load allowance is below reference demand`);
    if(e.confidence!=='verified') unknown.push(`${e.name}: has ${e.confidence||'unverified'} data`);
  }
  const voltage=Math.max(1,finite(project.voltage_v,230));
  const headroom=Math.max(1,1+finite(project.headroom_pct,25)/100);
  const genPF=Math.max(.01,Math.min(1,finite(project.generator_pf,.8)));
  const maxPhaseVA=Math.max(...PHASES.map(p=>phases[p].design_va));
  // Independent checks: total apparent load; real-power capability at generator rating;
  // per-phase imbalance with a small design margin. Manufacturer alternator limits still apply.
  const requiredVA=Math.max(designVA*headroom, (designKW*1000/genPF)*headroom, maxPhaseVA*3*1.10);
  const suggestedKVA=GENERATORS.find(k=>k*1000>=requiredVA)??Math.ceil(requiredVA/50000)*50;
  const selectedKVA=nonnegative(project.generator_kva,40);
  const maxPhaseAvailableVA=selectedKVA*1000/3;
  const generatorOK=selectedKVA*1000>=requiredVA;
  const duration=nonnegative(project.duration_h,8);
  const multiplier=Math.max(.1,finite(project.program_multiplier,1));
  const usable=Math.max(.01,Math.min(1,finite(project.battery_use_fraction,.8)));
  const efficiency=Math.max(.01,Math.min(1,finite(project.inverter_efficiency,.92)));
  const averageKW=referenceKW*multiplier;
  const batteryNominalKWh=averageKW*duration/(usable*efficiency);
  const batteryInstalled=nonnegative(project.battery_installed_kwh,0);
  const inverterKVA=nonnegative(project.inverter_kva,0);
  const batteryRuntimeH=averageKW>0 ? batteryInstalled*usable*efficiency/averageKW : null;
  const inverterCapacityOK=inverterKVA*1000>=requiredVA;
  const estimatedFuelLPH=project.fuel_rate_lph==null || project.fuel_rate_lph==='' ? null : nonnegative(project.fuel_rate_lph);
  const fuelLitres=estimatedFuelLPH===null?null:estimatedFuelLPH*duration;
  const payload=project.vehicle?.payload_kg;
  const v=project.vehicle||{};
  const sourceWeightFields=['generator_weight_kg','battery_weight_kg','other_weight_kg'];
  const knownSourceWeight=sourceWeightFields.reduce((sum,key)=>sum+(v[key]==null || v[key]===''?0:nonnegative(v[key])),0);
  const totalKnownWeight=weight+knownSourceWeight;
  const unknownSourceWeights=sourceWeightFields.filter(key=>v[key]==null||v[key]==='').length;
  const payloadRemaining=(payload===null||payload===undefined||payload==='')?null:nonnegative(payload)-totalKnownWeight;
  const deckArea=(project.vehicle?.deck_length_m>0&&project.vehicle?.deck_width_m>0)?Number(project.vehicle.deck_length_m)*Number(project.vehicle.deck_width_m):null;
  return {phases,referenceVA,designVA,referenceKW,designKW,requiredVA,suggestedKVA,selectedKVA,
    generatorOK,maxPhaseAvailableVA,totalCurrentEquivalentA:designVA/(3*voltage),
    duration,averageKW,batteryNominalKWh,batteryInstalled,batteryRuntimeH,inverterKVA,inverterCapacityOK,
    fuelLitres,estimatedFuelLPH,weight,knownSourceWeight,totalKnownWeight,unknownSourceWeights,
    unknownWeights,deckArea,knownFootprint,unknownFootprint,payloadRemaining,
    phaseCurrents:Object.fromEntries(PHASES.map(p=>[p,phases[p].design_va/voltage])),warnings:[...new Set(unknown)]};
}
