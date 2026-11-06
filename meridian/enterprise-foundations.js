/* Ledger, costing and integration preview for independent local ERP prototype.
 * Finance companies do not isolate legacy inventory/work orders.
 */
(()=>{
'use strict';
const el=id=>document.getElementById(id),esc=escapeHTML;
let companies=[],accounts=[],journal=[],trial=[],valuation=null;
let selected=0;
const money=cents=>(Number(cents||0)/100).toLocaleString('en-US',{style:'currency',currency:'USD'});
const rowsHtml=(rs,fn)=>rs.map(fn).join('');
const pick=(id,rs,title)=>{const e=el(id),old=e.value;e.innerHTML=rs.length?rs.map(r=>`<option value="${Number(r.id)}">${esc(title(r))}</option>`).join(''):'<option value="">No records</option>';if([...e.options].some(o=>o.value===old))e.value=old;};
const values=f=>Object.fromEntries(new FormData(f));
async function run(action){try{await action();await refreshFinance();}catch(e){toast(e.message,true);}}
async function refreshFinance(){
 try{
 companies=await api('/api/finance/companies');
 pick('financeCompany',companies,x=>`${x.code} · ${x.name}`);
 selected=Number(el('financeCompany').value)||0;
 if(!selected){accounts=[];journal=[];trial=[];valuation=null;render();return;}
 [accounts,journal,trial,valuation]=await Promise.all([
   api(`/api/finance/accounts?company_id=${selected}`),api(`/api/finance/journals?company_id=${selected}`),
   api(`/api/finance/trial-balance?company_id=${selected}`),api(`/api/finance/valuation?company_id=${selected}`)]);
 render();
 }catch(e){toast('Finance demo could not load: '+e.message,true);}
}
function render(){
 el('financeCompanyCount').textContent=String(companies.length);
 el('financeAccountCount').textContent=String(accounts.length);
 el('financeJournalCount').textContent=String(journal.length);
 el('financeValue').textContent=money(valuation?.total_cents||0);
 const getItem=id=>state.items.find(x=>x.id===Number(id));
 pick('financeCostItem',state.items,x=>x.sku+' · '+x.name);
 pick('financeAccountDebit',accounts,x=>x.code+' · '+x.name);
 pick('financeAccountCredit',accounts,x=>x.code+' · '+x.name);
 el('financeAccounts').innerHTML=rowsHtml(accounts,x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${esc(x.category)}</td></tr>`)||'<tr><td colspan="3">Add accounts to this company</td></tr>';
 el('financeTrial').innerHTML=rowsHtml(trial,x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${money(x.debit_cents)}</td><td>${money(x.credit_cents)}</td></tr>`)||'<tr><td colspan="4">No account balances</td></tr>';
 el('financeJournals').innerHTML=rowsHtml(journal,x=>`<tr><td>${esc(x.reference)}</td><td>${esc(x.memo)}</td><td>${money(x.total_debit_cents)}</td></tr>`)||'<tr><td colspan="3">No journals</td></tr>';
 el('financeValuation').innerHTML=rowsHtml(valuation?.rows||[],x=>`<tr><td>${esc(x.sku)}</td><td>${Number(x.on_hand)}</td><td>${money(x.standard_cost_cents)}</td><td>${money(x.indicative_value_cents)}</td></tr>`)||'<tr><td colspan="4">No items</td></tr>';
}
el('financeCompany').addEventListener('change',refreshFinance);
el('financeCompanyForm').addEventListener('submit',e=>{e.preventDefault();const f=values(e.target);run(async()=>{await api('/api/finance/companies','POST',f);toast('Finance company created. Legacy inventory remains shared demo data.');e.target.reset();});});
el('financeAccountForm').addEventListener('submit',e=>{e.preventDefault();const f=values(e.target);if(!selected)return toast('Create a company first.',true);run(async()=>{await api('/api/finance/accounts','POST',{...f,company_id:selected});toast('Account added.');e.target.reset();});});
el('financeJournalForm').addEventListener('submit',e=>{e.preventDefault();const f=values(e.target);if(!selected)return toast('Create a company first.',true);
 const debit=Math.round(Number(f.amount)*100);if(!Number.isSafeInteger(debit)||debit<=0||debit>1e12)return toast('Enter a positive valid USD amount.',true);
 if(!f.debit_account||!f.credit_account||f.debit_account===f.credit_account)return toast('Use two different ledger accounts.',true);
 run(async()=>{await api('/api/finance/journals','POST',{company_id:selected,reference:f.reference,memo:f.memo,lines:[{account_id:Number(f.debit_account),debit_cents:debit,credit_cents:0},{account_id:Number(f.credit_account),debit_cents:0,credit_cents:debit}]});toast('Balanced journal posted.');e.target.reset();});
});
el('financeCostForm').addEventListener('submit',e=>{e.preventDefault();const f=values(e.target);if(!selected)return toast('Create a company first.',true);const cents=Math.round(Number(f.cost)*100);if(!Number.isSafeInteger(cents)||cents<0)return toast('Enter a valid unit cost.',true);
 run(async()=>{await api('/api/finance/costs','PUT',{company_id:selected,item_id:Number(f.item_id),cost_cents:cents});toast('Indicative standard cost updated.');});});
el('stockCsvExample').addEventListener('click',()=>{el('stockCsvText').value='sku,location,quantity,reference\nBOLT-001,MAIN,5,EXAMPLE-PO-01\nPANEL-001,MAIN,2,EXAMPLE-PO-02';});
el('stockCsvPreviewForm').addEventListener('submit',async e=>{e.preventDefault();try{
 const result=await api('/api/integrations/stock-import/preview','POST',{csv_text:el('stockCsvText').value});
 el('stockCsvSummary').textContent=`${result.valid_count} of ${result.total_rows} rows valid. No records posted.`;
 el('stockCsvPreview').innerHTML=rowsHtml(result.rows,x=>`<tr><td>${esc(x.sku)}</td><td>${esc(x.location)}</td><td>${Number(x.quantity)}</td><td>${x.valid?'Valid':esc(x.issues.join(', '))}</td></tr>`);
 }catch(error){toast(error.message,true);}
});
window.addEventListener('meridian:data-refreshed',()=>refreshFinance());
refreshFinance();
})();
