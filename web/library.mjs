import {translate as t} from './i18n.mjs';
import {notify} from './notifications.mjs';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const words={driver:'Driver / transducer',amplifier:'Amplifier',passive_cabinet:'Passive cabinet',active_cabinet:'Active cabinet',accessory:'Accessory'};
export const isSource=p=>['amplifier','active_cabinet'].includes(p.kind)&&p.power_input!=='dc';
export function filterProducts(products,{query='',manufacturer='',kind='',archived=false}={}){
  const terms=query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return products.filter(p=>(!manufacturer||p.manufacturer_id===manufacturer)&&(!kind||p.kind===kind)&&(archived||p.status!=='archived')&&terms.every(word=>`${p.model} ${p.variant} ${p.manufacturer_id} ${p.manufacturer_name||''} ${p.category}`.toLowerCase().includes(word)));
}
export function assembleProfile(components,manufacturers,fields,id){
  if(!components.length||components.length>64)throw Error('Choose at least one library component.');
  if(components.some(c=>!Number.isInteger(c.quantity)||c.quantity<1||c.quantity>100))throw Error('Component quantities must be whole numbers from 1 to 100.');
  const sources=components.filter(c=>isSource(c.product));
  if(sources.length!==1||sources[0].quantity!==1)throw Error('Use exactly one amplifier or active cabinet per mains profile.');
  if(sources[0].product.kind==='active_cabinet'&&components.some(c=>c.product.kind!=='accessory'&&c!==sources[0]))throw Error('An active cabinet is a separate mains load. Add other cabinets in another profile.');
  const reference=Number(fields.reference_va),design=Number(fields.design_va),pf=Number(fields.power_factor);
  if([fields.reference_va,fields.design_va,fields.power_factor].some(v=>v===''||v===null||v===undefined)||!Number.isFinite(reference)||!Number.isFinite(design)||!Number.isFinite(pf)||reference<0||design<=0||design<reference||design>1_000_000||pf<=0||pf>1)throw Error('Enter reference VA, planning VA and power factor. Planning VA must be positive and at least reference VA.');
  const name=String(fields.name||'').trim(),basis=String(fields.basis||'').trim();
  if(!name||name.length>120||!basis||basis.length>500)throw Error('Enter a profile name and the basis for its mains estimates.');
  const label=p=>`${manufacturers.find(m=>m.id===p.manufacturer_id)?.name||p.manufacturer_id} ${p.model}${p.variant?' '+p.variant:''}`;
  const source=sources[0].product;
  return {id,name,category:['infra','kick','top','auxiliary','other'].includes(fields.category)?fields.category:'other',
    drivers:components.filter(c=>!isSource(c.product)).map(c=>`${label(c.product)} × ${c.quantity}`).join(' + ').slice(0,250),
    amplifier:label(source).slice(0,250),reference_va:reference,design_va:design,power_factor:pf,
    weight_kg:null,width_m:null,depth_m:null,source_url:source.source_url,
    reference_basis:basis,design_basis:basis,confidence:'estimate',
    library_components:components.map(c=>({product_id:c.product.id,manufacturer:manufacturers.find(m=>m.id===c.product.manufacturer_id)?.name||c.product.manufacturer_id,model:c.product.model,variant:c.product.variant,quantity:c.quantity,source_url:c.product.source_url}))};
}

export function initLibrary({addProfile}){
  const $=id=>document.getElementById(id),dialog=$('libraryDialog');
  let manifest=null,imported={schema_version:1,manufacturers:[],products:[]},selected=null,components=[],visible=20,request=0;
  const details=new Map();
  const merged=()=>{
    const manufacturers=new Map((manifest?.manufacturers||[]).map(m=>[m.id,m]));
    const products=new Map((manifest?.products||[]).map(p=>[p.id,p]));
    for(const m of imported.manufacturers)manufacturers.set(m.id,m);
    for(const p of imported.products)products.set(p.id,{...p,spec_count:p.specs.length});
    return {manufacturers:[...manufacturers.values()],products:[...products.values()].map(p=>({...p,manufacturer_name:manufacturers.get(p.manufacturer_id)?.name||''}))};
  };
  const label=p=>`${merged().manufacturers.find(m=>m.id===p.manufacturer_id)?.name||p.manufacturer_id} · ${p.model}${p.variant?' · '+p.variant:''}`;
  function renderList(){
    const data=merged(),matches=filterProducts(data.products,{query:$('libraryQuery').value,manufacturer:$('libraryManufacturer').value,kind:$('libraryKind').value,archived:$('libraryArchived').checked});
    $('libraryCount').textContent=t('Showing {0} of {1} product variants.').replace('{0}',Math.min(matches.length,visible)).replace('{1}',matches.length);
    $('libraryResults').innerHTML=matches.slice(0,visible).map(p=>`<button type="button" class="library-result secondary ${selected?.id===p.id?'selected':''}" data-product="${esc(p.id)}"><strong data-user-content>${esc(label(p))}</strong><small>${esc(t(words[p.kind]))}${p.status==='archived'?' · '+esc(t('Archived')):''} · ${esc(String(p.spec_count??p.specs?.length??0))} ${esc(t('specification fields'))}</small></button>`).join('')||`<p class="hint">${esc(t('No matching products. Try another search or include archived models.'))}</p>`;
    $('libraryMore').hidden=matches.length<=visible;
  }
  function renderSelected(){
    if(!selected){$('libraryDetail').innerHTML=`<p class="hint">${esc(t('Select a product to view its specifications.'))}</p>`;return}
    const p=selected,sections=new Map();
    for(const spec of p.specs){if(!sections.has(spec.section))sections.set(spec.section,[]);sections.get(spec.section).push(spec)}
    const sectionNames={generalSpecs:'General specifications',lfSpecs:'LF specifications',mfSpecs:'MF specifications',hfSpecs:'HF specifications',hornSpecs:'Horn specifications',crossOverSpecs:'Crossover specifications',params:'Thiele–Small parameters',design:'Construction',shippingMounting:'Dimensions and mounting'};
    $('libraryDetail').innerHTML=`<h3 data-user-content>${esc(label(p))}</h3><p class="hint">${esc(t(words[p.kind]))} · ${esc(t('Checked'))}: <span data-user-content>${esc(p.checked_at)}</span></p><p><a href="${esc(p.source_url)}" target="_blank" rel="noopener noreferrer">${esc(t('Official product page'))}</a></p><p class="hint">${esc(t('Published specifications retain the manufacturer’s language and test conditions. Missing specifications remain unknown; consult the original datasheet.'))}</p>${p.power_input==='dc'?`<p class="verdict warn">${esc(t('DC / PoE powered: use the upstream AC supply consumption, not the amplifier output rating.'))}</p>`:''}<button type="button" id="libraryUse" class="primary">${esc(t('Use in power profile'))}</button><details class="disclosure"><summary>${esc(t('Manufacturer specifications'))} (${p.specs.length})</summary>${[...sections].map(([section,specs])=>`<h4>${esc(t(sectionNames[section]||section))}</h4><dl class="library-specs">${specs.map(s=>`<div><dt data-user-content>${esc(s.label)}</dt><dd data-user-content>${esc(s.value)}${s.notes?`<small>${esc(s.notes)}</small>`:''}</dd></div>`).join('')}</dl>`).join('')||`<p>${esc(t('No published specification fields imported. See the official documents.'))}</p>`}</details><details class="disclosure"><summary>${esc(t('Datasheets and documents'))} (${p.datasheet_urls.length})</summary>${p.datasheet_urls.map((u,i)=>`<p><a href="${esc(u)}" target="_blank" rel="noopener noreferrer" data-user-content>${esc(u.split('/').at(-1).split('?')[0])||'PDF '+(i+1)}</a></p>`).join('')||`<p>${esc(t('See the official product page for downloads.'))}</p>`}</details>`;
  }
  function renderBuilder(){
    $('libraryBuilder').hidden=!components.length;
    $('libraryComponents').innerHTML=components.map((c,i)=>`<div class="library-component"><span data-user-content>${esc(label(c.product))}</span><label><span class="sr-only">${esc(t('Quantity'))}</span><input data-component-quantity="${i}" aria-label="${esc(t('Quantity'))}: ${esc(c.product.model)}" type="number" min="1" max="100" value="${c.quantity}" ${isSource(c.product)?'disabled':''}></label><button type="button" class="remove" data-component-remove="${i}" aria-label="${esc(t('Remove component'))}">×</button></div>`).join('');
    const source=components.find(c=>isSource(c.product));
    $('libraryPowerHint').textContent=source?t('One mains feed is counted for this profile. Passive cabinets and drivers do not add another mains load. Confirm channel wiring, impedance and amplifier compatibility separately.'):t('Add the amplifier that powers these components before creating a mains profile.');
  }
  async function refreshManifest(){
    const response=await fetch('/api/v3/library');if(!response.ok)throw Error('Library request failed');manifest=await response.json();
    const value=$('libraryManufacturer').value;
    $('libraryManufacturer').innerHTML=`<option value="">${esc(t('All manufacturers'))}</option>`+merged().manufacturers.map(m=>`<option value="${esc(m.id)}" data-user-content>${esc(m.name)}</option>`).join('');$('libraryManufacturer').value=value;
    renderList();
  }
  $('openLibrary').addEventListener('click',async()=>{
    dialog.showModal();$('libraryQuery').focus();
    try{if(!manifest)await refreshManifest();else renderList();renderSelected();renderBuilder()}
    catch(error){$('libraryResults').textContent=t('Could not load the product library. Close and try again.');manifest=null}
  });
  $('libraryClose').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()}});
  for(const id of ['libraryQuery','libraryManufacturer','libraryKind','libraryArchived'])$(id).addEventListener(id==='libraryQuery'?'input':'change',()=>{visible=20;renderList()});
  $('libraryMore').addEventListener('click',()=>{visible+=20;renderList()});
  $('libraryResults').addEventListener('click',async event=>{
    const id=event.target.closest('[data-product]')?.dataset.product;if(!id)return;const ticket=++request;
    try{
      let product=imported.products.find(p=>p.id===id)||details.get(id);
      if(!product){const response=await fetch('/api/v3/library/products/'+encodeURIComponent(id));if(!response.ok)throw Error();product=await response.json();details.set(id,product)}
      if(ticket!==request)return;selected=product;renderList();renderSelected();$('libraryUse').focus({preventScroll:true});$('libraryDetail').scrollIntoView({block:'nearest'});
    }catch{notify('Could not load product details. Try again.')}
  });
  $('libraryDetail').addEventListener('click',event=>{
    if(!event.target.closest('#libraryUse')||!selected)return;
    const existing=components.find(c=>c.product.id===selected.id);
    if(existing){if(!isSource(selected)&&existing.quantity<100)existing.quantity++;renderBuilder();return}
    if(components.length>=64){notify('A power profile can contain at most 64 component types.');return}
    if(isSource(selected)&&components.some(c=>isSource(c.product))){notify('Use exactly one amplifier or active cabinet per mains profile.');return}
    components.push({product:selected,quantity:1});
    if(!$('libraryProfileName').value)$('libraryProfileName').value=selected.model.slice(0,120);
    if(isSource(selected)){
      const e=selected.electrical;
      $('libraryReference').value=e?.reference_va??'';$('libraryPlanning').value=e?.design_va??'';$('libraryPF').value=e?.power_factor??'';$('libraryBasis').value=(e?.basis||'').slice(0,500);
    }
    renderBuilder();$('libraryBuilder').scrollIntoView({block:'nearest',behavior:'smooth'});
  });
  $('libraryComponents').addEventListener('click',event=>{const button=event.target.closest('[data-component-remove]');if(!button)return;components.splice(Number(button.dataset.componentRemove),1);renderBuilder()});
  $('libraryComponents').addEventListener('change',event=>{const el=event.target.closest('[data-component-quantity]');if(!el)return;const value=Number(el.value);if(!Number.isInteger(value)||value<1||value>100){notify('Component quantities must be whole numbers from 1 to 100.');renderBuilder();return}components[Number(el.dataset.componentQuantity)].quantity=value});
  $('libraryProfileForm').addEventListener('submit',event=>{
    event.preventDefault();
    try{
      const profile=assembleProfile(components,merged().manufacturers,{name:$('libraryProfileName').value,category:$('libraryCategory').value,reference_va:$('libraryReference').value,design_va:$('libraryPlanning').value,power_factor:$('libraryPF').value,basis:$('libraryBasis').value},'user-'+(globalThis.crypto?.randomUUID?.()??Date.now().toString(36)).toLowerCase());
      addProfile(profile);components=[];$('libraryProfileForm').reset();renderBuilder();dialog.close();notify('Library power profile added. Save the project to retain it.');
    }catch(error){notify(error.message)}
  });
  $('libraryImport').addEventListener('change',async event=>{
    const file=event.target.files[0];if(!file)return;
    try{
      if(file.size>8_000_000)throw Error('Library file exceeds 8 MB');
      const response=await fetch('/api/v3/library/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:await file.text()});
      if(!response.ok){const error=await response.json();throw Error(error.detail||'Invalid library')}
      const pack=await response.json(),manufacturers=new Map(imported.manufacturers.map(m=>[m.id,m])),products=new Map(imported.products.map(p=>[p.id,p]));
      for(const m of pack.manufacturers)manufacturers.set(m.id,m);
      for(const p of pack.products)products.set(p.id,p);
      const next={schema_version:1,manufacturers:[...manufacturers.values()],products:[...products.values()]};
      // Keep the existing saved library if browser storage is full.
      localStorage.setItem('soundtruck.library.v1',JSON.stringify(next));imported=next;selected=null;request++;
      await refreshManifest();renderSelected();notify('Library imported into this browser. Public library unchanged.');
    }catch(error){notify(t('Library import failed: {0}').replace('{0}',error.message))}
    finally{event.target.value=''}
  });
  $('libraryExport').addEventListener('click',()=>{
    if(!imported.products.length){notify('No browser-imported library to export.');return}
    const url=URL.createObjectURL(new Blob([JSON.stringify(imported,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='manufacturer-library.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
  });
  // Revalidate persisted packs before rendering their links or data.
  try{
    const saved=localStorage.getItem('soundtruck.library.v1');
    if(saved)fetch('/api/v3/library/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:saved}).then(async response=>{if(response.ok){imported=await response.json();if(manifest)await refreshManifest()}}).catch(()=>{});
  }catch{/* Browser libraries are optional. */}
  document.addEventListener('languagechange',()=>{if(manifest){const value=$('libraryManufacturer').value;$('libraryManufacturer').innerHTML=`<option value="">${esc(t('All manufacturers'))}</option>`+merged().manufacturers.map(m=>`<option value="${esc(m.id)}" data-user-content>${esc(m.name)}</option>`).join('');$('libraryManufacturer').value=value;renderList();renderSelected();renderBuilder()}});
}
