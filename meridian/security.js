/* Opt-in local demo login. Session token stored only in this tab, not localStorage. */
(()=>{
'use strict';
const dialog=document.getElementById('securityBackdrop');
const form=document.getElementById('securityLoginForm');
const warning=document.getElementById('securityError');
const indicator=document.getElementById('securityIndicator');
let enabled=false;
function show(){dialog.hidden=false;form.elements.username.focus();}
function hide(){dialog.hidden=true;}
async function status(){
 try{
  const r=await fetch('/api/security/status',{cache:'no-store'});const data=await r.json();enabled=!!data.login_required;
  indicator.textContent=enabled?'Local demo authentication enabled · no SSO or network security':'Unrestricted local demo · no login protection';
  if(enabled&&!window.meridianAccessToken)show();
 }catch(_){indicator.textContent='Could not check demo security mode';}
}
form.addEventListener('submit',async ev=>{
 ev.preventDefault();warning.textContent='';const submit=form.querySelector('button');submit.disabled=true;
 try{
  const r=await fetch('/api/security/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:form.elements.username.value,password:form.elements.password.value})});
  const data=await r.json();if(!r.ok)throw Error(data.detail||'Sign-in failed');
  window.meridianAccessToken=data.access_token;
  form.elements.password.value='';hide();indicator.textContent=`Signed in as ${data.username} (${data.role}) · local demo`;
  await refresh();
 }catch(e){warning.textContent=e.message;}finally{submit.disabled=false;}
});
window.addEventListener('meridian:unauthorized',()=>{window.meridianAccessToken='';if(enabled)show();});
status();
})();
