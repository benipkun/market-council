/* Market Council add-on 24 (16 Nov 2026): QUANT LAB under RESEARCH, SYSTEM > SETTINGS, and four ways into the target split.
   QUANT LAB: every number tool, inputs at the top, a Run button, the result below. A run is saved as answers/qlab-*.json;
   the engine job on GitHub Actions runs ops/engine/qlab.py (plain code, no Claude credits) and saves state/qlab/runs/<id>.json,
   listed in state/qlab/index.json. A result can be sent to the decision engine as a note; it never places or changes an order.
   Target split: a button at the top of PORTFOLIO, a tap on the TODAY bar, SYSTEM > SETTINGS, and "change my split" in Ask the Council. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DOT=" "+String.fromCharCode(183)+" ",ARROW=String.fromCharCode(8594);
var API="https://api.github.com/repos/benipkun/market-council-state";
M.extra.qlab="state/qlab/index.json";
var HELD=function(){return (((M.S&&M.S.treasury)||{}).positions||[]).map(function(p){return p.ticker;}).filter(Boolean);};
var SER=["US 10-year yield","US 2-year yield","WTI oil","Brent oil","Gold","Copper","Natural gas","Wheat","US dollar index","VIX (expected S&P 500 volatility)","Euro in dollars","Bitcoin","Dollar in forint"];
var T=[
 {id:"backtest",n:"1",name:"Backtester",what:"A rule against the S&P 500 fund, after Revolut fees (0.25%, at least $1).",before:"Built before: six rules on every holding, nightly (QUANT > NIGHTLY). New: any ticker, rule, years and order size.",
  f:[["ticker","Ticker","SPY"],["rule","Rule","trend200",["hold","trend200","cross","mom","dip","stop"]],["years","Years","10"],["amount","Order size $","1000"]]},
 {id:"signals",n:"2",name:"Signals lab",what:"Does an outside data series lead a share by 1 to 4 weeks?",before:"Built before: 13 series against your shares, nightly. New: any pair on request.",
  f:[["ticker","Ticker","UBER"],["series","Outside series",SER[0],SER]]},
 {id:"history",n:"3",name:"History check",what:"Past periods that looked like today, and what happened next.",before:"Built before: pattern matches inside the nightly back-checks. New: any ticker, on request.",
  f:[["ticker","Ticker","SPY"],["matches","Matches","30"]]},
 {id:"montecarlo",n:"4",name:"Monte Carlo",what:"Outcome range for a position, or for the whole portfolio under any target split.",before:"Built before: nightly ranges for holdings and the target split preview. New: any position or split, on request.",
  f:[["what","For","position",["position","portfolio"]],["ticker","Ticker (position)","UBER"],["amount","Amount $","1000"],["years","Years","1"],["stocks","STOCKS % (portfolio)","40"],["bonds","BONDS %","10"],["etfs","ETFs %","50"]]},
 {id:"doomsday",n:"5",name:"Doomsday back-test",what:"The worst falls of the S&P 500 fund, with and without the protocol.",before:"Built before: nightly from 2000. New: choose the start year and the safe asset.",
  f:[["from_year","From year","2000"],["safe","Safe asset","SHY",["SHY","cash"]]]},
 {id:"options",n:"6",name:"Options calculator",what:"Price and Greeks. For learning only: your broker has no options.",before:"Built before: nightly on your holdings. New: any strike, days and volatility.",
  f:[["ticker","Ticker (or leave empty)","UBER"],["price","Share price $ (empty = last close)",""],["strike","Strike $ (empty = at the money)",""],["days","Days","30"],["vol","Volatility % (empty = last 12 months)",""],["type","Type","call",["call","put"]]]},
 {id:"pairs",n:"7",name:"Pairs finder and backtester",what:"Shares that move together; the pair rule tested on years the fit never saw.",before:"Built before: nightly within sectors. New: your own list (2 = one pair, more = finder).",
  f:[["tickers","Tickers (empty = your holdings)","KO PEP"]]},
 {id:"earnings",n:"8",name:"Earnings reaction",what:"The usual move after results, and how the crowd reacts to a beat or a miss.",before:"Built before: the EARNINGS screen for coming results. New: any ticker with a saved result history.",
  f:[["ticker","Ticker","UBER"]]},
 {id:"learned",n:"9",name:"Learned signal",what:"A model of next month's return, tested walk-forward. Stays on paper until it beats the simple rules out of sample.",before:"Built before: one pooled model, nightly. New: per ticker, against momentum and holding.",
  f:[["ticker","Ticker","SPY"],["amount","Order size $","1000"]]}];
var css=document.createElement("style");css.textContent=
".p24f{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}.p24f label{font-size:10.5px;color:var(--dim);display:flex;flex-direction:column;gap:3px;flex:1;min-width:96px}"+
".p24f input,.p24f select{background:var(--bg);border:1px solid var(--bd);color:var(--tx);border-radius:3px;padding:8px;font:inherit;font-size:13px;width:100%;box-sizing:border-box}"+
".p24t{width:100%;border-collapse:collapse;font-size:12px;margin:6px 0}.p24t td{padding:4px 4px;border-top:1px solid var(--bd);white-space:normal}.p24t tr:first-child td{color:var(--dim);font-size:10.5px}"+
".p24top{display:flex;justify-content:flex-end;margin:0 0 8px}";
document.head.appendChild(css);
var runs={},open={},note={};
function lab(l){return '<span class="stg '+(l==="LIVE"?"live":l==="SAMPLE"?"lvl":"paper")+'">'+esc(l||"PAPER")+'</span>';}
function table(t){return t&&t.length?'<table class="p24t">'+t.map(function(r){return "<tr>"+r.map(function(c){return "<td>"+esc(c==null?"":c)+"</td>";}).join("")+"</tr>";}).join("")+"</table>":"";}
function result(r){if(!r)return "";if(r.status!=="ok")return '<div class="msg warn">'+esc(r.headline||"Could not run.")+'</div>';
var age=r.data_age_days==null?"":DOT+"data "+(r.data_age_days<=1?"from the last close":r.data_age_days+" days old");
return '<div class="q gap" style="white-space:normal">'+lab(r.label)+' <b style="color:var(--tx)">'+esc(r.headline)+'</b></div>'+table(r.table)+
'<div class="src" style="white-space:normal">Rests on: '+esc(r.cases_note||"no counted cases (a formula)")+DOT+"data through "+esc(r.data_through||"-")+age+DOT+"ran "+esc(String(r.ran_at||"").slice(0,16).replace("T"," "))+" UTC on GitHub Actions"+'</div>'+
'<details class="src"><summary>Method</summary><div style="white-space:normal">'+esc(r.method||"")+'</div></details>'+
(r.ticker?'<button class="btn sm" data-p24s="'+esc(r.id)+'">Send to the decision engine</button> <span class="src">Shown as a note on the action list for '+esc(r.ticker)+'. It never places or changes an order.</span>':"");}
function loadRun(id){if(runs[id])return;runs[id]={loading:true};MC.get("state/qlab/runs/"+id+".json").then(function(r){runs[id]=r||{status:"failed",headline:"Not found."};paint();});}
function tool(t){var ix=(M.X.qlab||{}).runs||[],mine=ix.filter(function(r){return r.tool===t.id;}).reverse(),cur=open[t.id]||(mine[0]&&mine[0].id);
if(cur)loadRun(cur);var r=cur&&runs[cur];
return M.blk(t.n+". "+t.name.toUpperCase(),lab(t.id==="options"?"SAMPLE":(["history","montecarlo","earnings"].indexOf(t.id)>=0?"LIVE":"PAPER")),
'<div class="src" style="white-space:normal">'+esc(t.what)+'</div><div class="p24f">'+t.f.map(function(f){var v=f[2];
return '<label>'+esc(f[1])+(f[3]?'<select data-p24i="'+t.id+'.'+f[0]+'">'+f[3].map(function(o){return "<option"+(o===v?" selected":"")+">"+esc(o)+"</option>";}).join("")+"</select>":'<input data-p24i="'+t.id+'.'+f[0]+'" value="'+esc(v)+'">')+"</label>";}).join("")+'</div>'+
'<button class="btn" data-p24r="'+t.id+'">Run</button> <span class="src">'+esc(note[t.id]||"")+'</span>'+
(r&&!r.loading?'<div class="fl" style="margin-top:8px">RESULT</div>'+result(r):(cur?'<div class="src">Loading the result'+String.fromCharCode(8230)+'</div>':'<div class="src">No run yet.</div>'))+
(mine.length>1?'<details class="src"><summary>Past runs ('+mine.length+')</summary>'+mine.map(function(x){return '<div><a href="#qlab" data-p24o="'+t.id+"|"+esc(x.id)+'">'+esc(String(x.ran_at||"").slice(0,16).replace("T"," "))+"</a> "+esc(x.headline||"")+"</div>";}).join("")+"</details>":""),
esc(t.before));}
function paintLab(){var el=$("v-qlab");if(!el||el.hidden&&el.__h)return;var ix=M.X.qlab||{};
var h='<div class="hd"><h2>QUANT LAB</h2></div><div class="msg" style="white-space:normal">Every number tool in one place. Choose the inputs, press Run: the engine on GitHub Actions runs it as plain code (no AI, no credits) within a few minutes and saves it, so past runs open again below each tool. LIVE = an estimate on today\'s data; PAPER = a rule that has not earned real money; SAMPLE = for learning. Under 20 cases is "too few cases to rely on". Nothing here places an order: you place every order yourself.'+(ix.waiting?" "+ix.waiting+" run(s) waiting for the next pass.":"")+'</div>'+T.map(tool).join("");
if(el.__h!==h){var ae=document.activeElement,k=ae&&ae.getAttribute&&ae.getAttribute("data-p24i"),vals={};
[].forEach.call(el.querySelectorAll("[data-p24i]"),function(i){vals[i.getAttribute("data-p24i")]=i.value;});
el.innerHTML=h;el.__h=h;[].forEach.call(el.querySelectorAll("[data-p24i]"),function(i){var v=vals[i.getAttribute("data-p24i")];if(v!=null)i.value=v;});
if(k){var e=el.querySelector('[data-p24i="'+k+'"]');if(e)e.focus();}}}
function paintSettings(){var el=$("v-settings");if(!el)return;var a=M.X.alloc||{},t=a.target;
var h='<div class="hd"><h2>SETTINGS</h2></div>'+M.blk("TARGET SPLIT",'<span class="stg '+(t?"live":"paper")+'">'+(t?"SET "+t.stocks+"/"+t.bonds+"/"+t.etfs:"NOT SET")+'</span>',
'<div class="src" style="white-space:normal">Your target for STOCKS, BONDS and ETFs, the tolerance band and whether sales may be suggested.</div><button class="btn" data-p24="split">Open the target split '+ARROW+'</button>',"")+
M.blk("RISK PROFILE","",'<div class="src">Level, horizon, maximum loss, short selling.</div><button class="btn sm" data-tab="system">Open under SYSTEM > STATUS '+ARROW+'</button>',"");
if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
function topButtons(){["v-map","v-portfolio"].forEach(function(v){var el=$(v);if(!el||el.querySelector(".p24top"))return;var d=document.createElement("div");d.className="p24top";
d.innerHTML='<button class="btn sm" data-p24="split">Target split '+ARROW+'</button>';el.insertBefore(d,el.firstChild);});}
function openSplit(){MC.show("portfolio");var n=0;(function go(){var b=$("p23-port");if(b){b.scrollIntoView({block:"start"});return;}if(++n<30)setTimeout(go,100);})();}
M.openSplit=openSplit;
function token(){return MC.store(MC.K.tok);}
function put(id,obj,msg){return fetch(API+"/contents/answers/"+id+".json",{method:"PUT",headers:{"Authorization":"Bearer "+token(),"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:msg,content:btoa(unescape(encodeURIComponent(JSON.stringify(obj))))})});}
function stamp(){return new Date().toISOString().replace(/[-:]/g,"").slice(0,15)+"Z";}
function runTool(id){if(!token()){note[id]="Add your token in the Log tab first.";paint();return;}var t=T.filter(function(x){return x.id===id;})[0],inp={};
t.f.forEach(function(f){var e=document.querySelector('[data-p24i="'+id+"."+f[0]+'"]');var v=e?String(e.value).trim():"";if(v!=="")inp[f[0]]=v;});
var rid="qlab-"+stamp();note[id]="Sending"+String.fromCharCode(8230);paint();
put(rid,{kind:"qlab",id:rid,tool:id,inputs:inp,at:new Date().toISOString().slice(0,19)+"Z"},"Market Council: quant lab run "+id).then(function(r){
note[id]=r.ok?"Queued. The engine runs it within a few minutes; this page checks back.":"Could not be sent ("+r.status+").";if(r.ok){open[id]=rid;[60,120,200,320].forEach(function(s){setTimeout(function(){delete runs[rid];M.reload();},s*1000);});}paint();}).catch(function(){note[id]="Could not be sent. Check your connection.";paint();});}
function sendRun(id){if(!token()){MC.toast("Add your token in the Log tab first.",true);return;}var sid="qlab-send-"+stamp();
put(sid,{kind:"qlab_send",run:id,at:new Date().toISOString().slice(0,19)+"Z"},"Market Council: quant lab result to the engine").then(function(r){MC.toast(r.ok?"Sent. It appears as a note on the action list after the next engine pass; no order changes.":"Could not be sent ("+r.status+").",!r.ok);});}
document.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest("[data-p24],[data-p24r],[data-p24s],[data-p24o]");if(!b)return;
if(b.getAttribute("data-p24")==="split"){e.preventDefault();openSplit();return;}
var r=b.getAttribute("data-p24r");if(r){runTool(r);return;}var s=b.getAttribute("data-p24s");if(s){sendRun(s);return;}
var o=b.getAttribute("data-p24o");if(o){e.preventDefault();var p=o.split("|");open[p[0]]=p[1];paint();}});
/* "change my split" (or "target split", "set my split"...) in Ask the Council opens the setting instead of sending a question */
var SPLIT=/\b(change|set|edit|adjust|update|open|show)\b[^.?!]{0,20}\b(my\s+)?(target\s+)?(split|allocation|distribution)\b|^\s*target split\s*$/i;
function intercept(id){var i=$(id);if(!i||!SPLIT.test(i.value||""))return false;i.value="";openSplit();MC.toast("Here is your target split.");return true;}
document.addEventListener("keydown",function(e){if(e.key!=="Enter"||e.shiftKey)return;var id=e.target&&e.target.id;if((id==="cmd-in"||id==="chat-in")&&intercept(id)){e.preventDefault();e.stopImmediatePropagation();}},true);
document.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest('[data-mc="cmd-go"],#chat-send');if(!b)return;if(intercept(b.id==="chat-send"?"chat-in":"cmd-in")){e.preventDefault();e.stopImmediatePropagation();}},true);
function paint(){try{paintLab();}catch(x){}try{paintSettings();}catch(x){}topButtons();}
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);paint();};
var prevShow=MC.onShow;MC.onShow=function(t){if(prevShow)prevShow(t);paint();if(t==="qlab"||t==="settings")M.reload();};
MC.hooks.push(paint);
M.reload();
})();
