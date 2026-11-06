/* v0.6 — traceable synthetic purchase-to-production flow with opt-in standard-cost journals.
 * Uses base dashboard `api`, `state`, `toast`, `escapeHTML`; no external UI dependencies.
 */
(()=>{
'use strict';
const node=id=>document.getElementById(id);
const escape=escapeHTML;
let config=null, financeCompanies=[], financeAccounts=[], finishedReceipts=[], financeEvents=[];
const option=(rows,make)=>rows.map(x=>`<option value="${Number(x.id)}">${escape(make(x))}</option>`).join('');
const update=(id,content)=>{const e=node(id),old=e.value;e.innerHTML=content||'<option value="">No matching records</option>';if([...e.options].some(o=>o.value===old))e.value=old;};
const dollars=v=>(Number(v||0)/100).toLocaleString('en-US',{style:'currency',currency:'USD'});
const message=(text,isError=false)=>{const target=node('flowStatus');target.textContent=text;target.style.color=isError?'#aa3838':'#087e75';};
async function loadFlow(){
 try{
  const [cfg,companies,receipts,events]=await Promise.all([
   api('/api/finance/operational-config'),api('/api/finance/companies'),
   api('/api/flow/finished-receipts'),api('/api/finance/operational-events?limit=100')]);
  config=cfg;financeCompanies=companies;finishedReceipts=receipts;financeEvents=events;
  render();
 }catch(error){message(`Workflow information not available: ${error.message}`,true);}
}
async function accountsForCompany(){
 const id=Number(node('flowCompany').value);
 if(!id){financeAccounts=[];renderAccountSelectors();return;}
 try{financeAccounts=await api(`/api/finance/accounts?company_id=${id}`);renderAccountSelectors();}
 catch(e){message(e.message,true);}
}
function renderAccountSelectors(){
 const groups=[['flowRawAccount','asset'],['flowGrniAccount','liability'],['flowWipAccount','asset'],['flowFinishedAccount','asset']];
 for(const [id,type] of groups){update(id,option(financeAccounts.filter(x=>x.category===type),x=>x.code+' · '+x.name));}
}
function render(){
 update('flowCompany',option(financeCompanies,x=>x.code+' · '+x.name));
 const cfg=config?.config;
 node('flowConfigBadge').textContent=cfg?`Enabled for company #${cfg.company_id}`:'Not enabled';
 node('flowConfigNotice').textContent=cfg?
  'Standard-cost postings are ON for this single demo company. Configuration is locked after activation.':
  'Automatic accounting is OFF. Receipts and production can still run without journals. Set up one company, four accounts, and positive item costs first.';
 node('flowConfigForm').hidden=!!cfg;
 node('flowConfigGuide').hidden=!!cfg;
 const eligible=state.orders.filter(x=>x.status==='completed'&&x.bom&&!finishedReceipts.some(r=>r.work_order_id===x.id));
 update('flowFinishedOrder',option(eligible,x=>`${x.number} · ${x.product_name} (${x.quantity} units)`));
 node('flowFinishedForm').querySelector('button[type=submit]').disabled=eligible.length===0;
 update('flowFinishedLocation',option(state.locations,x=>x.code+' · '+x.name));
 update('flowFinishedItem',option(state.items,x=>x.sku+' · '+x.name));
 syncFinishedSKU();
 node('flowFinishedList').innerHTML=finishedReceipts.slice(0,10).map(x=>`<tr><td>${escape(x.work_order)}</td><td><strong>${escape(x.finished_sku)}</strong></td><td>${Number(x.quantity)}</td><td>${escape(x.location)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No finished-goods receipts yet</td></tr>';
 node('flowJournalList').innerHTML=financeEvents.slice(0,25).map(x=>`<tr><td>${escape(x.source_kind.replaceAll('_',' '))}</td><td>${escape(x.journal_reference)}</td><td class="num">${dollars(x.value_cents)}</td></tr>`).join('')||'<tr><td colspan="3" class="empty">No automatic journals posted</td></tr>';
 accountsForCompany();
}
function syncFinishedSKU(){
 const wo=state.orders.find(x=>String(x.id)===node('flowFinishedOrder').value);
 const product=wo?.bom?.product_sku;
 if(product){const item=state.items.find(x=>x.sku===product);if(item)node('flowFinishedItem').value=String(item.id);}
 node('flowFinishedHint').textContent=wo?
  `Expected finished SKU: ${product||'Approved BOM required'} · Full receipt quantity: ${wo.quantity} · One finished-goods receipt per work order.`:
  'Complete a work order built from an active BOM before recording finished stock.';
}
node('flowCompany').addEventListener('change',accountsForCompany);
node('flowFinishedOrder').addEventListener('change',syncFinishedSKU);
node('flowConfigForm').addEventListener('submit',async e=>{
 e.preventDefault();
 const f=Object.fromEntries(new FormData(e.target));
 if(!Number(f.company_id))return message('Create a finance company and required accounts first.',true);
 if(!window.confirm('Enable standard-cost journals for this local demo company? This configuration will be locked. Existing transactions will not be backposted.'))return;
 const button=e.target.querySelector('button[type="submit"]');button.disabled=true;
 try{
  await api('/api/finance/operational-config','POST',{
   company_id:Number(f.company_id),raw_account_id:Number(f.raw_account_id),grni_account_id:Number(f.grni_account_id),
   wip_account_id:Number(f.wip_account_id),finished_account_id:Number(f.finished_account_id)
  });
  toast('Demo accounting posting rules enabled. Assign positive item costs before creating receipts.');await loadFlow();
 }catch(err){message(err.message,true);}finally{button.disabled=false;}
});
node('flowFinishedForm').addEventListener('submit',async e=>{
 e.preventDefault();const f=Object.fromEntries(new FormData(e.target));
 if(!f.work_order_id||!f.item_id||!f.location_id)return message('Choose a completed BOM work order, finished SKU, and warehouse.',true);
 const button=e.target.querySelector('button[type="submit"]');button.disabled=true;
 try{
  const result=await api(`/api/work-orders/${Number(f.work_order_id)}/receive-finished`,'POST',{
   item_id:Number(f.item_id),location_id:Number(f.location_id),command_id:command(),actor:'demo.production'});
  toast(`${result.quantity} finished units recorded for ${result.finished_sku}.${result.journal_id?' Journal posted.':' No automatic journal configured.'}`);
  await refresh();
 }catch(err){message(err.message,true);toast(err.message,true);}finally{button.disabled=false;}
});
node('flowReload').addEventListener('click',loadFlow);
window.addEventListener('meridian:data-refreshed',loadFlow);
window.addEventListener('meridian:finance-refreshed',loadFlow);
loadFlow();
})();
