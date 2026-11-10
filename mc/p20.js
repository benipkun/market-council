/* Market Council add-on 20 (10 Nov 2026): the MEMOS page. The investment committee's one-page memos (business, moat, key
   numbers, our DCF range with its main assumption, risks, what would change the view), each vote with dissent by name,
   the Advisor's and partners' reviews, the scores against what happened, and the private-company data report.
   Data: state/memos/index.json (ops/engine/memos.py; memos written by the Investment Committee routine, ops/COMMITTEE.md). */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DOT=" "+String.fromCharCode(183)+" ",DASH=String.fromCharCode(8212);
M.extra.memos="state/memos/index.json";
function money(v){return v==null?DASH:"$"+Number(v).toFixed(2);}
function pct(x){return x==null?DASH:(x>=0?"+":String.fromCharCode(8722))+Math.abs(100*x).toFixed(1)+"%";}
function li(a){return (a||[]).map(function(x){return '<div class="src" style="white-space:normal">'+String.fromCharCode(8226)+" "+esc(typeof x==="string"?x:(x&&x.risk?x.risk+(x.would_show_as?". Would show as: "+x.would_show_as:""):JSON.stringify(x)))+'</div>';}).join("");}
var TAG={APPROVE:"live",DECLINE:"stale","MORE WORK":"lvl"};
function fl(t){return '<div class="fl" style="margin-top:8px">'+t+'</div>';}
function memoHtml(m){var o=m.memo||{},d=o.dcf||{},v=m.vote||{},r=m.reviews||{},adv=r.advisor||{};
var dcf=(d.base!=null)?money(d.low)+" to "+money(d.high)+", base "+money(d.base)+". Main assumption: "+esc(d.main_assumption||"")+". "+esc(d.label||"Estimate."):esc(d.reason||d.note||"Not valued by our own model.");
return '<details class="q gap"><summary><b style="color:var(--tx)">'+esc(m.ticker)+'</b> '+esc(m.name||"")+DOT+esc(String(m.date||"").slice(0,10))+' <span class="stg '+(TAG[v.decision]||"paper")+'">'+esc(v.decision||"NO VOTE")+'</span></summary>'+
fl("BUSINESS")+'<div style="white-space:normal;font-size:13px">'+esc(o.business||DASH)+'</div>'+
fl("MOAT")+'<div style="white-space:normal;font-size:13px">'+esc(o.moat||DASH)+'</div>'+
fl("KEY NUMBERS")+(o.key_numbers||[]).map(function(k){return '<div class="src" style="white-space:normal">'+esc(k.name)+': <b style="color:var(--tx)">'+esc(String(k.value))+'</b> ('+esc(k.source||"no source")+')</div>';}).join("")+
fl("DCF VALUE (ESTIMATE)")+'<div class="src" style="white-space:normal">'+dcf+'</div>'+
fl("RISKS")+li(o.risks)+fl("WHAT WOULD CHANGE THE VIEW")+li(o.would_change_view)+
fl("COMMITTEE VOTE")+(v.votes||[]).map(function(x){return '<div class="src" style="white-space:normal"><b style="color:var(--tx)">'+esc(x.partner)+'</b> <span class="stg '+(TAG[x.vote]||"paper")+'">'+esc(x.vote)+'</span> '+esc(x.reason||"")+'</div>';}).join("")+
((v.dissent||[]).length?'<div class="src" style="white-space:normal;color:var(--wn)">Dissent: '+(v.dissent||[]).map(function(x){return esc(x.partner)+" ("+esc(x.reason||"")+")";}).join("; ")+'</div>':'<div class="src">No dissent.</div>')+
fl("REVIEWS")+'<div class="src" style="white-space:normal">Advisor, grade '+esc(adv.grade||DASH)+": "+esc((adv.questions||[]).join(" "))+'</div>'+
(r.partners||[]).map(function(x){return '<div class="src" style="white-space:normal">'+esc(x.partner)+" "+esc(String(x.score))+"/5: "+esc(x.note||"")+'</div>';}).join("")+
'<div class="src" style="opacity:.7;margin-top:6px">'+esc(m.label||"")+'</div></details>';}
function scoreRow(m){var s=m.score||{},k=Object.keys(s.marks||{}),last=k.length?s.marks[k[k.length-1]]:null;
return '<div class="src" style="white-space:normal">'+esc(m.ticker)+DOT+esc(String(m.date).slice(0,10))+DOT+esc((m.vote||{}).decision||"")+DOT+(last?k[k.length-1]+": share "+pct(last.share)+" vs S&P "+pct(last.spy)+(last.decision_right==null?"":(last.decision_right?" (decision right)":" (decision wrong)")):"not scored yet: the first mark is one month after the memo")+'</div>';}
function voteRow(m){var v=m.vote||{};return '<div class="src" style="white-space:normal"><b style="color:var(--tx)">'+esc(m.ticker)+'</b> <span class="stg '+(TAG[v.decision]||"paper")+'">'+esc(v.decision||"")+'</span> '+(v.votes||[]).map(function(z){return esc(z.partner)+": "+esc(z.vote);}).join(DOT)+((v.dissent||[]).length?DOT+"dissent: "+(v.dissent||[]).map(function(z){return esc(z.partner);}).join(", "):"")+'</div>';}
function privHtml(pv){return '<div class="q" style="white-space:normal">'+esc(pv.goal)+'</div>'+(pv.sources||[]).map(function(s){return '<details class="q gap"><summary>'+esc(s.name)+'</summary><div class="src" style="white-space:normal">Free: '+esc(s.free)+'</div>'+(s.paid?'<div class="src" style="white-space:normal">Paid: '+esc(s.paid)+'</div>':"")+'<div class="src" style="white-space:normal">Limits: '+esc(s.limits)+'</div>'+(s.covers_owner_age?'<div class="src" style="white-space:normal">Owner age: '+esc(s.covers_owner_age)+'</div>':"")+'</details>';}).join("")+
fl("WHAT IT CANNOT TELL US")+li(pv.cannot_tell)+fl("PERSONAL DATA (GDPR)")+'<div class="src" style="white-space:normal">'+esc(pv.gdpr)+'</div>'+fl("PROPOSAL")+'<div class="src" style="white-space:normal">'+esc(pv.proposal)+'</div><div class="q gap" style="white-space:normal;color:var(--wn)">'+esc(pv.decision_needed)+'</div>';}
function html(){var x=M.X.memos;if(!x)return "";var open=x.open||[],sc=x.scores||{},pv=x.private;
var h=M.blk("OPEN MEMOS",'<span class="stg lvl">'+open.length+'</span>',open.length?open.map(memoHtml).join(""):'<div class="msg">No memo yet. The committee writes up to two each weekday morning; next: '+esc((x.queue||[]).slice(0,4).map(function(q){return q.ticker;}).join(", "))+'.</div>',"One page per company. Values are estimates from our own model unless marked as an outside model.");
h+=M.blk("COMMITTEE VOTES","",open.length?open.map(voteRow).join(""):'<div class="msg">No votes yet.</div>',"APPROVE adds the company to the committee's paper book only; it is not an order.");
h+=M.blk("SCORED MEMOS",'<span class="stg paper">'+esc(String(sc.scored||0))+" OF "+esc(String(sc.memos||0))+'</span>',((x.all||[]).map(scoreRow).join("")||'<div class="msg">Nothing to score yet.</div>')+(sc.honesty?'<div class="src">'+esc(sc.honesty)+'</div>':""),esc(x.score_method||""));
if(pv)h+=M.blk("PRIVATE COMPANIES",'<span class="stg stale">REPORT ONLY</span>',privHtml(pv),"Nothing is built or bought until you say yes.");
return h;}
function render(){var el=$("v-memos");if(!el)return;var h=html()||'<div class="msg">The memos appear after the next engine run.</div>';if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);render();};
MC.hooks.push(render);
M.reload();
})();
