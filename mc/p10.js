/* Market Council add-on 10: partner meetings. Five partners judge whether the whole operation is profitable and call
   out problems early. Their figures come from state/partners/statement.json (plain code); the minutes, the register of
   open issues and the list of meetings are written by the meeting run (rulebook ops/PARTNERS.md in the records).
   Partners advise; nothing here places or prepares an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.pmin="state/partners/latest.json";M.extra.preg="state/partners/register.json";M.extra.pst="state/partners/statement.json";M.extra.pidx="state/partners/index.json";
var API="https://api.github.com/repos/benipkun/market-council-state",DOT=String.fromCharCode(183),DASH=String.fromCharCode(8212),note="";
function usd(v){return v==null?DASH:(v<0?"-":"")+"$"+Math.abs(v).toFixed(2);}
function pct(v,d){return v==null?DASH:(100*v).toFixed(d==null?1:d)+"%";}
function head(t){return '<div class="fl" style="margin-top:12px;font-weight:800;font-size:11px;letter-spacing:.06em">'+t+'</div>';}
function para(t){return String(t||"").split(String.fromCharCode(10)).filter(function(x){return x.trim();}).map(function(x){return '<div style="font-size:12.5px;white-space:normal;margin:4px 0">'+esc(x)+'</div>';}).join("");}
function statement(s){if(!s)return "";var a=s.against_index||{},r=s.real_money||{},p=s.paper_record||{},f=s.forecasts||{},b=f.backtest||{},k=s.risk||{},c=s.running_costs||{},m=s.machine||{};
return M.blk("THE STATEMENT",'<span class="stg live">PLAIN CODE</span>','<div class="q"><b style="color:var(--tx)">'+esc(s.bottom_line||"")+'</b></div>'+
head("REAL MONEY")+M.kv("Value now",usd(r.value_now))+M.kv("Unrealised gain or loss",usd(r.unrealised))+M.kv("Realised this year",usd(r.realised_this_year))+M.kv("Fees recorded",usd(r.fees_recorded)+" on "+(r.trades_recorded||0)+" trades")+(r.fee_note?'<div class="src">'+esc(r.fee_note)+'</div>':"")+
head("AGAINST DOING NOTHING")+(a.from?M.kv("Since",esc(a.from))+M.kv("Portfolio result",usd(a.result)+" ("+pct(a.result_pct)+")")+M.kv("Same money in the index fund",usd(a.index_result)+" ("+pct(a.index_result_pct)+")")+M.kv("Ahead of the index fund",usd(a.ahead_of_index)):'<div class="src">Not worked out this run.</div>')+
'<div class="src">'+esc((s.period||{}).note||"")+'</div>'+
head("PAPER RECORD")+M.kv("Ideas logged",String(p.ideas_logged==null?0:p.ideas_logged))+'<div class="src">'+esc(p.verdict||"")+'</div>'+
head("FORECASTS")+M.kv("Logged / checked",(f.logged||0)+" / "+(f.checked||0))+'<div class="src">'+esc(f.verdict||"")+' Back-test: '+esc(b.verdict||"none")+' ('+(b.cases||0)+' cases).</div>'+
head("RUNNING COSTS")+(c.known?M.kv("Per month",usd(c.usd_per_month)):'<div class="src">'+esc(c.note||"")+'</div>')+
head("CONCENTRATION AND THE BAD YEAR")+M.kv("Largest holding",esc(k.largest||DASH)+" "+pct(k.largest_share,0))+M.kv("Bad year (one in ten)",pct(k.bad_year))+M.kv("Under its high",pct(k.under_high))+
head("THE MACHINE")+M.kv("All jobs running",m.all_running===true?"yes":(m.all_running===false?"no":"not known"))+(m.problems||[]).map(function(x){return '<div class="src">'+esc(x)+'</div>';}).join("")+
((s.emergency||[]).length?head("EMERGENCY MEETING DUE")+s.emergency.map(function(x){return '<div class="q" style="color:var(--wn)">'+esc(x)+'</div>';}).join(""):""),
"Worked out "+M.upd(s.as_of)+". "+esc(s.method||""));}
function minutes(m){if(!m)return M.blk("PARTNER MEETINGS",'<span class="stg paper">NO MEETING YET</span>','<div class="nbx">No meeting has been held yet. A short one is held every Saturday and a full one on the first Saturday of the month.</div>',"");
var v=m.verdict||{},tag=v.profitable==="yes"?'<span class="stg live">PROFITABLE</span>':(v.profitable==="no"?'<span class="stg stale">NOT PROFITABLE</span>':'<span class="stg paper">NOT PROVEN</span>');
var probs=(m.problems||[]).map(function(p){return '<div class="q"><b style="color:var(--tx)">'+(p.rank||"")+'. '+esc(p.text)+'</b><div class="src">Cost: '+esc(p.cost||DASH)+' '+DOT+' Likelihood: '+esc(p.likelihood||DASH)+' '+DOT+' Raised by '+esc(p.raised_by||DASH)+'</div></div>';}).join("");
var acts=(m.actions||[]).map(function(a){return '<div class="src"><b style="color:var(--tx)">'+esc(a.id||"")+'</b> '+esc(a.text)+' '+DOT+' owner <b style="color:var(--tx)">'+esc(a.owner||DASH)+'</b> '+DOT+' by '+esc(a.due||DASH)+'</div>';}).join("");
var h=M.blk("THE VERDICT",tag,'<div class="q"><b style="color:var(--tx);font-size:14px">'+esc(v.first_line||"")+'</b></div>'+para(v.text)+
(probs?head("THE THREE BIGGEST UPCOMING PROBLEMS")+probs:"")+((m.flaws||[]).length?head("FLAWS FOUND")+m.flaws.map(function(x){return '<div class="src">'+esc(x)+'</div>';}).join(""):"")+(acts?head("ACTION ITEMS")+acts:""),
esc(m.mode||"")+" meeting of "+esc(m.date||"")+". "+(m.blind?"Each partner wrote a position alone before seeing the others.":"The positions were written in one run, so they are not truly independent.")+" Partners advise; you decide and place every order.");
h+=M.blk("EACH PARTNER'S POSITION",'<span class="stg paper">'+(m.positions||[]).length+' PARTNERS</span>',(m.positions||[]).map(function(p){return '<details class="p3d"><summary>'+esc(p.partner)+'</summary>'+para(p.text)+'</details>';}).join("")+
((m.challenges||[]).length?head("THE CHALLENGE ROUND")+m.challenges.map(function(c){return '<div class="q"><b style="color:var(--tx)">'+esc(c.from)+' to '+esc(c.to)+':</b> '+esc(c.text)+'</div>';}).join(""):"")+
(m.premortem?head("THE SCEPTIC'S PRE-MORTEM")+para(m.premortem):"")+(m.opposite?head("THE CONTRARIAN'S OPPOSITE CASE")+para(m.opposite):"")+
((m.votes||[]).length?head("VOTES")+m.votes.map(function(x){return '<div class="q"><b style="color:var(--tx)">'+esc(x.question)+'</b> '+esc(x.result||"")+'<div class="src">For: '+esc((x["for"]||[]).join(", ")||"nobody")+' '+DOT+' Against: '+esc((x.against||[]).join(", ")||"nobody")+((x.abstain||[]).length?' '+DOT+' Abstained: '+esc(x.abstain.join(", ")):"")+(x.dissent?' '+DOT+' Dissent: '+esc(x.dissent):"")+'</div></div>';}).join(""):""),"");
var rv=m.review||{};
if((rv.actions||[]).length||(rv.warnings||[]).length)h+=M.blk("LAST MEETING, CHECKED",'<span class="stg paper">REVIEW</span>',(rv.actions||[]).map(function(a){return '<div class="src"><b style="color:var(--tx)">'+esc(a.id||"")+'</b> '+esc(a.text)+': <b style="color:var(--tx)">'+esc(a.status||"")+'</b>'+(a.note?' '+DASH+' '+esc(a.note):"")+'</div>';}).join("")+
(rv.warnings||[]).map(function(w){return '<div class="src">'+esc(w.partner)+' warned on '+esc(w.date)+': '+esc(w.text)+' '+DASH+' <b style="color:var(--tx)">'+esc(w.outcome||"")+'</b></div>';}).join(""),"");
var u=m.usage||{};
h+='<div class="src" style="margin:8px 4px">Usage of this meeting: '+(u.runs||1)+' run'+((u.runs||1)===1?"":"s")+', about '+(u.words_read||0)+' words read and '+(u.words_written||0)+' written. '+esc(u.note||"")+'</div>';return h;}
function register(r){if(!r)return "";var open=(r.issues||[]).filter(function(i){return i.status==="open";}),closed=(r.issues||[]).filter(function(i){return i.status!=="open";});
function row(i){return '<div class="src"><b style="color:var(--tx)">'+esc(i.id)+'</b> '+esc(i.text)+' '+DOT+' raised by '+esc(i.raised_by||DASH)+' on '+esc(i.raised_on||DASH)+(i.status!=="open"?' '+DOT+' <b style="color:var(--tx)">'+esc(i.status)+'</b> '+esc(i.closed_on||"")+(i.note?' ('+esc(i.note)+')':""):"")+'</div>';}
var acts=(r.actions||[]).filter(function(a){return a.status==="open"||a.status==="late";});
return M.blk("OPEN-ISSUES REGISTER",'<span class="stg '+(open.length?"stale":"live")+'">'+open.length+' OPEN</span>',(open.length?open.map(row).join(""):'<div class="q">No open issue.</div>')+
(acts.length?head("ACTION ITEMS STILL OPEN")+acts.map(function(a){return '<div class="src"><b style="color:var(--tx)">'+esc(a.id||"")+'</b> '+esc(a.text)+' '+DOT+' '+esc(a.owner||DASH)+' '+DOT+' by '+esc(a.due||DASH)+(a.status==="late"?' '+DOT+' <b style="color:var(--wn)">late</b>':"")+'</div>';}).join(""):"")+
(closed.length?'<details class="p3d"><summary>Fixed or dropped ('+closed.length+')</summary>'+closed.map(row).join("")+'</details>':""),
"Every problem a partner raises stays here until it is fixed or formally dropped by a recorded vote.");}
function past(x){var L=((x&&x.meetings)||[]).slice().reverse();if(L.length<2)return "";
return '<details class="p3d" style="margin:8px 4px"><summary>Earlier meetings ('+(L.length-1)+')</summary>'+L.slice(1).map(function(m){return '<div class="src"><b style="color:var(--tx)">'+esc(m.date)+' '+esc(m.mode)+'</b> '+esc(m.first_line||"")+'</div>';}).join("")+'</details>';}
function html(){var X=M.X;return minutes(X.pmin)+register(X.preg)+statement(X.pst)+past(X.pidx)+
'<div class="gap" style="margin:10px 4px"><button class="btn sm" data-p10="call">Call a meeting now</button> <span class="fl" style="font-size:11px">'+esc(note)+'</span></div>';}
function render(){var el=$("v-partners");if(!el)return;var h=html();if(el.__h!==h){var open={};Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){if(d.open)open[i]=1;});var had=el.__h!=null;el.innerHTML=h;el.__h=h;
if(had)Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){d.open=!!open[i];});}}
/* "Call a meeting" writes one line to the inbox queue; the Trade Inbox routine starts the meeting from it. */
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p10]"):null;if(!b)return;var tok=MC.store(MC.K.tok);
if(!tok){note="Add your token in the Log tab first.";render();return;}
var ts=new Date().toISOString().replace(/[-:]/g,"").slice(0,15)+"Z",body="partners: meeting called from the app"+String.fromCharCode(10);
note="Sending"+String.fromCharCode(8230);render();
fetch(API+"/contents/inbox/queue/"+ts+"-partners.md",{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:"Market Council: partner meeting called",content:btoa(body)})})
.then(function(r){note=r.ok?"Called. The minutes appear here when the meeting is over, usually within a few minutes.":"Could not be sent ("+r.status+").";render();}).catch(function(){note="Could not be sent. Check your connection.";render();});});
var prevCc=M.slots["cc-extra"];
M.slots["cc-extra"]=function(){setTimeout(render,0);var top=prevCc?prevCc():"",m=M.X.pmin,r=M.X.preg,open=((r&&r.issues)||[]).filter(function(i){return i.status==="open";}).length;
return top+M.blk("PARTNERS",'<span class="stg paper">CRITICS, NOT CHEERLEADERS</span>','<div style="font-size:12.5px;white-space:normal">Five partners judge whether the whole operation is profitable and call out problems before they cost money: the Managing Partner, the Sceptic, the Numbers Partner, the Contrarian and the Operator. They advise; you decide.</div>'+
(m?'<div class="q"><b style="color:var(--tx)">'+esc((m.verdict||{}).first_line||"")+'</b> <span class="fl" style="font-size:11px">'+esc(m.date||"")+'</span></div>':'<div class="nbx">No meeting yet.</div>')+M.kv("Open issues",String(open))+
'<div class="gap"><button class="btn sm" data-tab="partners">Open the minutes</button></div>',"A short meeting every Saturday, a full one on the first Saturday of the month, and an emergency one when the portfolio falls 15% from its high or a job stays broken.");};
MC.hooks.push(render);
M.reload();
})();
