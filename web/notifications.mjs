import {translate} from './i18n.mjs';

let initialized=false;
let previousFocus=null;
export function initNotifications(){
  if(initialized)return;
  const dialog=document.getElementById('notificationDialog');
  const close=document.getElementById('notificationClose');
  close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;
    const box=dialog.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)dialog.close();
  });
  dialog.addEventListener('close',()=>{
    if(previousFocus?.isConnected)previousFocus.focus({preventScroll:true});
    previousFocus=null;
  });
  // Native modal dialogs handle Escape and keep keyboard focus inside the pop-up.
  initialized=true;
}
export function notify(message){
  initNotifications();
  const dialog=document.getElementById('notificationDialog');
  document.getElementById('notificationMessage').textContent=translate(String(message));
  if(!dialog.open){
    previousFocus=document.activeElement;
    dialog.showModal();
  }
}
