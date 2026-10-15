/* Market Council add-on 12: ORDER PLANS (Portfolio > Plans). Every holding and idea with its label, its levels, the
   Forecaster's chances, the expected result after fees and the orders in Revolut's wording, from state/plans.json
   (ops/engine/plans.py), and the stop back-test from state/plans_backtest.json. Changing a label writes an answer
   file; "Set the take-profit alert" writes one inbox line. Nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.plans="state/plans.json";M.extra.plbt="state/plans_backtest.json";
var API="https://api.github.com/repos/benipkun/market-council-state",DOT=String.fromCharCode(183),DASH=String.fromCharCode(8212),NL=String.fromCharCode(10),note={};
var LAB={short:"SHORT-TERM",medium:"MEDIUM-TERM",long:"LONG-TERM"};
function usd(v){return v==null?DASH:(v<0?"-":"")+"$"+Math.abs(v).toFixed(2);}
function pct(v,d){return v==null?DASH:(100*v).toFixed(d==null?1:d)+"%";}
function src(t){return '<div class="src" style="white-space:normal">'+t+'</div>';}
function head(t){return '<div class="fl" style="margin-top:12px;font-weight:800;font-size:11px;letter-spacing:.06em">'+t+'</div>';}
function labels(p){if(p.kept)return src("Label: long-term, set by your decision to keep it.");
return '<div class="gap" style="display:flex;gap:6px;flex-wrap:wrap">'+["short","medium","long"].map(function(l){return '<button class="btn sm'+(p.label===l?" primary":"")+'" data-p12="label" data-id="'+esc(p.id)+'" data-l="'+l+'">'+LAB[l]+'</button>';}).join("")+'</div>'+(note[p.id]?src(esc(note[p.id])):"");}
function fc(p){var f=p.forecast;if(!f)return src(esc(p.forecast_note||"No forecast for these levels yet."));
return M.kv("Forecaster",pct(f.tp_first,0)+" take-profit first, "+pct(f.stop_first,0)+" stop first, by "+esc(f.due||DASH))+src(f.few?"Too few similar past cases to rely on.":"From "+(f.cases||0)+" similar past cases. An estimate, not a promise.");}
function steps(p){return (p.revolut||[]).length?head("IN REVOLUT")+p.revolut.map(function(s){return src(esc(s));}).join(""):"";}
function alertBtn(p){return p.take_profit?'<div class="gap"><button class="btn sm" data-p12="alert" data-t="'+esc(p.ticker)+'" data-p="'+p.take_profit+'">Set the take-profit alert at '+usd(p.take_profit)+'</button>'+(note["a:"+p.ticker]?src(esc(note["a:"+p.ticker])):"")+'</div>':"";}
function holding(p){var e=p.earnings;
var b=M.kv("Holding",(p.shares)+" shares at "+usd(p.price)+(p.average_cost?" (average cost "+usd(p.average_cost)+")":""))+
M.kv("Stop-loss",usd(p.stop))+src(esc(p.stop_why||""))+
(p.stop_should_be?'<div class="q" style="color:var(--wn)"><b>Move the stop up to '+usd(p.stop_should_be)+'</b>: it is up by its first risk (trailing rule).</div>':"")+
M.kv("Loss if the stop is hit",usd(p.loss_at_stop)+" ("+pct(p.loss_pct)+", "+pct(p.loss_share_of_portfolio)+" of the portfolio)")+
M.kv("Take-profit",usd(p.take_profit))+src(esc(p.take_profit_why||""))+M.kv("Gain at the take-profit, after fees",usd(p.gain_at_take_profit))+
M.kv("Reward to risk",p.reward_risk==null?DASH:p.reward_risk.toFixed(2))+M.kv("Time limit",esc(p.until||DASH))+src(esc(p.until_why||""))+
fc(p)+(p.expected_after_fees!=null?M.kv("Expected result after fees",(p.expected_after_fees<0?"-":"+")+usd(Math.abs(p.expected_after_fees))):"")+
(e?'<div class="q" style="color:var(--wn)"><b>Results on '+esc(e.date)+'</b>, inside this plan: '+esc(e.action)+'. A 10% gap at the open would cost about '+usd(e.gap_10pct)+' and can open past the stop.</div>':"")+
(p.fraction_note?src(esc(p.fraction_note)):"")+steps(p)+alertBtn(p)+labels(p);
return M.blk(esc(p.ticker)+" "+DOT+" ORDER PLAN",'<span class="stg '+(p.kept?"paper":"live")+'">'+(p.kept?"YOUR DECISION":LAB[p.label])+'</span>',b,"Worked out from your books and your own rules. You place every order yourself.");}
function idea(p){var v=p.verdict||{},ok=v.buy===true;
var b='<div style="font-weight:800;margin-bottom:4px">'+esc(p.title||p.ticker)+'</div>'+
(ok?'<div class="q"><span class="stg live">ACTION '+esc(String(v.n||""))+'</span> '+esc(v.line||"")+'</div>':'<div class="q"><b style="color:var(--tx)">Not a buy now:</b> '+esc(v.why||"held back on its card")+'</div>')+
M.kv("Limit entry",usd(p.limit)+", valid until "+esc(p.valid_until||DASH))+M.kv("Size your risk profile allows",usd(p.size_allowed)+(p.shares?" = "+p.shares+" share"+(p.shares===1?"":"s")+" ("+usd(p.cost)+")":""))+
(p.note?src(esc(p.note)):"")+M.kv("Stop-loss / take-profit",usd(p.stop)+" / "+usd(p.take_profit))+M.kv("Loss if the stop is hit",usd(p.loss_at_stop)+(p.loss_share_of_portfolio!=null?" ("+pct(p.loss_share_of_portfolio)+" of the portfolio)":""))+
M.kv("Reward to risk",p.reward_risk==null?DASH:p.reward_risk.toFixed(2))+M.kv("Fees in and out",usd(p.fees_in)+" + "+usd(p.fees_out))+fc(p)+
(p.expected_after_fees!=null?M.kv("Expected result after fees",usd(p.expected_after_fees)):"")+'<details class="p3d"><summary>Orders in Revolut and the label</summary>'+steps(p)+labels(p)+'</details>';
return '<div class="p3q">'+b+'</div>';}
function shortList(L){if(!(L||[]).length)return "";
return M.blk("SHORT-TERM LIST",'<span class="stg paper">'+L.length+' IDEAS</span>',L.map(function(p){return '<div class="kv"'+(p.pays?"":' style="opacity:.55"')+'><span><b>'+esc(p.ticker)+'</b> <span class="stg stale">UNPROVEN</span><br><span class="fl" style="font-size:11px">'+esc(p.title||"")+'</span></span><span class="r">fees '+usd(p.fees_in)+' in, '+usd(p.fees_out)+' out<br><span class="fl" style="font-size:11px">'+(p.pays?"pays from about "+usd(p.smallest_paying):"does not pay at the sizes tested")+'</span></span></div>';}).join(""),
"Days to about four weeks. Greyed when the fees take the gain at the sizes tested. Every short-term rule is unproven on your own record.");}
function backtest(b){if(!b||!(b.rules||[]).length)return M.blk("STOP AND TAKE-PROFIT BACK-TEST",'<span class="stg paper">NEXT NIGHT</span>','<div class="nbx">The back-test runs with the nightly back-checks; the first table appears after the next run.</div>',"");
return M.blk("STOP AND TAKE-PROFIT BACK-TEST",'<span class="stg paper">'+b.rules.reduce(function(s,r){return s+r.cases;},0)+' CASES</span>',b.rules.map(function(r){return '<div class="q"><b style="color:var(--tx)">'+esc(r.name)+'</b>'+
M.kv("Cases",String(r.cases))+M.kv("Take-profit first / stop first / time limit",pct(r.take_profit_first,0)+" / "+pct(r.stop_first,0)+" / "+pct(r.time_limit,0))+
M.kv("Average result with the plan / without",pct(r.with_plan,2)+" / "+pct(r.without_plan,2))+M.kv("Plan better in",pct(r.plan_better_share,0)+" of cases")+
M.kv("Stopped out, then back above the entry",pct(r.stopped_then_recovered,0))+M.kv("Gapped more than 2% past the stop",pct(r.gapped_past_stop,0)+" (average gap "+pct(r.average_gap,2)+")")+src(esc(r.verdict||""))+'</div>';}).join(""),
esc(b.method||"")+" "+esc(b.honesty||"")+" "+M.upd(b.as_of));}
function html(){var P=M.X.plans;if(!P)return "";
var ev=P.events||[];
var top=ev.length?M.blk("NEEDS YOU",'<span class="stg stale">'+ev.length+'</span>',ev.map(function(e){return '<div class="q">'+esc(e.text)+'</div>';}).join(""),"You get one phone message when something here is new. "+esc(P.push_note||"")):"";
var ideas=(P.ideas||[]).length?M.blk("IDEAS",'<span class="stg paper">'+P.ideas.length+'</span>',P.ideas.map(idea).join(""),"Every open idea card with its order plan. Only those today's action list buys show an action number."):"";
return top+(P.holdings||[]).map(holding).join("")+ideas+shortList(P.short_term)+backtest(M.X.plbt)+
M.blk("HOW REVOLUT TAKES THESE ORDERS",'',src(esc(P.revolut||"")),"From Revolut's help pages and trading terms, October 2026. Check the order screen in the app if anything differs.");}
function render(){var el=$("v-plans");if(!el)return;var h=html()||'<div class="msg">The order plans appear after the next engine run.</div>';if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
function put(path,msg,text){var tok=MC.store(MC.K.tok);if(!tok)return Promise.resolve("Add your token in the Log tab first.");
return fetch(API+"/contents/"+path,{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:msg,content:btoa(unescape(encodeURIComponent(text)))})})
.then(function(r){return r.ok?null:"Could not be sent ("+r.status+").";}).catch(function(){return "Could not be sent. Check your connection.";});}
function stamp(){return new Date().toISOString().replace(/[-:]/g,"").replace(/[.][0-9]+Z$/,"");}
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p12]"):null;if(!b)return;var k=b.getAttribute("data-p12");
if(k==="label"){var id=b.getAttribute("data-id"),l=b.getAttribute("data-l");note[id]="Sending"+String.fromCharCode(8230);render();
put("answers/"+stamp()+"-"+Math.random().toString(36).slice(2,7)+".json","Market Council answer: label "+id,JSON.stringify({kind:"label",id:id,label:l,at:new Date().toISOString().replace(/[.][0-9]+Z$/,"Z")}))
.then(function(err){note[id]=err||"Recorded as "+LAB[l].toLowerCase()+". The plan is worked out again within a few minutes.";render();if(!err)[90,180].forEach(function(s){setTimeout(M.reload,s*1000);});});}
if(k==="alert"){var t=b.getAttribute("data-t"),p=b.getAttribute("data-p");note["a:"+t]="Sending"+String.fromCharCode(8230);render();
put("inbox/queue/"+stamp()+"Z-alert.md","Market Council: price alert","alert "+t+" above "+p+NL).then(function(err){note["a:"+t]=err||"Alert sent to the inbox: you get a phone message when "+t+" reaches $"+p+".";render();});}});
MC.hooks.push(render);
M.reload();
})();
