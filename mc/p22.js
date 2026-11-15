/* Market Council add-on 22 (15 Nov 2026): results in parts, Ben's standing decision. On TODAY and PORTFOLIO: the system
   picks (after fees, against the S&P 500 fund), his own picks, the conviction holding (UBER, kept by his choice), and the
   total line. PORTFOLIO also states the conviction holding's share of the portfolio once, as a fact.
   Data: state/results.json (ops/engine/results.py). */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DOT=" "+String.fromCharCode(183)+" ",DASH=String.fromCharCode(8212);
M.extra.results="state/results.json";
function usd(v){return v==null?DASH:(v<0?String.fromCharCode(8722):"+")+"$"+Math.abs(v).toFixed(2);}
function pct(v){return v==null?DASH:(v<0?String.fromCharCode(8722):"+")+Math.abs(100*v).toFixed(1)+"%";}
function part(p,withFund){if(!p||!(p.positions||[]).length)return "";
return '<div class="q gap"><div style="display:flex;justify-content:space-between"><b style="color:var(--tx)">'+esc(p.name)+'</b><b style="color:var('+(p.gain<0?"--wn":"--ok")+')">'+usd(p.gain)+" ("+pct(p.gain_pct)+')</b></div>'+
(withFund&&p.fund_gain!=null?'<div class="src">The S&amp;P 500 fund with the same money on the same days: '+usd(p.fund_gain)+DOT+(p.vs_fund_usd>=0?"ahead by ":"behind by ")+"$"+Math.abs(p.vs_fund_usd).toFixed(2)+'</div>':"")+
(p.positions||[]).map(function(x){return '<div class="src" style="white-space:normal">'+esc(x.ticker)+DOT+usd(x.gain)+" ("+pct(x.gain_pct)+")"+(x.fund_pct!=null?DOT+"fund "+pct(x.fund_pct):"")+(x.closed?DOT+"closed "+esc(x.closed):(x.bought?DOT+"since "+esc(x.bought):""))+'</div>';}).join("")+'</div>';}
function block(withFact){var r=M.X.results;if(!r||!r.system)return "";var c=r.conviction||{},cp=(c.positions||[])[0]||{},fact="";
if(withFact){var snap=(M.S&&M.S.treasury)||{};var nav=Number(snap.nav||0),pos=(snap.positions||[]).filter(function(p){return p.ticker===cp.ticker;})[0];
if(nav&&pos)fact='<div class="src" style="white-space:normal">Fact: '+esc(cp.ticker)+" is "+Math.round(100*Number(pos.market_value||0)/nav)+"% of the portfolio. It is your conviction holding, kept by your choice (target $80.00, review 5 Oct 2027)."+'</div>';}
return M.blk("RESULTS IN PARTS",'<span class="stg '+(r.total<0?"stale":"live")+'">TOTAL '+usd(r.total)+'</span>',
'<div class="q" style="white-space:normal;font-weight:700;color:var(--tx)">'+esc(r.total_line)+'</div>'+part(r.system,true)+part(r.own,true)+
(cp.ticker?'<div class="q gap"><div style="display:flex;justify-content:space-between"><b style="color:var(--tx)">Conviction holding: '+esc(cp.ticker)+'</b><b style="color:var('+(cp.gain<0?"--wn":"--ok")+')">'+usd(cp.gain)+" ("+pct(cp.gain_pct)+')</b></div><div class="src">Kept by your choice. Not counted in the system\'s record.</div>'+fact+'</div>':""),
esc(r.method||""));}
var prevTd=M.slots["td-dec"];M.slots["td-dec"]=function(){var h=prevTd?prevTd():"";return h+block(false);};
function paintPortfolio(){var el=$("v-portfolio");if(!el)return;var h=block(true);if(!h)return;var box=$("p22-port");
if(!box){box=document.createElement("div");box.id="p22-port";el.insertBefore(box,el.firstChild);}if(box.__h!==h){box.innerHTML=h;box.__h=h;}}
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);paintPortfolio();};
MC.hooks.push(paintPortfolio);
M.reload();
})();
