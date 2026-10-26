import {calculate, PHASES, GENERATORS} from './calc.mjs';
import {venueSupply,supplySummary} from './supply.mjs';
import {initV2,renderV2} from './v2.mjs';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,dp=1)=>Number(v).toLocaleString('en-GB',{maximumFractionDigits:dp,minimumFractionDigits:dp});
const get=(o,k,d)=>o?.[k]??d;
const safeURL=u=>/^https?:\/\/[^\s]+$/i.test(u||'')?u:null;
const createId=()=> 'user-'+(globalThis.crypto?.randomUUID?.()??Date.now().toString(36)).toLowerCase();
let catalogue=[],example=null,project=null,editingUnitIndex=null;
function notify(message){$('notice').textContent=message;setTimeout(()=>{if($('notice').textContent===message)$('notice').textContent='';},6000)}
function update(prop,value){project[prop]=value;render();}
function dateNumber(id,pathFn,key,nullWhenEmpty=false){const el=$(id);el.addEventListener('change',()=>{const raw=el.value;pathFn()[key]=(nullWhenEmpty&&raw==='')?null:Number(raw);render()})}
function bind(){
  $('setupMode').addEventListener('change',e=>update('setup_mode',e.target.value));
  for(const phase of PHASES)dateNumber('venue'+phase,()=>project.venue_supply??={},phase,true);
  $('save').addEventListener('click',()=>{localStorage.setItem('soundtruck.project.v1',JSON.stringify(project));notify('Project saved in this browser.')});
  $('export').addEventListener('click',()=>download(`${fileBase()}.json`,JSON.stringify(project,null,2),'application/json'));
  $('import').addEventListener('click',()=>$('importfile').click());
  $('importfile').addEventListener('change',async e=>{const file=e.target.files[0];if(!file)return;try{const next=JSON.parse(await file.text());validateProject(next);project=next;populateControls();render();notify('Imported project. Save it if you want it retained.')}catch(e){notify('Import failed: '+e.message)}e.target.value=''});
  $('reset').addEventListener('click',()=>{if(!confirm('Reset this project to the original test configuration?'))return;project=structuredClone(example);populateControls();render();notify('Example restored (not yet saved).')});
  $('downloadPDF').addEventListener('click',async ()=>{
    const button=$('downloadPDF');button.disabled=true;button.textContent='Preparing PDF…';
    try{
      const response=await fetch('/api/v1/reports/engineering.pdf',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({project,equipment:allEquipment().filter(e=>project.units.some(u=>u.equipment_id===e.id))})
      });
      if(!response.ok)throw Error('Report service returned HTTP '+response.status);
      downloadBlob(`${fileBase()}-engineering.pdf`,await response.blob());
      notify('Engineering PDF prepared.');
    }catch(error){notify('PDF export failed: '+error.message)}
    finally{button.disabled=false;button.textContent='Download engineering PDF'}
  });
  $('downloadSummary').addEventListener('click',()=>download(`${fileBase()}-summary.txt`,summary(),'text/plain'));
  $('projectName').addEventListener('input',e=>{project.name=e.target.value});
  dateNumber('duration',()=>project,'duration_h');dateNumber('programMultiplier',()=>project,'program_multiplier');
  dateNumber('batteryInstalled',()=>project,'battery_installed_kwh');
  dateNumber('inverterKVA',()=>project,'inverter_kva');
  dateNumber('fuelRate',()=>project,'fuel_rate_lph',true);
  $('powerMode').addEventListener('change',e=>update('power_mode',e.target.value));
  dateNumber('generatorWeight',()=>project.vehicle,'generator_weight_kg',true);
  dateNumber('batteryWeight',()=>project.vehicle,'battery_weight_kg',true);
  dateNumber('otherWeight',()=>project.vehicle,'other_weight_kg',true);
  dateNumber('generatorPF',()=>project,'generator_pf');dateNumber('headroom',()=>project,'headroom_pct');
  dateNumber('voltage',()=>project,'voltage_v');dateNumber('batteryFraction',()=>project,'battery_use_fraction');dateNumber('inverterEfficiency',()=>project,'inverter_efficiency');
  $('generatorRating').addEventListener('change',e=>update('generator_kva',Number(e.target.value)));
  $('vehicleType').addEventListener('input',e=>project.vehicle.type=e.target.value);
  dateNumber('deckLength',()=>project.vehicle,'deck_length_m',true);dateNumber('deckWidth',()=>project.vehicle,'deck_width_m',true);
  dateNumber('payload',()=>project.vehicle,'payload_kg',true);
  $('addEquipment').addEventListener('click',()=>{const equipment_id=$('equipmentType').value;if(!equipment_id)return;const calc=calculate(project,catalogue);const phase=[...PHASES].sort((a,b)=>calc.phases[a].design_va-calc.phases[b].design_va)[0];project.units.push({equipment_id,phase});render();});
  $('balancePhases').addEventListener('click',()=>{
    const items=new Map(allEquipment().map(e=>[e.id,e]));
    const loads={L1:0,L2:0,L3:0};
    const ranked=project.units.map((u,i)=>({i,va:Number(items.get(u.equipment_id)?.design_va)||0})).sort((a,b)=>b.va-a.va);
    for(const item of ranked){const phase=[...PHASES].sort((a,b)=>loads[a]-loads[b])[0];project.units[item.i].phase=phase;loads[phase]+=item.va;}
    render();notify('Phases reallocated by high-load allowance. Validate real currents.');
  });
  $('customForm').addEventListener('submit',e=>{e.preventDefault();const form=new FormData(e.target);const value=k=>String(form.get(k)||'').trim();const optional=k=>value(k)===''?null:Number(value(k));const item={id:createId(),name:value('name'),category:value('category'),drivers:value('drivers'),amplifier:value('amplifier'),reference_va:Number(value('reference_va')),design_va:Number(value('design_va')),power_factor:Number(value('power_factor')),weight_kg:optional('weight_kg'),width_m:optional('width_m'),depth_m:optional('depth_m'),source_url:value('source_url'),reference_basis:'User-entered reference estimate',design_basis:value('design_basis')||'User-entered high-load estimate',confidence:'estimate'};
    if(!Number.isFinite(item.reference_va)||!Number.isFinite(item.design_va)||item.design_va<item.reference_va){notify('High-load allowance must be at least the reference VA.');return}
    project.custom_equipment??=[];project.custom_equipment.push(item);
    if(editingUnitIndex!==null){project.units[editingUnitIndex].equipment_id=item.id;}
    else{project.units.push({equipment_id:item.id,phase:'L1'});}
    const wasEditing=editingUnitIndex!==null;
    editingUnitIndex=null;$('customForm').reset();$('customFormWrap').open=false;
    $('customFormWrap').querySelector('summary').textContent='Add a custom cabinet / amplifier profile';
    render();notify(wasEditing?'Cabinet profile customised for this project.':'Custom cabinet added to this project.');
  });
  $('unitList').addEventListener('change',e=>{const s=e.target.closest('[data-phase]');if(!s)return;const i=Number(s.dataset.phase);if(PHASES.includes(s.value)){project.units[i].phase=s.value;render()}});
  $('unitList').addEventListener('click',e=>{
    const edit=e.target.closest('[data-edit]');
    if(edit){
      const i=Number(edit.dataset.edit),unit=project.units[i],item=allEquipment().find(x=>x.id===unit.equipment_id);
      if(!item)return;
      editingUnitIndex=i;
      const form=$('customForm');
      for(const name of ['name','category','drivers','amplifier','reference_va','design_va','power_factor','weight_kg','width_m','depth_m','source_url','design_basis']){
        if(form.elements[name])form.elements[name].value=item[name]??'';
      }
      $('customFormWrap').querySelector('summary').textContent='Customise selected cabinet (project-specific)';
      $('customFormWrap').open=true;$('customFormWrap').scrollIntoView({behavior:'smooth',block:'nearest'});
      return;
    }
    const btn=e.target.closest('[data-remove]');if(!btn)return;project.units.splice(Number(btn.dataset.remove),1);render()});
}
function populateControls(){
  $('setupMode').value=project.setup_mode==='fixed'?'fixed':'mobile';
  for(const phase of PHASES)$('venue'+phase).value=project.venue_supply?.[phase]??'';
  $('projectName').value=project.name??'';
  project.vehicle??={};
  for(const [id,key] of [['batteryInstalled','battery_installed_kwh'],['inverterKVA','inverter_kva']])$(id).value=project[key]??0;
  $('fuelRate').value=project.fuel_rate_lph??'';
  $('powerMode').value=['generator','battery','hybrid'].includes(project.power_mode)?project.power_mode:'generator';
  for(const [id,key] of [['generatorWeight','generator_weight_kg'],['batteryWeight','battery_weight_kg'],['otherWeight','other_weight_kg']])$(id).value=project.vehicle[key]??'';
  for(const [id,key] of [['duration','duration_h'],['programMultiplier','program_multiplier'],['generatorPF','generator_pf'],['headroom','headroom_pct'],['voltage','voltage_v'],['batteryFraction','battery_use_fraction'],['inverterEfficiency','inverter_efficiency']])$(id).value=project[key]??(key==='program_multiplier'?1:'');
  $('generatorRating').innerHTML=GENERATORS.map(v=>`<option value="${v}">${v} kVA</option>`).join('');
  if(!GENERATORS.includes(Number(project.generator_kva))){$('generatorRating').insertAdjacentHTML('beforeend',`<option value="${Number(project.generator_kva)}">${Number(project.generator_kva)} kVA</option>`)}
  $('generatorRating').value=Number(project.generator_kva);
  $('vehicleType').value=project.vehicle?.type??'';
  for(const [id,key] of [['deckLength','deck_length_m'],['deckWidth','deck_width_m'],['payload','payload_kg']])$(id).value=project.vehicle?.[key]??'';
}
function validateProject(p){if(!p||p.version!==1||typeof p.name!=='string'||!Array.isArray(p.units)||p.units.length>300||!Array.isArray(p.custom_equipment||[])||(p.custom_equipment||[]).length>250||typeof p.vehicle!=='object'||p.vehicle===null)throw Error('Unsupported or invalid project file');for(const u of p.units){if(!u||typeof u.equipment_id!=='string'||!PHASES.includes(u.phase))throw Error('Invalid cabinet data')}for(const e of p.custom_equipment||[]){if(!e||typeof e.id!=='string'||!Number.isFinite(Number(e.reference_va))||!Number.isFinite(Number(e.design_va)))throw Error('Invalid equipment specification')}}
function allEquipment(){return [...catalogue,...(project.custom_equipment||[])]}
function render(){
  const all=allEquipment(),byId=new Map(all.map(e=>[e.id,e])),r=calculate(project,catalogue);
  const fixed=project.setup_mode==='fixed',venue=venueSupply(project,r);
  $('venuePanel').hidden=!fixed;
  $('vehicle').hidden=fixed;$('vehicleNav').hidden=fixed;
  $('sourceTitle').textContent=fixed?'Venue supply & generator fallback':'Generator & storage';
  $('scenarioLabel').textContent=fixed?'Fallback planning scenario':'Planning scenario';
  $('generatorTitle').textContent=fixed?'Generator fallback if venue supply is unavailable or insufficient':'Generator option';
  $('venueRequirements').replaceChildren();
  if(fixed){
    const lines=supplySummary(project,r);
    for(const line of lines.slice(1,5)){
      const item=document.createElement('p');item.textContent=line;$('venueRequirements').append(item);
    }
    $('venueVerdict').textContent=lines[5];
    $('venueVerdict').className='verdict'+(venue.status==='covered'?'':' warn');
  }
  $('equipmentType').innerHTML=all.map(e=>`<option value="${esc(e.id)}">${esc(e.name)} · ${esc(e.amplifier)}</option>`).join('');
  $('unitCount').textContent=(project.units||[]).filter(u=>byId.has(u.equipment_id)).length;
  $('unitList').innerHTML=(project.units||[]).map((u,i)=>{const e=byId.get(u.equipment_id);if(!e)return `<div class="unit-row"><div>Missing: ${esc(u.equipment_id)}</div><div></div><div></div><button class="remove" data-remove="${i}" aria-label="Remove missing item">×</button></div>`;return `<div class="unit-row"><div class="unit-main"><strong>${esc(e.name)}</strong><small>${esc(e.drivers)} · ${num(e.reference_va,0)} VA ref / ${num(e.design_va,0)} VA design</small></div><select aria-label="Phase for ${esc(e.name)}" data-phase="${i}">${PHASES.map(p=>`<option value="${p}" ${u.phase===p?'selected':''}>${p}</option>`).join('')}</select><button class="secondary edit-unit" data-edit="${i}" aria-label="Customise ${esc(e.name)}">Edit</button><button class="remove" data-remove="${i}" aria-label="Remove ${esc(e.name)}">×</button></div>`}).join('')||'<p class="hint">No cabinets. Add equipment above.</p>';
  $('referenceLoad').textContent=num(r.referenceKW,1)+' kW';
  $('designLoad').textContent=num(r.designVA/1000,1)+' kVA';
  $('suggestedGenerator').textContent=r.suggestedKVA+' kVA';
  $('batteryCapacity').textContent=num(r.batteryNominalKWh,0)+' kWh';
  $('powerVerdict').className='verdict'+(r.generatorOK?'':' warn');
  $('powerVerdict').textContent=r.generatorOK?`Selected ${r.selectedKVA} kVA generator covers the illustrative envelope. Verify input ratings, load response, phase imbalance and protection with your supplier.`:`Selected ${r.selectedKVA} kVA may be undersized: provisional minimum ${r.suggestedKVA} kVA. Rebalance phases and validate the inputs.`;
  $('phaseBars').innerHTML=PHASES.map(p=>{const va=r.phases[p].design_va,percent=r.maxPhaseAvailableVA?100*va/r.maxPhaseAvailableVA:0;return `<div class="phase-row"><div class="phase-title"><span>${p}: ${num(va/1000,2)} kVA / ${num(r.phaseCurrents[p],1)} A</span><span>${num(percent,0)}% of per-phase budget</span></div><div class="bar"><div class="bar-fill ${percent>100?'over':''}" style="width:${Math.min(100,percent)}%"></div></div></div>`}).join('');
  const powerMode=project.power_mode||'generator';
  const modeWords={generator:'Generator-only',battery:'Battery-only',hybrid:'Hybrid'};
  const run=r.batteryRuntimeH===null?'unknown':num(r.batteryRuntimeH,1)+' h';
  const batteryReady=r.batteryInstalled>0&&r.inverterCapacityOK&&r.batteryRuntimeH!==null&&r.batteryRuntimeH>=r.duration;
  const verdict=powerMode==='generator'?(r.generatorOK?'Generator covers provisional envelope; check dynamic response.':'Selected generator below provisional load envelope.'):
    powerMode==='battery'?(batteryReady?'Battery energy and inverter nameplate cover the numerical screening checks.':'Battery or inverter below estimated requirement; see input fields.'):
    'Hybrid requires a supplier-approved, synchronised generator/BESS controller and source-specific protection.';
  $('storageVerdict').className='verdict'+(powerMode==='battery'&&!batteryReady?' warn':'');
  $('storageVerdict').textContent=modeWords[powerMode]+': '+verdict;
  $('fuelNote').textContent=r.fuelLitres===null?(project.generator_fuel_curve?'See V2 supplier fuel curve interpolation below.':'Fuel: enter the generator supplier’s L/h estimate or complete the V2 fuel curve below.'):`At the entered fuel rate, ${num(r.fuelLitres,1)} L is estimated for ${r.duration} h before any reserve.`;
  $('batteryNote').textContent=`At ${num(r.averageKW,2)} kW programme demand for ${r.duration} h, estimated nominal battery capacity is ${num(r.batteryNominalKWh,1)} kWh, assuming ${Math.round(Number(project.battery_use_fraction)*100)}% usable fraction and ${Math.round(Number(project.inverter_efficiency)*100)}% conversion efficiency. Power (kW) of a three-phase grid-forming inverter is a separate constraint.`;
  const payloadStatus=r.payloadRemaining===null?'Payload not entered':(r.unknownWeights||r.unknownSourceWeights)?`Known combined weight ${num(r.totalKnownWeight,0)} kg; ${r.unknownWeights} missing cabinet weights and ${r.unknownSourceWeights} missing other weights — payload cannot be certified`:`Known combined weight ${num(r.totalKnownWeight,0)} kg; preliminary remaining payload ${num(r.payloadRemaining,0)} kg`;
  $('vehicleNote').textContent=`${payloadStatus}. ${r.deckArea?`Deck area ${num(r.deckArea,1)} m².`:'Enter deck dimensions.'} ${r.unknownFootprint?`${r.unknownFootprint} cabinet footprints unknown. `:''}Axle loads, stack geometry, tie-downs, running-in-motion approval and pedestrian safety require separate assessment.`;
  $('sourceList').innerHTML=all.filter(e=>project.units.some(u=>u.equipment_id===e.id)).map(e=>`<div class="source-row"><strong>${esc(e.name)} <span class="tag">${esc(e.confidence)}</span></strong><small>${esc(e.reference_basis)}<br>${esc(e.design_basis)}</small>${safeURL(e.source_url)?`<a href="${esc(e.source_url)}" target="_blank" rel="noopener noreferrer">Manufacturer reference</a>`:''}</div>`).join('');
  renderV2();
}
function fileBase(){return (project.name||'sound-truck').toLowerCase().replace(/[^a-z0-9-]+/g,'-').slice(0,70)||'sound-truck'}
function downloadBlob(name,blob){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)}
function download(name,content,type){const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000)}
function summary(){const r=calculate(project,catalogue);return [`Sound Truck Power Planner — preliminary engineering summary`, `Project: ${project.name}`,...supplySummary(project,r),`Date: ${new Date().toISOString()}`,`Duration: ${r.duration} h`,``, `Reference AC load: ${num(r.referenceKW,2)} kW (${num(r.referenceVA/1000,2)} kVA)`,`High-load planning envelope: ${num(r.designVA/1000,2)} kVA / ${num(r.designKW,2)} kW`,`Minimum suggested generator class: ${r.suggestedKVA} kVA`,`Selected generator: ${r.selectedKVA} kVA (${r.generatorOK?'provisional coverage':'undersized for illustrative envelope'})`,`Battery-only nominal: ${num(r.batteryNominalKWh,1)} kWh at program multiplier ${project.program_multiplier||1}`,``,...PHASES.map(p=>`${p}: ${num(r.phases[p].design_va/1000,2)} kVA / ${num(r.phaseCurrents[p],1)} A`),``,`Cabinets:`,...project.units.map((u,i)=>{const e=allEquipment().find(e=>e.id===u.equipment_id);return `${i+1}. ${e?.name||u.equipment_id} / ${u.phase} / ref ${e?.reference_va??'unknown'} VA / design ${e?.design_va??'unknown'} VA`}),``,`Warning: design allowances are estimates. Verify cabinet ratings, inrush, harmonics, dynamic loads, power-factor characteristics and phase imbalance.`, project.setup_mode==='fixed'?`Venue supply, generator fallback, protection, bonding, RCD coordination, cables and sound exposure must be professionally checked.`:`Mobile generator/BESS operation, protection, bonding, RCD coordination, cables, vehicle payload and sound exposure must be professionally checked.`,``,`Sources:`,...allEquipment().filter(e=>project.units.some(u=>u.equipment_id===e.id)).map(e=>`${e.name}: ${e.source_url||'No source'} | ${e.reference_basis}; ${e.design_basis}`)].join('\n')+'\n'}
async function start(){try{const [catalogResponse,exampleResponse]=await Promise.all([fetch('/api/v1/catalog'),fetch('/api/v1/example')]);if(!catalogResponse.ok||!exampleResponse.ok)throw Error('API not responding');catalogue=await catalogResponse.json();example=await exampleResponse.json();const saved=localStorage.getItem('soundtruck.project.v1');try{project=saved?JSON.parse(saved):structuredClone(example);validateProject(project)}catch{project=structuredClone(example)}project.program_multiplier??=1;project.vehicle??={};bind();populateControls();initV2({project:()=>project,catalogue:()=>catalogue,refresh:render,calculate:()=>calculate(project,catalogue)});render()}catch(e){document.querySelector('.shell').insertAdjacentHTML('afterbegin',`<div class="disclaimer">Unable to load equipment catalogue: ${esc(e.message)}</div>`)}}
start();
