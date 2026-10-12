/* Market Council add-on 7: system status. Reads state/health.json (written by the health check job): each job's last
   good run, anything late or failed, how old each set of results is, and the price cross-check. Places no orders. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc;
M.extra.health="state/health.json";
function tag(ok,txt){return '<span class="stg '+(ok?"live":"stale")+'">'+txt+'</span>';}
function when(t){return t?esc(MC.when(t))+" ("+esc(MC.ago(t))+")":"never";}
function head(t){return '<div class="fl" style="margin-top:12px;font-weight:800;font-size:11px;letter-spacing:.06em">'+t+'</div>';}
M.slots["sy-extra"]=function(){var h=M.X.health;
if(!h)return M.blk("SYSTEM STATUS",tag(false,"NO REPORT YET"),'<div class="nbx">The health check has not reported yet. It runs every half hour and lists each job&#39;s last good run, anything that failed or was skipped, and how old each set of results is.</div>',"Source: state/health.json, written by the health check job.");
var age=(Date.now()-new Date(h.as_of).getTime())/3600000,silent=age>6,P=h.problems||[];
var top=silent?'<div class="q"><b style="color:var(--tx)">The health check itself has been silent for '+Math.round(age)+' hours.</b> Skipped jobs and stale data are not being watched until it reports again.</div>':"";
var probs=P.map(function(p){return '<div class="q"><b style="color:var(--tx)">'+(p.alert?"Problem":"Note")+':</b> '+esc(p.text)+' <span class="fl" style="font-size:11px">since '+esc(MC.when(p.since))+'</span></div>';}).join("");
var jobs=(h.jobs||[]).map(function(j){var bad=j.late||j.last_result==="failed";
return M.kv(j.name,tag(!bad,j.late?"LATE":(j.last_result==="failed"?"FAILED":"OK"))+" last good run "+when(j.last_ok))+'<div class="src">Runs '+esc(j.schedule||"")+(j.note?". "+esc(j.note):"")+'.</div>';}).join("");
var data=(h.data||[]).map(function(d){return M.kv(d.name,tag(!d.stale,d.stale?"STALE":"FRESH")+" "+(d.as_of?when(d.as_of):"no date in the file"))+(d.note?'<div class="src">'+esc(d.note)+'.</div>':"");}).join("");
var pc=h.price_check,pch="";
if(pc){var held=pc.held||[],one=pc.one_source||[];
pch=head("PRICE CROSS-CHECK")+M.kv("Shares compared with a second source",String(pc.checked||0))+M.kv("Agree within "+Math.round(100*(pc.tolerance||0))+"%",String((pc.agree||[]).length))+
M.kv("Held back",held.length?tag(false,"HELD")+" "+esc(held.join(", ")):"none")+M.kv("One source only, not cross-checked",one.length?esc(one.join(", ")):"none")+
'<div class="src">Second source: '+esc(pc.second_source||"")+'. A card is held back when its price series is a finished day behind, or the two closes differ by more than the tolerance.</div>';}
return M.blk("SYSTEM STATUS",(h.ok&&!silent)?tag(true,"ALL RUNNING"):tag(false,silent?"CHECK SILENT":(P.length+" TO LOOK AT")),
top+probs+head("JOBS")+jobs+head("RESULTS AND ROUTINES")+data+pch,
"Checked "+esc(MC.when(h.as_of))+". "+esc(h.method||"")+" A job that fails also messages your phone at once.");};
var prev=M.cardExtra;
M.cardExtra=function(c){var h=prev?prev(c):"";var p=c&&c.price_check;if(!p)return h;
var line=p.ok===true?"Price cross-check: "+esc(p.why)+".":(p.ok===false?"Price cross-check failed: "+esc(p.why)+".":"Price from one source only: the second source has no prices for this share, so it was not cross-checked.");
return h+'<div class="src">'+line+'</div>';};
M.reload();
})();
