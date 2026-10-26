import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {configureTranslations,setLanguage} from '../web/i18n.mjs';
import {notify,initNotifications} from '../web/notifications.mjs';
class Element {
  listeners={};textContent='';open=false;showCalls=0;
  addEventListener(name,handler){(this.listeners[name]??=[]).push(handler)}
  emit(name,event={}){for(const listener of this.listeners[name]||[])listener(event)}
  showModal(){this.open=true;this.showCalls++}
  close(){if(this.open){this.open=false;this.emit('close')}}
  getBoundingClientRect(){return {left:100,right:500,top:100,bottom:300}}
}
const dialog=new Element(),close=new Element(),message=new Element();
const elements={notificationDialog:dialog,notificationClose:close,notificationMessage:message};
let restored=0;
const opener={isConnected:true,focus(options){assert.equal(options.preventScroll,true);restored++}};
globalThis.document={getElementById:id=>elements[id],activeElement:opener};
configureTranslations(JSON.parse(readFileSync(new URL('../web/nl.json',import.meta.url))));setLanguage('nl');
initNotifications();initNotifications();
assert.equal(close.listeners.click.length,1,'Do not register duplicate dismiss handlers');
notify('Phases reallocated by high-load allowance. Validate real currents.');
assert.equal(dialog.open,true);
assert.equal(message.textContent,'Fasen opnieuw verdeeld op basis van ontwerpbelasting. Controleer de werkelijke stromen.');
dialog.emit('click',{target:dialog,clientX:200,clientY:200});
assert.equal(dialog.open,true,'Clicking dialog padding must not dismiss it');
dialog.emit('click',{target:message,clientX:10,clientY:10});
assert.equal(dialog.open,true,'Clicks inside message content must not dismiss it');
notify('Measurement summary cleared.');
assert.equal(dialog.showCalls,1,'Update the existing pop-up rather than stacking dialogs');
assert.equal(message.textContent,'Meetsamenvatting gewist.');
close.emit('click');
assert.equal(dialog.open,false);assert.equal(restored,1);
notify('Project saved in this browser.');
dialog.emit('click',{target:dialog,clientX:20,clientY:20});
assert.equal(dialog.open,false);assert.equal(restored,2);
notify('<img src=x onerror=alert(1)>');
assert.equal(message.textContent,'<img src=x onerror=alert(1)>','Messages are displayed as plain text');
opener.isConnected=false;close.emit('click');
assert.equal(restored,2,'Do not focus a control removed by a render');
console.log('Notification pop-up translation, updates, close button, backdrop and focus restoration passed');
