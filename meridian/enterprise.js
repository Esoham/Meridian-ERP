/* Meridian ERP extension shell — operational UI + local personalizations.
   The role selector is PRESENTATION ONLY, not an authorization control. */
(function(){
'use strict';
const $=id=>document.getElementById(id);
const html=escapeHTML;
const ent={suppliers:[],purchaseOrders:[],quality:[],fields:[],insights:{}};
const KEY='meridian:v0.4:workspace';
const MODULES=['overview','inventory','boms','production','procurement','quality','reports','finance','integrations','audit','settings'];
const WIDGETS=['kpis','production','ledger','actions','guide','procurement','quality'];
const PRESETS={
 operations:WIDGETS,
 inventory:['kpis','ledger','actions','procurement'],
 planner:['kpis','production','actions','guide','quality'],
 purchasing:['kpis','procurement','ledger','actions'],
 quality:['kpis','quality','production','ledger']
};
const DEFAULT={workspaceName:'Manufacturing',role:'operations',accent:'teal',density:'comfortable',theme:'light',sidebar:'expanded',widgets:[...WIDGETS]};
let preferences={...DEFAULT};
function validatePrefs(raw){
 const data=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw:{};
 return {
 workspaceName:typeof data.workspaceName==='string' ? data.workspaceName.trim().slice(0,32)||'Manufacturing':'Manufacturing',
 role:Object.hasOwn(PRESETS,data.role)?data.role:'operations',
 accent:['teal','blue','indigo','orange'].includes(data.accent)?data.accent:'teal',
 density:['compact','comfortable'].includes(data.density)?data.density:'comfortable',
 theme:['light','dark'].includes(data.theme)?data.theme:'light',
 sidebar:['expanded','collapsed'].includes(data.sidebar)?data.sidebar:'expanded',
 widgets:Array.isArray(data.widgets)?WIDGETS.filter(x=>data.widgets.includes(x)):[...WIDGETS]
 };
}
try{preferences=validatePrefs(JSON.parse(localStorage.getItem(KEY)||'null'));}catch(_){preferences=validatePrefs(null);}
function save(){try{localStorage.setItem(KEY,JSON.stringify(preferences));}catch(_){toast('Browser storage is blocked; preferences apply only until this page is closed.',true);}}
function applyPrefs(){
 document.body.dataset.accent=preferences.accent;
 document.body.dataset.density=preferences.density;
 document.body.dataset.theme=preferences.theme;
 document.body.dataset.sidebar=preferences.sidebar;
 $('workspaceLabel').textContent=preferences.workspaceName;
 document.querySelectorAll('#page-overview [data-widget]').forEach(node=>{node.hidden=!preferences.widgets.includes(node.dataset.widget);});
 for(const [key,val] of Object.entries(preferences)){
  const input=$('settingsForm').elements.namedItem(key);
  if(input && key!=='widgets')input.value=val;
 }
 document.querySelectorAll('#widgetOptions input[type=checkbox]').forEach(box=>{box.checked=preferences.widgets.includes(box.value);});
}
applyPrefs();
$('settingsForm').addEventListener('submit',ev=>{
 ev.preventDefault();const form=Object.fromEntries(new FormData(ev.target));
 preferences=validatePrefs({...preferences,...form,widgets:preferences.widgets});save();applyPrefs();toast('Workspace preferences saved to this browser.');
});
$('roleSelect').addEventListener('change',ev=>{
 preferences.role=ev.target.value;
 preferences.widgets=[...(PRESETS[preferences.role]||WIDGETS)];
 save();applyPrefs();toast('Role workspace applied. This is not a security permission.');
});
$('widgetOptions').addEventListener('change',ev=>{
 if(!ev.target.matches('input[type=checkbox]'))return;
 preferences.widgets=[...document.querySelectorAll('#widgetOptions input:checked')].map(el=>el.value).filter(v=>WIDGETS.includes(v));
 save();applyPrefs();
});
$('resetSettings').addEventListener('click',()=>{preferences=validatePrefs(DEFAULT);save();applyPrefs();toast('Workspace appearance restored to default.');});
$('exportPrefs').addEventListener('click',()=>{
 const blob=new Blob([JSON.stringify({kind:'MeridianWorkspacePreferences',version:1,preferences},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='meridian-workspace.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('importPrefs').addEventListener('change',async ev=>{
 const file=ev.target.files?.[0];if(!file)return;
 try{if(file.size>15000)throw Error('Preferences file is too large');const raw=JSON.parse(await file.text());if(raw?.kind!=='MeridianWorkspacePreferences'||raw?.version!==1)throw Error('Unrecognized workspace settings file');
 preferences=validatePrefs(raw.preferences);save();applyPrefs();toast('Workspace appearance imported.');}
 catch(e){toast('Could not import preferences: '+e.message,true);}ev.target.value='';
});
// Safe pick lists preserve an existing selection when possible.
function pick(id,rows,label,placeholder='No records'){const node=$(id),value=node.value;node.innerHTML=rows.length?rows.map(x=>`<option value="${Number(x.id)}">${html(label(x))}</option>`).join(''):`<option value="">${html(placeholder)}</option>`;if([...node.options].some(o=>o.value===value))node.value=value;}
const formData=form=>Object.fromEntries(new FormData(form));
async function send(form,url,body,ok,method='POST'){
 const button=form.querySelector('button[type=submit]');if(button)button.disabled=true;
 try{await api(url,method,body);toast(ok);await refresh();await load();return true;}
 catch(e){toast(e.message,true);return false;}
 finally{if(button)button.disabled=false;}
}
async function runAction(button,url,body,success){button.disabled=true;try{await api(url,'POST',body);toast(success);await refresh();await load();}catch(e){toast(e.message,true);}finally{button.disabled=false;}}
const optionItems=()=>state.items.map(i=>`<option value="${Number(i.id)}">${html(i.sku+' · '+i.name)}</option>`).join('');
// PURCHASE ORDERS
function addPOLine(item=null,quantity=1,price=0){
 const root=$('poLines');const d=document.createElement('div');d.className='po-line';
 d.innerHTML=`<label>Item<select data-po-item required>${optionItems()}</select></label><label>Quantity<input data-po-qty type="number" min="1" max="1000000" value="${Number(quantity)}" required></label><label>Unit cost ($)<input data-po-cost type="number" min="0" max="1000000" step="0.01" value="${Number(price).toFixed(2)}" required></label><button class="button tiny danger" type="button" data-delete-po-line aria-label="Remove purchase order line">✕</button>`;
 root.appendChild(d);if(item!==null)d.querySelector('select').value=String(item);
 $('poLineCount').textContent=`${root.children.length} line${root.children.length===1?'':'s'}`;
}
function getPOLines(){const elems=[...$('poLines').children];if(!elems.length)throw Error('Add at least one PO line.');
 const rows=elems.map(d=>{const item_id=Number(d.querySelector('[data-po-item]').value);
  const quantity=Number(d.querySelector('[data-po-qty]').value);
  const cost=Number(d.querySelector('[data-po-cost]').value);
  if(!Number.isSafeInteger(item_id)||item_id<1||!Number.isSafeInteger(quantity)||quantity<1||quantity>1000000||!Number.isFinite(cost)||cost<0||cost>1000000)throw Error('Enter a valid item, quantity, and unit cost.');
  const cents=Math.round(cost*100);if(Math.abs(cost*100-cents)>1e-5)throw Error('Unit cost supports at most two decimal places.');
  return {item_id,quantity,unit_price_cents:cents};});
 if(new Set(rows.map(x=>x.item_id)).size!==rows.length)throw Error('Each item may appear only once on a PO.');
 return rows;
}
$('addPOLine').addEventListener('click',()=>addPOLine());
$('poLines').addEventListener('click',ev=>{const btn=ev.target.closest('[data-delete-po-line]');if(!btn)return;btn.closest('.po-line').remove();if(!$('poLines').children.length)addPOLine();$('poLineCount').textContent=$('poLines').children.length+' line(s)';});
$('supplierForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=formData(ev.target);if(await send(ev.target,'/api/suppliers',f,'Supplier created.'))ev.target.reset();});
$('poForm').addEventListener('submit',async ev=>{ev.preventDefault();try{const f=formData(ev.target);const lines=getPOLines();if(await send(ev.target,'/api/purchase-orders',{number:f.number,supplier_id:Number(f.supplier_id),lines},'Draft purchase order created.')){$('poLines').innerHTML='';addPOLine();}}catch(e){toast(e.message,true);}});
$('poReceiptForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=formData(ev.target);await send(ev.target,`/api/purchase-orders/${Number(f.po_id)}/receive`,{item_id:Number(f.item_id),location_id:Number(f.location_id),quantity:Number(f.quantity),command_id:command()},'PO receipt posted to inventory.');});
$('poReceiptOrder').addEventListener('change',populateReceiptItems);
function populateReceiptItems(){const po=ent.purchaseOrders.find(p=>String(p.id)===$('poReceiptOrder').value);
 pick('poReceiptItem',po?po.lines.filter(x=>x.remaining>0).map(x=>({id:x.item_id,sku:x.sku,remaining:x.remaining})):[],x=>`${x.sku} · ${x.remaining} outstanding`);
 const line=po?.lines.find(x=>String(x.item_id)===$('poReceiptItem').value);if(line)$('poReceiptForm').elements.namedItem('quantity').max=String(line.remaining);
}
$('poReceiptItem').addEventListener('change',populateReceiptItems);
$('poSearch').addEventListener('input',renderPOs);
$('poList').addEventListener('click',ev=>{const button=ev.target.closest('[data-approve-po]');if(!button)return;runAction(button,`/api/purchase-orders/${Number(button.dataset.approvePo)}/approve`,{actor:'demo.purchasing'},'Purchase order approved.');});
function renderPOs(){const query=$('poSearch').value.toLowerCase().trim(),view=ent.purchaseOrders.filter(p=>!query||[p.number,p.supplier_code,p.supplier_name,p.status,...p.lines.map(x=>x.sku)].some(x=>String(x).toLowerCase().includes(query)));
 $('poCount').textContent=`${ent.purchaseOrders.length} purchase orders`;
 $('poList').innerHTML=view.map(p=>{const lines=p.lines.map(l=>`<tr><td><strong>${html(l.sku)}</strong></td><td class="num">${l.ordered_qty}</td><td class="num">${l.received_qty}</td><td class="num">${l.remaining}</td><td class="num">$${(l.unit_price_cents/100).toFixed(2)}</td></tr>`).join('');
 return `<article class="po-register"><div class="register-top"><div><strong>${html(p.number)}</strong><p>${html(p.supplier_name)} · ${html(p.supplier_code)}</p></div><span class="chip ${html(p.status==='approved'?'released':p.status==='received'?'completed':p.status==='draft'?'draft':'materials_issued')}">${html(p.status)}</span></div><div class="register-meta"><span>Ordered value $${(p.total_cents/100).toLocaleString('en-US',{minimumFractionDigits:2})}</span><span>${p.lines.length} line(s)</span></div><div class="table-wrap"><table><thead><tr><th>SKU</th><th>Ordered</th><th>Received</th><th>Open</th><th>Unit $</th></tr></thead><tbody>${lines}</tbody></table></div>${p.status==='draft'?`<div class="register-actions"><button class="button green tiny" type="button" data-approve-po="${p.id}">Approve PO</button></div>`:''}</article>`;}).join('')||'<p class="empty">No purchase orders match your search.</p>';
}
// QUALITY
$('qualitySearch').addEventListener('input',renderQuality);
$('qualityForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=formData(ev.target);
 const payload={number:f.number,summary:f.summary,severity:f.severity,source:f.source,item_id:f.item_id?Number(f.item_id):null};
 if(await send(ev.target,'/api/quality-cases',payload,'Quality case created.'))ev.target.reset();
});
$('qualityList').addEventListener('click',ev=>{const b=ev.target.closest('[data-quality-action]');if(!b)return;
 const id=Number(b.dataset.qualityId),status=b.dataset.qualityAction;
 const holder=b.closest('.quality-register'),note=holder.querySelector('[data-quality-resolution]')?.value.trim()||'';
 if(status==='resolved' && note.length<5){toast('Explain the corrective action (minimum 5 characters).',true);return;}
 runAction(b,`/api/quality-cases/${id}/status`,{status,resolution:note,actor:'demo.quality'},`Quality case moved to ${status.replace('_',' ')}.`);
});
function renderQuality(){const q=$('qualitySearch').value.toLowerCase().trim(),rows=ent.quality.filter(x=>!q||[x.number,x.summary,x.source,x.severity,x.status,x.item_sku].some(s=>String(s||'').toLowerCase().includes(q)));
 $('qualityCount').textContent=`${ent.quality.length} cases`;
 $('qualityList').innerHTML=rows.map(x=>`<article class="quality-register"><div class="register-top"><div><strong>${html(x.number)}</strong><p>${html(x.summary)}</p></div><span class="chip ${x.status==='resolved'?'completed':x.status==='in_review'?'released':'draft'}">${html(x.status.replace('_',' '))}</span></div><div class="register-meta"><span>Source: ${html(x.source)}</span><span>Priority: ${html(x.severity)}</span>${x.item_sku?`<span>SKU: ${html(x.item_sku)}</span>`:''}</div>${x.resolution?`<p class="help"><strong>Resolution:</strong> ${html(x.resolution)}</p>`:''}${x.status!=='resolved'?`<div class="register-actions">${x.status==='open'?`<button class="button alt tiny" type="button" data-quality-id="${x.id}" data-quality-action="in_review">Start review</button>`:''}<textarea data-quality-resolution aria-label="Resolution for ${html(x.number)}" placeholder="Document corrective action, evidence, or disposition"></textarea><button class="button green tiny" type="button" data-quality-id="${x.id}" data-quality-action="resolved">Resolve case</button></div>`:''}</article>`).join('')||'<p class="empty">No quality cases match.</p>';
}
// FIELDS & ITEM CONFIGURATION
$('fieldForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=formData(ev.target);if(await send(ev.target,'/api/custom-fields',f,'Custom field created.'))ev.target.reset();});
function fieldOption(){const el=ent.fields.find(x=>String(x.id)===$('customField').value);const input=$('customValue');
 input.type=el?.field_type==='number'?'number':'text';input.placeholder=el?.field_type==='boolean'?'Enter true or false':el?.field_type==='number'?'Example: 12':'Enter field value';if(el?.field_type==='number')input.step='any';else input.removeAttribute('step');}
$('customField').addEventListener('change',()=>{fieldOption();loadItemValues();});
$('customItem').addEventListener('change',loadItemValues);
$('valueForm').addEventListener('submit',async ev=>{ev.preventDefault();const f=formData(ev.target),field=ent.fields.find(x=>x.id===Number(f.field_id));if(!field){toast('Define a custom field first.',true);return;}
 let val=f.value;
 if(field.field_type==='number'){val=Number(val);if(!Number.isFinite(val)){toast('Enter a valid number.',true);return;}}
 if(field.field_type==='boolean'){if(!['true','false'].includes(val.trim().toLowerCase())){toast('Enter true or false.',true);return;}val=val.trim().toLowerCase()==='true';}
 if(await send(ev.target,`/api/items/${Number(f.item_id)}/custom-fields/${Number(f.field_id)}`,{value:val,actor:'demo.admin'},'Custom item value saved.','PUT'))loadItemValues();
});
async function loadItemValues(){const item=Number($('customItem').value);if(!item){$('itemCustomDisplay').textContent='Select an item.';return;}
 try{const v=await api(`/api/items/${item}/custom-fields`);const values=Object.entries(v.values);
 $('itemCustomDisplay').innerHTML=values.map(([key,val])=>`<div class="data-row"><strong>${html(key)}</strong><span>${html(String(val))}</span></div>`).join('')||'<p class="help">No custom values for this item.</p>';
 }catch(e){$('itemCustomDisplay').textContent=e.message;}
}
function renderFields(){pick('customItem',state.items,x=>`${x.sku} · ${x.name}`,'No items');pick('customField',ent.fields,x=>`${x.label} (${x.field_type})`,'Define a field first');fieldOption();
 $('fieldList').innerHTML=ent.fields.map(f=>`<div class="data-row"><strong>${html(f.label)}<br><small>${html(f.field_key)}</small></strong><span class="chip">${html(f.field_type)}</span></div>`).join('')||'<p class="help">No custom fields defined yet.</p>';
 loadItemValues();
}
// REPORTS
function renderReports(){const i=ent.insights;
 $('reportPO').textContent=formatNum(i.open_purchase_orders||0);$('reportQuality').textContent=formatNum(i.open_quality_cases||0);
 $('reportCompleted').textContent=formatNum(state.orders.filter(x=>x.status==='completed').length);
 $('reportAvailable').textContent=formatNum(state.stock.reduce((n,x)=>n+Number(x.available||0),0));
 $('reportStock').innerHTML=state.stock.map(x=>`<tr><td><strong>${html(x.sku)}</strong></td><td>${html(x.location_code)}</td><td class="num">${x.on_hand}</td><td class="num">${x.reserved}</td><td class="num ${Number(x.available)<1?'bad':''}">${x.available}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No stock available.</td></tr>';
 $('reportEvents').innerHTML=(i.recent_events||[]).map(e=>`<div class="data-row"><div><strong>${html(e.event_type)}</strong><br><small>${html(e.actor)}</small></div><span class="caption">${html(e.created_at)}</span></div>`).join('')||'<p class="empty">No events recorded yet.</p>';
 $('dashboardOpenPO').textContent=formatNum(i.open_purchase_orders||0);$('dashboardDraftPO').textContent=formatNum(i.draft_purchase_orders||0);$('dashboardOpenQuality').textContent=formatNum(i.open_quality_cases||0);
}
$('exportReport').addEventListener('click',()=>downloadCSV('meridian-inventory-report.csv',state.stock.map(x=>[x.sku,x.location_code,x.on_hand,x.reserved,x.available]),['sku','location','on_hand','reserved','available']));
$('exportPO').addEventListener('click',()=>downloadCSV('meridian-purchase-orders.csv',ent.purchaseOrders.flatMap(p=>p.lines.map(l=>[p.number,p.supplier_code,p.status,l.sku,l.ordered_qty,l.received_qty,l.remaining,l.unit_price_cents/100])),['po_number','supplier','status','sku','ordered','received','remaining','unit_price_usd']));
$('exportQuality').addEventListener('click',()=>downloadCSV('meridian-quality-cases.csv',ent.quality.map(q=>[q.number,q.summary,q.source,q.severity,q.status,q.item_sku,q.resolution]),['number','summary','source','severity','status','sku','resolution']));
// FAST CROSS-MODULE SEARCH
function setSearchOpen(open){$('commandBackdrop').hidden=!open;document.body.style.overflow=open?'hidden':'';if(open){$('commandInput').value='';renderSearch();$('commandInput').focus();}else{$('openCommand').focus();}}
$('openCommand').addEventListener('click',()=>setSearchOpen(true));$('closeCommand').addEventListener('click',()=>setSearchOpen(false));
$('commandBackdrop').addEventListener('click',ev=>{if(ev.target===$('commandBackdrop'))setSearchOpen(false);});
window.addEventListener('keydown',ev=>{if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='k'){ev.preventDefault();setSearchOpen(true);}if(ev.key==='Escape'&&!$('commandBackdrop').hidden)setSearchOpen(false);});
$('commandInput').addEventListener('input',renderSearch);
$('commandInput').addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.preventDefault();$('commandResults').querySelector('button[data-jump]')?.click();}});
$('commandResults').addEventListener('click',ev=>{const b=ev.target.closest('button[data-jump]');if(!b)return;location.hash=b.dataset.jump;setSearchOpen(false);});
function renderSearch(){const q=$('commandInput').value.toLowerCase().trim();const names=Object.entries(pageTitles).map(([page,title])=>({title,subtitle:'Module',page}));
 const records=[
 ...state.items.map(x=>({title:x.sku,subtitle:`Item · ${x.name}`,page:'inventory'})),
 ...state.orders.map(x=>({title:x.number,subtitle:`Work order · ${x.product_name}`,page:'production'})),
 ...state.boms.map(x=>({title:x.product_sku+' Rev '+x.revision,subtitle:`BOM · ${x.status}`,page:'boms'})),
 ...ent.purchaseOrders.map(x=>({title:x.number,subtitle:`Purchase order · ${x.supplier_name}`,page:'procurement'})),
 ...ent.quality.map(x=>({title:x.number,subtitle:`Quality case · ${x.summary.slice(0,80)}`,page:'quality'}))];
 const matches=[...names,...records].filter(x=>!q||(x.title+' '+x.subtitle+' '+x.page).toLowerCase().includes(q)).slice(0,28);
 $('commandResults').innerHTML=matches.map(x=>`<button class="command-result" type="button" data-jump="${html(x.page)}"><span><strong>${html(x.title)}</strong><br><small>${html(x.subtitle)}</small></span><span>↵</span></button>`).join('')||'<p class="empty">No records match. Try another SKU or module name.</p>';
}
// DATA LOADING
async function load(){try{const [suppliers,purchaseOrders,quality,fields,insights]=await Promise.all(['/api/suppliers','/api/purchase-orders','/api/quality-cases','/api/custom-fields','/api/insights'].map(url=>api(url)));
 Object.assign(ent,{suppliers,purchaseOrders,quality,fields,insights});renderEnterprise();}
 catch(e){toast('Additional modules could not load: '+e.message,true);}
}
function renderEnterprise(){
 pick('poSupplier',ent.suppliers,x=>`${x.code} · ${x.name}`,'Create a supplier first');
 pick('poReceiptOrder',ent.purchaseOrders.filter(x=>['approved','partial'].includes(x.status)),x=>`${x.number} · ${x.supplier_name}`,'No approved POs');
 pick('poReceiptLoc',state.locations,x=>`${x.code} · ${x.name}`,'Create a location');
 pick('qualityItem',state.items,x=>`${x.sku} · ${x.name}`,'No items');
 const itemSelect=$('qualityItem');const old=itemSelect.value;itemSelect.insertAdjacentHTML('afterbegin','<option value="">Unassigned</option>');if(!old)itemSelect.value='';
 $('supplierRows').innerHTML=ent.suppliers.map(s=>`<tr><td><strong>${html(s.code)}</strong></td><td>${html(s.name)}</td><td>${html(s.email||'—')}</td></tr>`).join('')||'<tr><td colspan="3" class="empty">No suppliers yet</td></tr>';
 $('poLines').querySelectorAll('[data-po-item]').forEach(el=>{const previous=el.value;el.innerHTML=optionItems();if([...el.options].some(x=>x.value===previous))el.value=previous;});
 renderPOs();populateReceiptItems();renderQuality();renderFields();renderReports();renderSearch();applyPrefs();
}
window.addEventListener('meridian:data-refreshed',()=>load());
// First render uses initial data from existing dashboard's refresh() if available.
addPOLine();load();
})();
