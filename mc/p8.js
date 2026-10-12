/* Market Council add-on 8: the Forecaster. Reads state/forecasts.json (plain code: simulation, past base rates, option
   prices). Shows every probability the same way everywhere: a number, the same thing in words, and a bar with its range.
   Every figure is an estimate, not a promise. Places no orders. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.fc="state/forecasts.json";
var KN={up:"Higher than today",fall10:"A fall of more than 10% at some point",fall25:"A fall of more than 25% at some point",beat:"Beats the index fund",tp_first:"Target before stop",stop_first:"Stop before target",port_loss:"Worth less than today",port_max:"Down more than your maximum loss"};
var HO=["1m","3m","1y","by"];
function F(){return M.X.fc;}
function pc(p){return p==null?String.fromCharCode(8212):Math.round(100*p)+"%";}
function sg(p){return p==null?String.fromCharCode(8212):(p>0?"+":"")+Math.round(100*p)+"%";}
function bar(f){var lo=Math.round(100*f.lo),hi=Math.round(100*f.hi),p=Math.round(100*f.p);
return '<div style="position:relative;height:10px;background:rgba(128,128,128,.22);border-radius:5px;margin:5px 0 3px" role="img" aria-label="'+p+' percent, range '+lo+' to '+hi+'">'+
'<div style="position:absolute;left:'+lo+'%;width:'+Math.max(1,hi-lo)+'%;top:0;bottom:0;background:var(--ac);opacity:.3;border-radius:5px"></div>'+
'<div style="position:absolute;left:0;width:'+p+'%;top:3px;bottom:3px;background:var(--ac);border-radius:3px"></div></div>';}
function head(f){return '<b style="font-size:15px;color:var(--tx)">'+pc(f.p)+'</b> <span class="fl">'+esc(f.words||"")+' '+String.fromCharCode(183)+' range '+pc(f.lo)+' to '+pc(f.hi)+'</span>';}
function src(f){var a=["Simulation "+pc(f.sim)];
a.push("Similar past cases "+(f.base==null?"none":pc(f.base)+" ("+(f.cases||0)+" case"+(f.cases===1?"":"s")+(f.months?" in "+f.months+" different months":"")+(f.few?"; too few cases to rely on, not counted":"")+")"));
a.push("Option prices "+(f.opt==null?"no figure":pc(f.opt)));
if(f.own!=null)a.push("This share's own history "+pc(f.own)+" ("+(f.own_cases||0)+" periods, for comparison only)");
if(f.plain!=null)a.push("Any share, any setup "+pc(f.plain));return a;}
function one(k,f){var mv=(f.movers||[]).map(function(m){return '<div class="src">If '+esc(m["if"])+': '+pc(m.to)+' ('+sg(m.by)+').</div>';}).join("");
return '<details class="p3d"><summary>'+esc(KN[k]||k)+': '+pc(f.p)+' <span class="fl" style="font-weight:400">'+esc(f.words||"")+'</span></summary>'+
'<div class="q"><b style="color:var(--tx)">'+esc(f.q||"")+'</b></div><div>'+head(f)+'</div>'+bar(f)+
src(f).map(function(s){return '<div class="src">'+esc(s)+'.</div>';}).join("")+
(mv?'<div class="fl" style="margin-top:8px;font-size:11px;font-weight:800">WHAT WOULD MOVE IT MOST</div>'+mv:"")+
'<div class="src" style="margin-top:6px">'+esc(f.note||"An estimate, not a promise.")+'</div></details>';}
function horizon(h,H,money){if(!H)return "";var ks=Object.keys(H.f||{});
var rng=money?"Middle half of outcomes: $"+H.range50[0]+" to $"+H.range50[1]+". Nine in ten: $"+H.range90[0]+" to $"+H.range90[1]+".":
"Middle half of outcomes: "+sg(H.range50[0])+" to "+sg(H.range50[1])+". Nine in ten: "+sg(H.range90[0])+" to "+sg(H.range90[1])+".";
return '<div class="fl" style="margin-top:12px;font-weight:800;font-size:11px;letter-spacing:.06em">'+esc((H.label||h).toUpperCase())+' '+String.fromCharCode(183)+' CHECKED '+esc(H.due||"")+'</div>'+
'<div class="src">'+esc(rng)+' From the simulation.'+(H.implied_from?' Option figure from '+esc(H.implied_from)+'.':'')+'</div>'+ks.map(function(k){return one(k,H.f[k]);}).join("");}
function target(t,x){if(x.none)return M.blk(t,'<span class="stg stale">NO FORECAST</span>','<div class="nbx">'+esc(x.none)+'</div>',"");
var a=x.assume||{};
return M.blk(t+(x.name&&x.name!==t?" "+String.fromCharCode(183)+" "+x.name:""),x.held?'<span class="stg live">HELD</span>':'<span class="stg paper">IDEA</span>',
'<div class="q"><b style="color:var(--tx)">'+esc(x.line||"")+'</b></div>'+
'<div class="src">Price $'+x.price+' on '+esc(x.as_of||"")+'. Today&#39;s setup: '+esc(x.setup||"not known")+'. Assumed yearly return '+pc(a.mu)+', past volatility '+pc(a.vol)+', from '+a.years+' years of its own prices.'+
(x.plan?' Levels: '+esc(x.plan.kind||"")+' ($'+x.plan.target+(x.plan.stop?' and $'+x.plan.stop:'')+').':'')+'</div>'+
HO.map(function(h){return horizon(h,x.h&&x.h[h],true);}).join(""),x.check||"");}
function bands(rows){if(!rows||!rows.length)return "";
return '<table class="tb" style="width:100%;font-size:12px"><tr><th style="text-align:left">It said about</th><th>Times</th><th>It happened</th></tr>'+rows.map(function(b){
return '<tr'+(b.few?' style="opacity:.55"':'')+'><td>'+pc(b.band)+'</td><td style="text-align:center">'+b.n+'</td><td style="text-align:center">'+(b.n?pc(b.happened):String.fromCharCode(8212))+(b.few&&b.n?' <span class="fl" style="font-size:10px">too few</span>':'')+'</td></tr>';}).join("")+'</table>';}
function scoreBlock(s,title,tag,foot){if(!s)return "";
var riv=s.checked&&s.brier!=null?M.kv("Forecaster&#39;s error score (0 is perfect)",String(s.brier))+M.kv("Always saying 50%",String(s.brier_fifty))+M.kv("Plain base rate",String(s.brier_plain)):"";
var kinds=s.kinds?'<details class="p3d"><summary>By kind of question</summary><table class="tb" style="width:100%;font-size:12px"><tr><th style="text-align:left">Question</th><th>Times</th><th>Said</th><th>Happened</th><th>Error</th><th>Base-rate error</th></tr>'+
Object.keys(s.kinds).map(function(k){var r=s.kinds[k];return '<tr><td>'+esc(k)+'</td><td style="text-align:center">'+r.n+'</td><td style="text-align:center">'+pc(r.said)+'</td><td style="text-align:center">'+pc(r.happened)+'</td><td style="text-align:center">'+r.brier+'</td><td style="text-align:center">'+r.brier_plain+'</td></tr>';}).join("")+'</table></details>':"";
var ak=Object.keys(s.adjust||{}).filter(function(b){return Math.abs(s.adjust[b])>=0.02;});
var adj=ak.length?'<div class="src">Bias of two points or more: '+ak.map(function(b){return "when it says about "+pc(parseFloat(b))+", it happens "+sg(s.adjust[b])+" points "+(s.adjust[b]>0?"more":"less")+" often";}).join("; ")+'. Future forecasts are corrected only from the live record, once a band has 20 checked forecasts.</div>':"";
return M.blk(title,tag,'<div class="q"><b style="color:var(--tx)">'+esc(s.verdict||"")+'</b></div>'+M.kv("Forecasts checked",String(s.checked||0))+riv+bands(s.bands)+adj+kinds+
(s.method?'<div class="src" style="margin-top:6px">'+esc(s.method)+'</div>':"")+((s.limits||[]).map(function(l){return '<div class="src">'+esc(l)+'</div>';}).join("")),foot||"");}
function logBlock(L){if(!L)return "";var rows=(L.recent||[]).slice(-40).reverse().map(function(e){
return '<div class="src"><b style="color:var(--tx)">'+pc(e.p)+'</b> ('+pc(e.lo)+' to '+pc(e.hi)+') '+esc(e.q)+' <span class="fl">made '+esc(e.made)+(e.o==null?", open":(e.o?", HAPPENED":", DID NOT HAPPEN"))+'</span></div>';}).join("");
return M.blk("FORECAST LOG",L.intact?'<span class="stg live">UNEDITED</span>':'<span class="stg stale">CHECK FAILED</span>',
M.kv("Forecasts logged",String(L.count||0))+M.kv("Still open",String(L.open||0))+M.kv("First entry",esc(L.first||"none yet"))+
'<details class="p3d"><summary>The latest entries</summary>'+rows+'</details>',
"Each forecast is written once, on the day it is made, and never edited: every entry carries a fingerprint of the one before it, and the job refuses to add to a log whose fingerprints no longer match.");}
function html(){var f=F();if(!f)return '<div class="msg">The Forecaster has not reported yet. It runs after each US trading day.</div>';
var h=M.blk("THE FORECASTER",'<span class="stg live">A1 '+String.fromCharCode(183)+' PREDICTS ONLY</span>',
'<div style="font-size:12.5px;white-space:normal">'+esc((f.agent&&f.agent.job)||"")+' '+esc((f.agent&&f.agent.rule)||"")+'</div><div class="src" style="margin-top:6px">'+esc(f.method||"")+'</div><div class="src">'+esc(f.honesty||"")+'</div>',
"Forecasts as of "+esc(f.made||"")+", worked out "+M.upd(f.as_of)+". Plain code; the agent never invents a probability.");
h+=scoreBlock(f.score,"LIVE SCORE",(f.score&&f.score.enough)?'<span class="stg live">SCORED</span>':'<span class="stg paper">TOO EARLY TO JUDGE</span>',"Counts only forecasts whose date has arrived. The score is the average squared gap between the stated chance and what happened.");
h+=scoreBlock(f.backtest,"BACK-TEST OF THE METHOD",'<span class="stg paper">PAST DATES</span>',"A back-test is evidence about the method, not a record of real forecasts.");
var p=f.portfolio;
if(p)h+=p.none?M.blk("YOUR PORTFOLIO",'<span class="stg stale">NO FORECAST</span>','<div class="nbx">'+esc(p.none)+'</div>',""):
M.blk("YOUR PORTFOLIO",'<span class="stg live">'+pc(p.covers)+' COVERED</span>','<div class="src">'+esc(p.note||"")+' Assumed yearly return '+pc(p.assume.mu)+', past volatility '+pc(p.assume.vol)+'.</div>'+
["1m","3m","1y"].map(function(k){return horizon(k,p.h&&p.h[k],false);}).join(""),"Ranges are changes in value from today.");
var T=f.targets||{},ks=Object.keys(T).sort(function(a,b){return (T[b].held?1:0)-(T[a].held?1:0)||(a<b?-1:1);});
h+=ks.map(function(t){return target(t,T[t]);}).join("");
h+=logBlock(f.log);return h;}
function render(){var el=$("v-forecasts");if(!el)return;var h=html();if(el.__h!==h){var open={};Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){if(d.open)open[i]=1;});var had=el.__h!=null;el.innerHTML=h;el.__h=h;
if(had)Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){d.open=!!open[i];});}}
var prevCard=M.cardExtra;
M.cardExtra=function(c){var h=prevCard?prevCard(c):"";if(!c||c.kind==="test"||!c.ticker)return h;var f=F(),x=f&&f.targets&&f.targets[c.ticker];
if(!x||x.none)return h+(f?'<div class="src">Forecast: '+esc((x&&x.none)||"none yet; the Forecaster runs after each US trading day")+'.</div>':"");
var hk=(x.plan&&x.plan.horizon)||"3m",ff=x.h&&x.h[hk]&&x.h[hk].f,b=ff&&(ff.tp_first||ff.up);
return h+'<div class="q"><b style="color:var(--tx)">Forecast:</b> '+esc(x.line||"")+'</div>'+(b?bar(b):"")+'<div class="src">'+(b?esc(b.words)+". ":"")+'An estimate, not a promise. <button class="btn sm" data-tab="forecasts">Full forecast</button></div>';};
var prevCc=M.slots["cc-extra"];
M.slots["cc-extra"]=function(){setTimeout(render,0);var top=prevCc?prevCc():"",f=F(),s=f&&f.score;
return top+M.blk("FORECASTER",'<span class="stg live">A1 '+String.fromCharCode(183)+' PREDICTS ONLY</span>',
'<div style="font-size:12.5px;white-space:normal">Sits beside the analysts. Its only job is dated yes-or-no forecasts with a probability; it does not pick shares or argue for an idea, and the Councillor may not raise a card without a forecast from it. Not an AI: simulation, past base rates and option prices.</div>'+
(f?M.kv("Shares and ideas forecast",String(Object.keys(f.targets||{}).length))+M.kv("Forecasts logged",String((f.log&&f.log.count)||0))+M.kv("Score",esc((s&&s.verdict)||"none yet")):'<div class="nbx">No report yet.</div>')+
'<div class="gap"><button class="btn sm" data-tab="forecasts">Open the forecasts</button></div>',f?"Last run "+M.upd(f.as_of)+".":"");};
MC.hooks.push(render);
M.reload();
})();
