/* Market Council add-on 19 (10 Nov 2026): prove it first. On TODAY, under the answer: each signal's back-test (past cases,
   how often they rose), its paper record against the S&P 500 fund after fees, and its progress toward the line where it may
   raise real-money cards; the core (S&P 500 fund), the conviction bet (UBER) and the capped side portion for stock ideas.
   Under every card: its evidence line. On SYSTEM: today's running cost. Data from state/actions.json "proof" and
   state/costs.json, written by plain code. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,DASH=String.fromCharCode(8212);
M.extra.costs="state/costs.json";
function pct(x){return x==null?DASH:(x>=0?"+":String.fromCharCode(8722))+Math.abs(100*x).toFixed(1)+"%";}
function proofBlk(){var a=M.X.acts||{},p=a.proof;if(!p||!p.signals)return "";var sp=p.split||{};
var rows=p.signals.filter(function(s){return s;}).map(function(s){var b=s.backtest||{},q=s.paper||{};
return '<tr><td style="white-space:normal">'+esc(s.name)+'</td><td>'+(b.cases?Number(b.cases).toLocaleString("en-US"):DASH)+(b.hit!=null?" "+String.fromCharCode(183)+" "+Math.round(100*b.hit)+"%":"")+'</td><td>'+esc(String(Math.min(q.at_mark||0,p.paper_min)))+" of "+esc(String(p.paper_min))+" "+String.fromCharCode(183)+" "+esc(String(q.logged||0))+' logged</td><td>'+(q.at_mark?pct(q.vs_spy_mark):(q.measured_now?pct(q.vs_spy_now)+" early":DASH))+'</td><td><span class="stg '+(s.proven?"live":"paper")+'">'+(s.proven?"PROVEN":"PAPER")+'</span></td></tr>';}).join("");
var conv=(sp.conviction||[]).map(function(c){return '<div class="src" style="white-space:normal">Conviction bet: '+esc(c.ticker)+" $"+Number(c.value||0).toFixed(0)+" ("+Math.round(100*(c.share||0))+"% of the portfolio)"+(c.target?", your target $"+Number(c.target).toFixed(2):"")+(c.review?" by "+esc(c.review):"")+'.</div>';}).join("");
return M.blk("PROVE IT FIRST",'<span class="stg paper">PAPER FIRST</span>',
'<div class="src" style="white-space:normal">'+esc(p.rule||"")+'</div>'+
'<div class="q gap"><b style="color:var(--tx)">Core and side portion.</b> '+esc(sp.text||"")+" Core (S&P 500 fund) $"+Number(sp.core_usd||0).toFixed(0)+'.</div>'+conv+
'<div style="overflow-x:auto"><table class="tb" style="margin-top:8px;font-size:12px"><tr><th>SIGNAL</th><th>PAST CASES '+String.fromCharCode(183)+' ROSE</th><th>PAPER AT 3 MONTHS</th><th>VS S&amp;P AFTER FEES</th><th></th></tr>'+rows+'</table></div>',
"Past cases: our back-test since 2000 on 300 shares (six months on; rules per trade). Paper: every idea since 7 Oct 2026, after fees. Early reads are under three months and prove nothing yet.");}
function costBlk(){var c=M.X.costs;if(!c||!c.routines)return "";
return M.blk("RUNNING COST TODAY",'<span class="stg lvl">'+esc(String(c.day||""))+'</span>','<div class="q" style="white-space:normal">'+esc(c.text)+'</div>'+
c.routines.map(function(r){return '<div class="src" style="white-space:normal">'+esc(r.name)+" ("+esc(r.model)+"): "+esc(String(r.worked))+" with work"+(r.note?". "+esc(r.note):"")+'.</div>';}).join(""),esc(c.method||""));}
var prevTd=M.slots["td-dec"];M.slots["td-dec"]=function(){var h=prevTd?prevTd():"";return h+proofBlk();};
var prevSy=M.slots["sy-extra"];M.slots["sy-extra"]=function(){var h=prevSy?prevSy():"";return h+costBlk();};
var prevTop=M.cardTop;M.cardTop=function(c){var h=prevTop?prevTop(c):"",v=c&&c.verdict;if(v&&v.proof)h+='<div class="src" style="white-space:normal;opacity:.8">'+esc(v.proof)+'</div>';return h;};
M.reload();
})();
