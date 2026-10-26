import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {configureTranslations,setLanguage,translate,initLanguage,getLanguage} from '../web/i18n.mjs';
const dictionary=JSON.parse(readFileSync(new URL('../web/nl.json',import.meta.url)));
configureTranslations(dictionary);
setLanguage('nl');
assert.equal(translate('Find model'),'Model zoeken');
assert.equal(translate('Could not search models: Enter between 2 and 100 characters.'),'Modellen zoeken mislukt: Vul tussen 2 en 100 tekens in.');
assert.match(translate('Venue assessment: Venue supply is insufficient. Arrange a generator or reduce/rebalance the load.'),/^Beoordeling locatievoeding: De locatievoeding is onvoldoende/);
assert.equal(translate('L1: require 47.8 A; venue available not confirmed'),'L1: benodigd 47.8 A; beschikbaar op locatie niet bevestigd');
assert.equal(translate('B&C 12NDL88'),'B&C 12NDL88');
setLanguage('en');
assert.equal(translate('Find model'),'Find model');

// Exercise DOM translation, reverse switching, dynamic messages and persistence.
const label={nodeValue:'Find model',parentElement:{closest:()=>null}};
const userText={nodeValue:'My own venue',parentElement:{closest:()=>true}};
const option={textContent:'other',value:''};
const selector={value:'en',addEventListener(type,handler){this.change=handler}};
const attrs={placeholder:'Not confirmed','aria-label':'Venue L1 available (A)'};
const field={closest:()=>null,hasAttribute:k=>k in attrs,getAttribute:k=>attrs[k],setAttribute:(k,v)=>attrs[k]=v};
let stored='nl',observer;
globalThis.NodeFilter={SHOW_TEXT:4};
globalThis.MutationObserver=class{constructor(callback){observer=callback}observe(){}};
globalThis.localStorage={getItem:()=>stored,setItem:(key,value)=>{assert.equal(key,'soundtruck.language');stored=value}};
globalThis.document={body:{},documentElement:{},title:'',
  createTreeWalker(){let i=0;return {nextNode(){this.currentNode=[label,userText][i++];return !!this.currentNode}}},
  querySelectorAll:query=>query.startsWith('option')?[option]:[field],getElementById:()=>selector,dispatchEvent(){}};
globalThis.fetch=async()=>({ok:true,json:async()=>dictionary});
await initLanguage();
assert.equal(label.nodeValue,'Model zoeken');
assert.equal(userText.nodeValue,'My own venue');
assert.equal(option.value,'other');
assert.equal(attrs.placeholder,'Niet bevestigd');
assert.equal(document.documentElement.lang,'nl');
selector.value='en';selector.change();
assert.equal(label.nodeValue,'Find model');
assert.equal(attrs.placeholder,'Not confirmed');
assert.equal(stored,'en');
selector.value='nl';selector.change();
label.nodeValue='No indexed model match. Paste an official product URL below.';observer();
assert.match(label.nodeValue,/Geen model in de index/);
selector.value='en';selector.change();
assert.equal(label.nodeValue,'No indexed model match. Paste an official product URL below.');
assert.equal(getLanguage(),'en');
console.log('English/Dutch messages, DOM switching, user content, option values and persistence passed');
