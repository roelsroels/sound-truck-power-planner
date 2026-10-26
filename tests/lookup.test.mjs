import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {initV2} from '../web/v2.mjs';

// Minimal DOM for exercising the real V2 initialization and registered handler.
class Element {
  value=''; textContent=''; disabled=false; children=[]; listeners={};
  addEventListener(type,handler){this.listeners[type]=handler}
  replaceChildren(){this.children=[]}
  append(...children){this.children.push(...children)}
  get options(){return this.children}
  showModal(){this.open=true}
  close(){this.open=false;this.listeners.close?.()}
}
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const elements=new Map([...html.matchAll(/id="([^"]+)"/g)].map(([,id])=>[id,new Element()]));
globalThis.document={getElementById:id=>elements.get(id),createElement:()=>new Element()};
const project={units:[]};
initV2({project:()=>project,catalogue:()=>[],calculate:()=>({averageKW:0}),refresh:()=>{}});
const button=elements.get('searchModel'),input=elements.get('specModel');
const status=elements.get('specSearchStatus');
assert(status,'Search feedback must live beside the lookup controls');
assert(html.indexOf('id="specSearchStatus"')<html.indexOf('id="specURL"'));
let requests=[];
globalThis.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>({items:[]})}};
input.value='a';
await button.listeners.click();
assert.equal(requests.length,0);
assert.match(status.textContent,/2 and 100/);
input.value='  B&C 12NDL88  ';
let resolve;
let requestSignal;
globalThis.fetch=(url,options)=>{requests.push(url);requestSignal=options.signal;return new Promise(r=>{resolve=r})};
const pending=button.listeners.click();
assert.equal(button.disabled,true);
assert.match(status.textContent,/Searching/);
await button.listeners.click();
assert.equal(requests.length,1,'Do not issue duplicate in-flight requests');
assert(requestSignal instanceof AbortSignal);
assert.equal(requests.at(-1),'/api/v2/specs/search?model=B%26C%2012NDL88');
resolve({ok:true,json:async()=>({items:[{manufacturer:'B&C',model:'12NDL88',description:'Driver',url:'https://example.com'}]})});
await pending;
assert.equal(button.disabled,false);
assert.equal(elements.get('specResults').children.length,1);
assert.match(status.textContent,/1 official/);
globalThis.fetch=async()=>({ok:true,json:async()=>({items:[]})});
await button.listeners.click();
assert.match(status.textContent,/No indexed model match.*official product URL/);
assert.equal(elements.get('specResults').children.length,0);
for(const response of [
  {ok:false,status:422,json:async()=>({detail:'Invalid model'})},
  {ok:false,status:502,json:async()=>{throw Error('Unexpected token <')}},
  {ok:true,status:200,json:async()=>({})}
]){
  globalThis.fetch=async()=>response;
  await button.listeners.click();
  assert.match(status.textContent,/Could not search models:/);
  assert.equal(button.disabled,false);
}
globalThis.fetch=async()=>{throw Error('Network unavailable')};
await button.listeners.click();
assert.match(status.textContent,/Network unavailable/);
assert.equal(button.disabled,false);
const originalTimeout=AbortSignal.timeout;
AbortSignal.timeout=ms=>{assert.equal(ms,10000);return AbortSignal.abort(new DOMException('Search timed out','TimeoutError'))};
globalThis.fetch=async(url,{signal})=>{signal.throwIfAborted()};
await button.listeners.click();
assert.match(status.textContent,/Search timed out/);
assert.equal(button.disabled,false);
AbortSignal.timeout=originalTimeout;
console.log('V2 lookup initialization, request, results and error tests passed');
