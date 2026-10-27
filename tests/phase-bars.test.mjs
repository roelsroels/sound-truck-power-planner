import assert from 'node:assert/strict';
import {renderPhaseBars} from '../web/phase-bars.mjs';
class Element{
  children=[];className='';textContent='';style={};
  constructor(document){this.ownerDocument=document}
  append(...nodes){this.children.push(...nodes)}
  replaceChildren(...nodes){this.children=nodes}
  set innerHTML(value){throw Error('HTML parsing is not allowed in phase bars')}
  setAttribute(){throw Error('Attribute/CSS text writes are not allowed in phase bars')}
}
const doc={createElement:()=>new Element(doc)};
const container=new Element(doc);
const format=(n,d)=>Number(n).toFixed(d);
renderPhaseBars(container,[
  {phase:'L1',va:660,current:2.9,budget:1000},
  {phase:'L2',va:1500,current:6.5,budget:1000},
  {phase:'L3',va:200,current:.9,budget:0}
],format,s=>'Translated: '+s);
const fills=()=>container.children.map(row=>row.children[1].children[0]);
assert.deepEqual(fills().map(fill=>fill.style.width),['66%','100%','0%']);
assert.equal(fills()[1].className,'bar-fill over');
assert.equal(fills()[0].className,'bar-fill');
assert.match(container.children[0].children[0].children[0].textContent,/L1: 0.66 kVA \/ 2.9 A/);
assert.equal(container.children[0].children[0].children[1].textContent,'Translated: 66% of per-phase budget');
renderPhaseBars(container,[{phase:'L1',va:100,current:1,budget:1000}],format,s=>s);
assert.equal(container.children.length,1,'Rerender replaces stale phase loads');
assert.equal(fills()[0].style.width,'10%');
console.log('Phase bars: proportional widths, overloads, zero supply and CSP-safe DOM rendering passed.');
