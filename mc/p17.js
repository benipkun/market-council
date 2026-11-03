/* Market Council add-on 17: BEHAVIOUR (Research > Behaviour). How the crowd may act around events: today's readings
   for each holding with their normal range and a plain sentence, the market mood, the tested behaviour patterns with
   their historical results and case counts (kept or dropped, and why), the walk-forward test of the forecasts with and
   without the behaviour adjustment, the live score, and the event cards (base, adjustment, final). Plain code
   (ops/engine/behaviour.py, state/behaviour.json); estimates, never promises. Nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.behav="state/behaviour.json";
var DASH=String.fromCharCode(8212),DOT=" "+String.fromCharCode(183)+" ",open={};
function pc(v,d){return v==null?DASH:(Math.round(1000*v)/10).toFixed(d==null?1:d)+"%";}
function sp(v){return v==null?DASH:(v>=0?"+":"")+(Math.round(1000*v)/10).toFixed(1)+"%";}
function val(x){var v=x.value;if(v==null)return DASH;if(typeof v==="number"&&Math.abs(v)<3&&/Run-up|Distance|change/.test(x.name))return sp(v);return esc(String(v));}
function p(t){return '<p style="font-size:13px;line-height:1.5;white-space:normal;margin:5px 0">'+t+'</p>';}
function small(t){return '<div style="font-size:12px;color:var(--dim);white-space:normal;margin:3px 0">'+t+'</div>';}
function tag(s){var k=/^kept/.test(s)?"live":"stale";return '<span class="stg '+k+'" style="font-size:10px">'+esc(String(s||"").toUpperCase())+'</span>';}
function mood(b){var m=b.mood||{};
  return M.blk("MARKET MOOD",'<span class="stg '+(m.stressed?"stale":"live")+'">'+(m.stressed?"STRESSED":"CALM")+'</span>',
    p("Volatility index (VIX) "+(m.vix!=null?m.vix.toFixed(1):DASH)+(m.vix_pct_1y!=null?", higher than on "+pc(m.vix_pct_1y,0)+" of the last year's days":"")+DOT+"Market Council stress level "+esc(m.stress_level||DASH)+DOT+"S&P 500 fund "+sp(m.spy_from_high)+" from its 12-month high.")+
    small("Fear/greed index: "+esc(m.fear_greed||DASH)),"Stressed means the VIX at 25 or more, or the S&P 500 fund 10% or more under its high.");}
function reads(b){var r=b.readings||{},ks=Object.keys(r).sort();if(!ks.length)return "";
  return M.blk("TODAY'S READINGS FOR YOUR SHARES","",ks.map(function(t){var o=open["r"+t];
    var rows=(r[t]||[]).filter(function(x){return o||x.available;}).map(function(x){return '<tr><td>'+esc(x.name)+'</td><td class="r mono">'+val(x)+'</td><td class="r mono">'+(x.normal?esc(String(x.normal[0]))+" to "+esc(String(x.normal[1])):DASH)+'</td></tr><tr><td colspan="3" style="color:var(--dim);font-size:12px;white-space:normal">'+esc(x.sentence)+'</td></tr>';}).join("");
    return '<div style="margin:8px 0"><b>'+esc(t)+'</b> <button class="btn sm" data-p17="r'+esc(t)+'">'+(o?"Hide what is missing":"Show what is missing too")+'</button><div class="tw"><table><thead><tr><th>Signal</th><th class="r">Today</th><th class="r">Normal</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>';}).join(""),
    "Normal range: the 10th to 90th percentile of this share's own history, where one exists.");}
function pats(b){var ps=b.patterns||[];
  return M.blk("THE BEHAVIOUR PATTERNS, TESTED","",ps.map(function(x){return '<div style="margin:8px 0">'+tag(x.status)+' <b>'+esc(x.name)+'</b>'+small(esc(x.rule))+
    (x.words?p(esc(x.words)+(x.cases!=null?" ("+x.cases+" cases)":"")+(x.few?' <span class="stg stale" style="font-size:10px">TOO FEW CASES</span>':"")):"")+(x.why?small("Why "+(/^kept/.test(x.status)?"kept":"dropped")+": "+esc(x.why)):"")+'</div>';}).join(""),
    "No pattern is assumed to work: each is kept only if it improved forecasts on data it was not fitted on.");}
function bt(b){var t=b.backtest||{},base=t.base||{},pcnd=t.per_condition||{};if(!t.events)return M.blk("DOES THE ADJUSTMENT HELP?","",p("Not enough past events yet."),"");
  var rows=Object.keys(pcnd).map(function(k){var x=pcnd[k];return '<tr><td>'+esc(k==="all"?"all conditions":k.replace("_"," "))+'</td><td class="r">'+x.fired_on+'</td><td class="r mono">'+(x.brier_change>0?"+":"")+x.brier_change+'</td><td class="r mono">'+sp(x.move_error_change)+'</td><td class="r">'+esc(x.years_better)+'</td><td>'+(k==="all"?"":(x.kept?"kept":"dropped"))+'</td></tr>';}).join("");
  return M.blk("DOES THE ADJUSTMENT HELP? (WALK-FORWARD)","",p("Past events tested: "+t.events+". Without the adjustment: direction score "+base.brier_up+" (a coin scores 0.25), size-of-move error "+pc(base.move_error,2)+". Kept: "+((t.kept||[]).length?esc(t.kept.join(", ")):"none")+".")+
    '<div class="tw"><table><thead><tr><th>Condition</th><th class="r">Fired</th><th class="r">Score change</th><th class="r">Move error</th><th class="r">Years better</th><th></th></tr></thead><tbody>'+rows+'</tbody></table></div>'+small(esc(t.method||"")),
    "Lower is better for both. A negative change means the adjustment helped.");}
function live(b){var l=b.live||{};return M.blk("LIVE: IS THE ADJUSTMENT HELPING?","",p(esc(l.verdict||"")),"Every adjusted forecast is logged before the event and scored after it.");}
function cards(b){var c=b.cards||{},ks=Object.keys(c);if(!ks.length)return "";
  return M.blk("EVENT CARDS","",ks.map(function(t){var x=c[t],n=x.final_next_day||{},ps=x.position;
    return '<div style="margin:8px 0"><b>'+esc(t)+'</b> '+esc((x.call||{}).date||"")+p(esc(x.line))+small("Range the next day after the adjustment: "+sp(n.p10)+" to "+sp(n.p90)+".")+
      (x.top_readings||[]).map(function(s){return small(DOT+esc(s));}).join("")+
      (ps?small("Holding through the call: middle "+(ps.hold.middle!=null?"$"+ps.hold.middle:DASH)+", worst 10% "+(ps.hold.worst_10!=null?"$"+ps.hold.worst_10:DASH)+", best 10% "+(ps.hold.best_10!=null?"$"+ps.hold.best_10:DASH)+". "+esc(ps.note||"")):"")+'</div>';}).join(""),
    "Estimates, never promises.");}
function html(){var b=M.X.behav;if(!b)return "";return cards(b)+mood(b)+reads(b)+pats(b)+bt(b)+live(b)+M.blk("","",small(esc(b.honesty||"")),"");}
function render(){var el=$("v-behaviour");if(!el)return;var h=html()||'<div class="msg">The behaviour readings appear after the next engine run.</div>';if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
document.addEventListener("click",function(ev){var b=ev.target.closest?ev.target.closest("[data-p17]"):null;if(!b)return;var k=b.getAttribute("data-p17");open[k]=!open[k];render();});
MC.hooks.push(render);
var prevRender=M.render;M.render=function(){var o=prevRender.apply(this,arguments);try{render();}catch(e){}return o;};
setTimeout(render,0);
M.reload();
})();
