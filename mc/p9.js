/* Market Council add-on 9: the live track record and honest labels. Reads state/track.json (plain code): every idea
   logged on the day it was raised, measured after fees against the index fund and the average share of the same list,
   and the rule, written in advance, for dropping a check. Marks every idea card that rests on unproven checks. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.track="state/track.json";
var DASH=String.fromCharCode(8212),MK=[["1m","One month"],["3m","Three months"],["6m","Six months"],["12m","Twelve months"],["now","To date"]];
var CN={value:"Value",quality:"Quality",momentum:"Momentum",trend:"Trend",insiders:"Insiders",holders:"Holders",drift:"Results drift"};
function T(){return M.X.track;}
function sg(v){return v==null?DASH:(v>0?"+":"")+(100*v).toFixed(1)+"%";}
function pc(v){return v==null?DASH:Math.round(100*v)+"%";}
function marks(t){if(!t)return "";
return '<div class="ox"><table class="mt" style="width:100%;font-size:12px"><tr><th style="text-align:left">After</th><th>Ideas</th><th>Ideas made</th><th>Index fund</th><th>Average share</th><th>Beat the index</th><th>Beat the list</th></tr>'+
MK.map(function(m){var r=t[m[0]]||{n:0};if(!r.n)return '<tr style="opacity:.5"><td>'+m[1]+'</td><td style="text-align:center">0</td><td colspan="5" style="text-align:center">none has reached this mark</td></tr>';
return '<tr'+(r.few?' style="opacity:.6"':'')+'><td>'+m[1]+(r.few?' <span class="fl" style="font-size:10px">too few cases</span>':'')+'</td><td style="text-align:center">'+r.n+'</td><td style="text-align:center">'+sg(r.idea)+'</td><td style="text-align:center">'+sg(r.spy)+'</td><td style="text-align:center">'+sg(r.list)+'</td><td style="text-align:center">'+pc(r.beat_spy)+'</td><td style="text-align:center">'+pc(r.beat_list)+'</td></tr>';}).join("")+'</table></div>';}
function state(c){var t=T(),k=t&&t.checks&&t.checks[c];return k?k.state:"unproven";}
function checksBlock(t){var ids=Object.keys(t.checks||{});
var rows=ids.map(function(c){var k=t.checks[c],a=(k.passed||{})["3m"]||{},b=(k.passed||{})["6m"]||{},st=k.state;
return '<tr><td>'+esc(CN[c]||c)+'</td><td style="text-align:center"><span class="stg '+(st==="proven"?"live":(st==="dropped"?"stale":"paper"))+'">'+st.toUpperCase()+'</span></td><td style="text-align:center">'+(a.n||0)+'</td><td style="text-align:center">'+sg(a.vs_spy)+'</td><td style="text-align:center">'+sg(a.vs_list)+'</td><td style="text-align:center">'+(b.n||0)+'</td><td style="text-align:center">'+sg(b.vs_spy)+'</td><td style="text-align:center">'+sg(b.vs_list)+'</td></tr>';}).join("");
var dr=Object.keys(t.dropped||{}).map(function(c){var d=t.dropped[c];return '<div class="q"><b style="color:var(--tx)">'+esc(CN[c]||c)+' was dropped on '+esc(d.on)+'.</b> Ideas passing it: '+sg(d.three_months.vs_spy)+' against the index fund and '+sg(d.three_months.vs_list)+' against the average share at three months ('+d.three_months.n+' ideas); '+sg(d.six_months.vs_spy)+' and '+sg(d.six_months.vs_list)+' at six months ('+d.six_months.n+').</div>';}).join("");
return M.blk("THE DROP RULE",'<span class="stg live">WRITTEN IN ADVANCE</span>','<div style="font-size:12.5px;white-space:normal">'+esc(t.rule||"")+'</div>'+(dr||'<div class="q">No check has been dropped. None has the 30 ideas at both marks that the rule needs.</div>')+
(rows?'<div class="ox"><table class="mt" style="width:100%;font-size:12px"><tr><th style="text-align:left">Ideas that passed</th><th>State</th><th>At 3 months</th><th>vs index</th><th>vs list</th><th>At 6 months</th><th>vs index</th><th>vs list</th></tr>'+rows+'</table></div>':'<div class="src">No idea with a checklist has been logged yet.</div>'),
"All seven checks stay labelled unproven until this table, or a fair back-test on data that includes failed companies, says otherwise.");}
function ideas(t){var L=(t.ideas||[]).slice().reverse();if(!L.length)return "";
return '<details class="p3d"><summary>Every idea in the log ('+t.count+')</summary>'+L.map(function(r){var n=r.now;
return '<div class="src"><b style="color:var(--tx)">'+esc(r.t)+'</b> raised '+esc(r.day)+' at $'+r.price+' '+String.fromCharCode(183)+' '+(r.offered?"offered":"greyed out")+(r.late?", added afterwards":"")+' '+String.fromCharCode(183)+' '+
(n?'to date '+sg(n.idea)+', index fund '+sg(n.spy)+', average share '+sg(n.list)+' ('+n.days+' trading days)':esc(r.note||"not measured yet"))+'</div>';}).join("")+'</details>';}
function html(){var t=T();if(!t)return '<div class="msg">The track record has not been measured yet. It is measured after each US trading day.</div>';
return M.blk("LIVE TRACK RECORD",t.intact?'<span class="stg live">UNEDITED LOG</span>':'<span class="stg stale">LOG CHECK FAILED</span>',
'<div class="q"><b style="color:var(--tx)">'+esc(t.verdict||"")+'</b></div>'+M.kv("Ideas logged",String(t.count||0))+M.kv("First idea",esc(t.first||"none yet"))+M.kv("Measured to",esc(t.to||""))+
'<div class="fl" style="margin-top:10px;font-weight:800;font-size:11px">EVERY IDEA, OFFERED OR GREYED OUT</div>'+marks(t.all)+
'<details class="p3d"><summary>Only the ideas that were offered to you</summary>'+marks(t.offered)+'</details>'+
'<details class="p3d"><summary>Only the ideas that were greyed out</summary>'+marks(t.greyed)+'</details>'+ideas(t)+
'<div class="src" style="margin-top:6px">'+esc(t.method||"")+'</div><div class="src">'+esc(t.honesty||"")+'</div>',
"Measured "+M.upd(t.as_of)+". Every idea is written down once, on the day it is raised, and none is left out or edited afterwards.")+checksBlock(t);}
function render(){var el=$("v-record");if(!el)return;var h=html();if(el.__h!==h){var open={};Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){if(d.open)open[i]=1;});var had=el.__h!=null;el.innerHTML=h;el.__h=h;
if(had)Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){d.open=!!open[i];});}}
/* the label above every idea card that rests on checks which have not proved themselves */
M.cardTop=function(c){if(!c||c.kind!=="idea")return "";var ks=(c.checks||[]).filter(function(k){return k.pass===true&&state(k.id)!=="proven";});
if(!ks.length)return "";
return '<div class="q" style="border-left:3px solid var(--wn);padding-left:8px"><span class="stg paper">UNPROVEN</span> This idea rests on '+ks.length+' check'+(ks.length===1?"":"s")+' that '+(ks.length===1?"has":"have")+' not yet shown, in the live record or in a fair back-test, that '+(ks.length===1?"it picks":"they pick")+' better shares: '+esc(ks.map(function(k){return (CN[k.id]||k.id).toLowerCase();}).join(", "))+'. <button class="btn sm" data-tab="record">See the record</button></div>';};
var prevCc=M.slots["cc-extra"];
M.slots["cc-extra"]=function(){setTimeout(render,0);var top=prevCc?prevCc():"",t=T();
return top+M.blk("LIVE TRACK RECORD",'<span class="stg paper">'+(t&&t.all&&t.all["3m"]&&t.all["3m"].n>=20?"MEASURED":"TOO EARLY TO JUDGE")+'</span>',
'<div style="font-size:12.5px;white-space:normal">'+esc((t&&t.verdict)||"Not measured yet.")+'</div><div class="gap"><button class="btn sm" data-tab="record">Open the record</button></div>',
"Every idea, against the index fund and the average share of the same list, after fees.");};
MC.hooks.push(render);
M.reload();
})();
