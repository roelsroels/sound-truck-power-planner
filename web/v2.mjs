import {translate as t,getLanguage} from './i18n.mjs';
import {parseMeterCSV,estimateFuel,provisionalCircuits} from './v2calc.mjs';
const $=id=>document.getElementById(id);
const escapeHTML=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(n,p=1)=>Number(n).toLocaleString(getLanguage()==='nl'?'nl-NL':'en-GB',{minimumFractionDigits:p,maximumFractionDigits:p});
let ctx=null;
let inspection=null;

const notice=t=>{$('v2Status').textContent=t;};
const current=()=>ctx.project();
function profileList(){
  const p=current();
  return [...ctx.catalogue(),...(p.custom_equipment||[])];
}
function setProjectValue(key,value){current()[key]=value;ctx.refresh();}
function previewSearch(items){
  $('specResults').replaceChildren();
  if(!items.length)return;
  for(const item of items){
    const div=document.createElement('div');
    div.className='source-row';
    const strong=document.createElement('strong');
    strong.textContent=item.manufacturer+' · '+item.model;
    const small=document.createElement('small');small.textContent=item.description;
    const button=document.createElement('button');
    button.className='secondary';button.textContent='Inspect official page';
    button.addEventListener('click',()=>{$('specURL').value=item.url;inspectURL()});
    div.append(strong,small,button);$('specResults').append(div);
  }
}
function inspectPreview(data){
  inspection=data;
  const content=$('specPreview');
  content.replaceChildren();
  const title=document.createElement('p');title.textContent='Source: '+data.manufacturer+' · '+data.url;
  content.append(title);
  const table=document.createElement('div');table.className='spec-findings';
  const fields=Object.entries(data.fields||{});
  if(fields.length===0){
    const p=document.createElement('p');p.textContent='No unambiguous numeric fields extracted. Check the manufacturer page manually.';
    table.append(p);
  }
  for(const [key,value] of fields){
    const cell=document.createElement('div');
    cell.textContent=key.replaceAll('_',' ') + ': ' + value;
    table.append(cell);
  }
  content.append(table);
  const warning=document.createElement('p');warning.className='hint';warning.textContent=data.warning;
  content.append(warning);
  for(const str of (data.evidence||[]).slice(0,4)){
    const p=document.createElement('p');p.className='hint';p.textContent='Evidence: '+str;
    content.append(p);
  }
  $('approveSpecs').disabled=false;
  renderTargets();
}
async function inspectURL(){
  const url=$('specURL').value.trim();
  $('inspectSpecs').disabled=true;
  notice('Fetching official manufacturer page…');
  try{
    const response=await fetch('/api/v2/specs/inspect',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Manufacturer request failed');
    inspectPreview(data);notice('Review values against the original page before applying.');
  }catch(e){notice('Could not inspect page: '+e.message)}
  finally{$('inspectSpecs').disabled=false}
}
function renderTargets(){
  const select=$('specTarget'),previous=select.value;
  select.replaceChildren();
  current().units.forEach((u,i)=>{
    const p=profileList().find(x=>x.id===u.equipment_id);
    if(!p)return;
    const option=document.createElement('option');option.value=String(i);
    option.textContent=(i+1)+'. '+p.name;
    select.append(option);
  });
  if([...select.options].some(o=>o.value===previous))select.value=previous;
}
function applyManufacturer(){
  if(!inspection)return;
  const index=Number($('specTarget').value),p=current(),unit=p.units[index];
  if(!unit){notice('Choose a valid cabinet.');return}
  const original=profileList().find(x=>x.id===unit.equipment_id);
  if(!original){notice('Cabinet profile is missing.');return}
  const modelNotes=Object.entries(inspection.fields||{}).map(([key,val])=>key+'='+val).join(', ');
  const data={
    ...original,
    id:'review-'+(globalThis.crypto?.randomUUID?.()||Date.now().toString(36)).toLowerCase(),
    source_url:inspection.url,
    reference_basis:('Manufacturer page inspected (NOT validated as mains consumption). '+modelNotes).slice(0,500),
    confidence:'mixed'
  };
  p.custom_equipment??=[];p.custom_equipment.push(data);
  unit.equipment_id=data.id;
  inspection=null;$('approveSpecs').disabled=true;
  ctx.refresh();renderTargets();
  notice('Source attached to a project-specific cabinet copy. Electrical VA is unchanged; verify ratings and adjust using Edit.');
}
function renderMeter(){
  const m=current().meter_summary;
  $('meterSummary').textContent=m?
    `Measured ${fmt(m.average_kw,2)} kW average, ${fmt(m.observed_peak_kw,2)} kW highest observed sample, ${fmt(m.energy_kwh,2)} kWh across ${fmt(m.minutes,1)} minutes (${m.samples} readings). Peak is sample-based, not a transient capture.`:
    'No measured programme data yet. The default estimate remains active.';
  $('applyMeter').disabled=!m;
}
function renderFuel(){
  const p=current(),fuel=p.generator_fuel_curve||{};
  for(const q of [25,50,75,100]){
    const el=$('fuelP'+q);
    if(document.activeElement!==el)el.value=fuel['p'+q]??'';
  }
  if(document.activeElement!==$('fuelModel'))$('fuelModel').value=fuel.model??'';
  if(document.activeElement!==$('fuelSource'))$('fuelSource').value=fuel.source??'';
  const average=p.meter_summary?.average_kw ?? ctx.calculate().averageKW;
  const result=estimateFuel(p,average);
  const prefix=p.meter_summary?'Measured average power':'Reference estimated power';
  $('fuelCurveResult').textContent=result.status==='estimated'?
    `${prefix}: ${fmt(average,2)} kW. Estimated generator load ${result.load_pct}%, fuel ${result.lph} L/h, total ${result.litres} L before reserve. Interpolation only, not an engine guarantee.`:
    result.status==='below-25'? `Load ${result.load_pct}% is below the 25% curve endpoint; no unsupported extrapolation is made.`:
    result.status==='overload'? `Estimated load ${result.load_pct}% is above generator rating; fuel prediction withheld.`:
    'Enter all four supplier fuel rates (25/50/75/100%) in non-decreasing L/h values to estimate consumption.';
}
function renderCircuits(){
  const list=$('circuitsList'),p=current();
  p.circuit_notes??={};
  list.replaceChildren();
  for(const circuit of provisionalCircuits(p,ctx.catalogue())){
    const key=String(circuit.index);
    const data=p.circuit_notes[key]||{};
    const row=document.createElement('div');row.className='circuit-row';
    const title=document.createElement('strong');
    title.textContent=`${circuit.index+1}. ${circuit.name} · ${circuit.phase} · ~${circuit.estimated_a} A high-load apparent equivalent`;
    row.append(title);
    for(const [field,placeholder] of [['length_m','Cable length m'],['breaker_a','Protective device A'],['cable_mm2','Cable area mm²']]){
      const input=document.createElement('input');
      input.type='number';input.min='0';input.step='any';input.placeholder=placeholder;
      input.value=data[field]??'';
      input.title=placeholder;input.setAttribute('aria-label',placeholder+' for '+circuit.name);
      input.addEventListener('change',()=>{
        const num=input.value===''?null:Number(input.value);
        p.circuit_notes[key]??={};
        p.circuit_notes[key][field]=Number.isFinite(num)&&num>=0?num:null;
      });
      row.append(input);
    }
    const label=document.createElement('label');label.className='circuit-reviewed';
    const cb=document.createElement('input');cb.type='checkbox';cb.checked=!!data.engineer_reviewed;
    cb.addEventListener('change',()=>{p.circuit_notes[key]??={};p.circuit_notes[key].engineer_reviewed=cb.checked});
    label.append(cb,document.createTextNode('Engineer checked'));
    row.append(label);list.append(row);
  }
}
export function renderV2(){
  if(!ctx)return;
  renderTargets();renderMeter();renderFuel();renderCircuits();
}
export function initV2(context){
  ctx=context;
  $('searchModel').addEventListener('click',async ()=>{
    const button=$('searchModel'),status=$('specSearchStatus');
    if(button.disabled)return;
    const model=$('specModel').value.trim();
    $('specResults').replaceChildren();
    if(model.replace(/\s+/g,' ').length<2 || model.length>100){
      status.textContent='Enter between 2 and 100 characters.';return;
    }
    button.disabled=true;
    status.textContent='Searching curated manufacturer models…';
    try{
      const response=await fetch('/api/v2/specs/search?model='+encodeURIComponent(model),
        {signal:AbortSignal.timeout(10000)});
      let json;
      try{json=await response.json()}catch{throw Error('Search service returned HTTP '+response.status+' without valid JSON')}
      if(!response.ok)throw Error(typeof json.detail==='string'?json.detail:'Search service returned HTTP '+response.status);
      if(!Array.isArray(json.items))throw Error('Search service returned invalid model results');
      previewSearch(json.items);
      status.textContent=json.items.length?json.items.length+' official models matched.':
        'No indexed model match. Paste an official product URL below.';
    }catch(e){status.textContent='Could not search models: '+e.message}
    finally{button.disabled=false}
  });
  $('inspectSpecs').addEventListener('click',inspectURL);
  $('approveSpecs').addEventListener('click',applyManufacturer);
  $('meterFile').addEventListener('change',async e=>{
    const file=e.target.files[0];if(!file)return;
    try{
      if(file.size>1000000)throw Error('File exceeds 1 MB');
      current().meter_summary=parseMeterCSV(await file.text());
      ctx.refresh();notice('Meter summary imported locally. Raw CSV is not uploaded to the server.');
    }catch(err){notice('CSV rejected: '+err.message)}
    finally{e.target.value=''}
  });
  $('clearMeter').addEventListener('click',()=>{delete current().meter_summary;ctx.refresh();notice('Measurement summary cleared.')});
  $('applyMeter').addEventListener('click',()=>{
    const p=current(),ref=ctx.calculate().referenceKW,actual=p.meter_summary?.average_kw;
    if(!Number.isFinite(actual)||!ref){notice('Need measured average and non-zero reference load.');return}
    if(!confirm(t('Replace programme multiplier with measured-to-reference ratio? Verify that the measured rig matches the current project.')))return;
    p.program_multiplier=Number((actual/ref).toFixed(3));
    $('programMultiplier').value=p.program_multiplier;ctx.refresh();
    notice('Multiplier updated from measured average. Meter log remains a historical snapshot.');
  });
  for(const q of [25,50,75,100]){
    $('fuelP'+q).addEventListener('change',e=>{
      current().generator_fuel_curve??={};
      current().generator_fuel_curve['p'+q]=e.target.value===''?null:Number(e.target.value);
      ctx.refresh();
    });
  }
  for(const [id,key] of [['fuelModel','model'],['fuelSource','source']]){
    $(id).addEventListener('change',e=>{
      current().generator_fuel_curve??={};
      current().generator_fuel_curve[key]=e.target.value.slice(0,180);
      ctx.refresh();
    });
  }
  renderV2();
}
