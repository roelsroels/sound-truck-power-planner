let language='nl';
let dictionary={};
let patterns=[];
const originals=new WeakMap();
const attributes=new WeakMap();
const escapeRE=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
export const getLanguage=()=>language;
export function configureTranslations(data){
  dictionary=data;
  patterns=Object.entries(data).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>{
    const slots=[...key.matchAll(/\{(\d+)\}/g)].map(m=>m[1]);
    const re='^'+key.split(/\{\d+\}/).map(escapeRE).join('(.*?)')+'$';
    return {re:new RegExp(re,'s'),value,slots,weight:key.replace(/\{\d+\}/g,'').length};
  }).sort((a,b)=>b.weight-a.weight);
}
export function translate(text,depth=0){
  if(language!=='nl'||typeof text!=='string')return text;
  if(dictionary[text]!==undefined)return dictionary[text];
  if(depth>3)return text;
  for(const {re,value,slots} of patterns){
    const match=text.match(re);
    if(match){
      const values=Object.fromEntries(slots.map((slot,i)=>[slot,translate(match[i+1],depth+1)]));
      return value.replace(/\{(\d+)\}/g,(_,slot)=>values[slot]);
    }
  }
  return text;
}
export function setLanguage(value){language=value==='en'?'en':'nl'}
function localizeDOM(){
  document.documentElement.lang=language;
  document.title=language==='nl'?'Sound Truck / Stroomplanner':'Sound Truck / Power Planner';
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode;
    if(node.parentElement.closest('script,style,code,textarea,[data-user-content],#languageSelect'))continue;
    const old=originals.get(node);
    const source=old&&node.nodeValue===old.localized?old.source:node.nodeValue;
    const localized=source.replace(/\S[\s\S]*\S|\S/,s=>translate(s));
    originals.set(node,{source,localized});
    if(node.nodeValue!==localized)node.nodeValue=localized;
  }
  for(const el of document.querySelectorAll('[placeholder],[title],[aria-label]')){
    if(el.closest('[data-user-content]'))continue;
    const previous=attributes.get(el)||{};
    for(const name of ['placeholder','title','aria-label']){
      if(!el.hasAttribute(name))continue;
      const current=el.getAttribute(name),old=previous[name];
      const source=old&&current===old.localized?old.source:current;
      const localized=translate(source);
      previous[name]={source,localized};
      if(current!==localized)el.setAttribute(name,localized);
    }
    attributes.set(el,previous);
  }
}
export async function initLanguage(){
  const response=await fetch(new URL('./nl.json',import.meta.url));
  if(!response.ok)throw Error('Language resources unavailable');
  configureTranslations(await response.json());
  // Option text may be translated, but submitted project category values must stay stable.
  for(const option of document.querySelectorAll('option:not([value])'))option.value=option.textContent;
  try{setLanguage(localStorage.getItem('soundtruck.language'))}catch{setLanguage('nl')}
  const selector=document.getElementById('languageSelect');
  selector.value=language;
  selector.addEventListener('change',()=>{
    setLanguage(selector.value);
    try{localStorage.setItem('soundtruck.language',language)}catch{/* Browser storage is optional. */}
    localizeDOM();
    document.dispatchEvent(new Event('languagechange'));
  });
  localizeDOM();
  const observer=new MutationObserver(localizeDOM);
  observer.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']});
}
