/* Market Council add-on 11: WHAT TO DO NOW. The numbered action list (BUY, SELL, SWAP, HOLD) from state/actions.json,
   worked out by plain code (ops/engine/actions.py) from the cards, the Forecaster, the order plans, the cash, the fees
   and your standing decisions; plus the two questions "What should I do with [amount] now?" and "Should I sell
   [ticker]?". A sell question about a holding and this month's money are answered at once from the file; any other
   amount goes to the inbox as a question, and the same code answers it within a few minutes. Nothing here places an
   order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.acts="state/actions.json";M.extra.amsg="state/messages.json";
var API="https://api.github.com/repos/benipkun/market-council-state",DOT=String.fromCharCode(183),DASH=String.fromCharCode(8212),NL=String.fromCharCode(10);
var view=null,note="",asked=null;
function money(v){return v==null?DASH:"$"+Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});}
function pct(v){return v==null?DASH:Math.round(100*v)+"%";}
var TAG={BUY:"live",SELL:"stale",SWAP:"lvl",HOLD:"paper"};
function line(a){var s=[],f=a.forecast||{},p=a.portfolio||{},e=a.evidence||{};
if(f.tp_first!=null)s.push("Forecaster: "+pct(f.tp_first)+" take-profit first, "+pct(f.stop_first)+" stop first by "+esc(f.due||DASH)+(f.beat_index!=null?", "+pct(f.beat_index)+" to beat the index fund over "+esc(f.beat_over||""):""));
if(a.expected_usd!=null)s.push("Expected after fees <b style=\"color:var(--tx)\">"+(a.expected_usd<0?"-":"+")+money(Math.abs(a.expected_usd))+"</b>"+(a.index_usd!=null?" "+DOT+" same money in the index fund "+(a.index_usd<0?"-":"+")+money(Math.abs(a.index_usd)):"")+(a.if_take_profit!=null?" "+DOT+" at take-profit "+money(a.if_take_profit)+" "+DOT+" at stop "+money(a.if_stop):" "+esc(a.expected_note||"")));
if(a.type==="SWAP"&&a.why_better)s.push("Why "+esc((a.buy||{}).ticker)+" over "+esc((a.sell||{}).ticker)+": "+esc(a.why_better));
var pp=[];if(p.largest)pp.push("largest holding after: "+esc(p.largest.t)+" "+pct(p.largest.share));if(p.bad_year!=null&&p.bad_year_now!=null)pp.push("bad year "+(100*p.bad_year).toFixed(1)+"% (now "+(100*(p.bad_year_now||0)).toFixed(1)+"%)");
if(p.share!=null&&p.cap!=null)pp.push(pct(p.share)+" of the portfolio against your "+pct(p.cap)+" limit");if(p.bad_year_at_cap!=null)pp.push("bad year "+(100*p.bad_year).toFixed(1)+"% as held, "+(100*p.bad_year_at_cap).toFixed(1)+"% at the limit");
if(p.bad_year_if_sold!=null)pp.push("bad year if sold "+(100*p.bad_year_if_sold).toFixed(1)+"%");if(pp.length&&!a.decision)s.push("Portfolio: "+pp.join(" "+DOT+" "));
if(e.text)s.push("Evidence: "+esc(e.text));
(a.disagree||[]).forEach(function(d){s.push('<span style="color:var(--wn)">The parts disagree: '+esc(d)+'</span>');});
if(a.effect)s.push(esc(a.effect));(a.closest||[]).forEach(function(c){s.push("Closest idea: "+esc(c));});if(a.valid_until)s.push("Card valid until "+esc(a.valid_until)+". "+esc(a.exit_rule||""));
var flags=(a.flags||[]).map(function(x){return '<span class="stg '+(x==="unproven"?"stale":"paper")+'" style="margin-left:6px">'+esc(x.toUpperCase())+'</span>';}).join("");
return '<div class="q" style="margin-top:8px"><span class="stg '+(TAG[a.type]||"paper")+'">'+(a.n||"")+". "+a.type+'</span>'+flags+'<div style="font-size:13px;color:var(--tx);font-weight:700;margin:4px 0;white-space:normal">'+esc(a.line||"")+'</div>'+
s.map(function(x){return '<div class="src" style="white-space:normal">'+x+'</div>';}).join("")+'</div>';}
function list(acts){return (acts||[]).map(line).join("");}
function reply(){if(!asked)return "";var L=((M.X.amsg||{}).messages||[]),q=null,r=null;
L.forEach(function(m){if(m.from==="ben"&&m.text===asked.text&&m.at>=asked.at)q=m;});if(q)L.forEach(function(m){if(m.reply_to===q.id)r=m;});
if(!r)return '<div class="src gap">Asked '+esc(asked.text)+'. The answer appears here in a few minutes.</div>';
return '<div class="q gap"><b style="color:var(--tx)">'+esc(asked.text)+'</b>'+String(r.text||"").split(NL).map(function(x){return '<div class="src" style="white-space:normal">'+esc(x)+'</div>';}).join("")+'</div>';}
function box(a){var held=Object.keys(a.sell_answers||{}).sort(),inp=a.inputs||{};
return '<div class="gap" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"><span style="font-size:12.5px">What should I do with</span>'+
'<input id="p11-amt" type="text" inputmode="decimal" placeholder="amount" style="width:110px;min-height:40px"> <select id="p11-cur" style="min-height:40px"><option>HUF</option><option>USD</option></select>'+
'<button class="btn sm" data-p11="amt">now?</button></div>'+
'<div class="gap" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"><span style="font-size:12.5px">Should I sell</span><select id="p11-t" style="min-height:40px">'+held.map(function(t){return "<option>"+esc(t)+"</option>";}).join("")+'</select>'+
'<button class="btn sm" data-p11="sell">?</button>'+(inp.monthly_huf?'<button class="btn sm" data-p11="month">This month\'s '+Number(inp.monthly_huf).toLocaleString("en-US")+' HUF</button>':"")+'</div>'+
(note?'<div class="src">'+esc(note)+'</div>':"");}
function html(){var a=M.X.acts;if(!a||!a.actions)return "";
var top=a.actions[0]||{},v=view,cnt=a.actions.filter(function(x){return !x.decision;}).length;
var body=v?'<div class="fl" style="margin-top:10px;font-weight:800;font-size:11px;letter-spacing:.06em">'+esc(v.head)+'</div>'+list(v.acts)+'<div class="gap"><button class="btn sm" data-p11="back">Back to today\'s list</button></div>':list(a.actions);
return M.blk("WHAT TO DO NOW",'<span class="stg '+(top.type==="HOLD"&&!top.ticker?"paper":"live")+'">'+cnt+' ACTION'+(cnt===1?"":"S")+'</span>'+((a.stale||[]).length?'<span class="stg stale" style="margin-left:6px">STALE DATA</span>':""),
body+box(a)+reply(),
"Worked out "+M.upd(a.as_of)+" from the books of "+esc(String(a.books_as_of||"").slice(0,16))+". "+esc(a.foot||""));}
function paint(){var el=$("p11-host");if(el){var h=html();if(el.__h!==h){var v=($("p11-amt")||{}).value;el.innerHTML=h;el.__h=h;if(v&&$("p11-amt"))$("p11-amt").value=v;}}}
function send(text){var tok=MC.store(MC.K.tok);if(!tok){note="Add your token in the Log tab first.";paint();return;}
var ts=new Date().toISOString().replace(/[-:]/g,"").slice(0,15)+"Z";asked={text:text,at:new Date().toISOString().slice(0,19)};note="Sending"+String.fromCharCode(8230);paint();
fetch(API+"/contents/inbox/queue/"+ts+"-ask.md",{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:"Market Council: question",content:btoa("ask: "+text+NL)})})
.then(function(r){note=r.ok?"Sent. Your own system's code works out the answer; it appears below in a few minutes.":"Could not be sent ("+r.status+").";paint();if(r.ok)[60,120,180,300].forEach(function(s){setTimeout(M.reload,s*1000);});})
.catch(function(){note="Could not be sent. Check your connection.";paint();});}
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p11]"):null;if(!b)return;var a=M.X.acts||{},k=b.getAttribute("data-p11");note="";
if(k==="back"){view=null;asked=null;}
else if(k==="sell"){var t=($("p11-t")||{}).value;view={head:"Should I sell "+t+"?",acts:(a.sell_answers||{})[t]||[]};}
else if(k==="month"){view={head:"What to do with this month's "+Number((a.inputs||{}).monthly_huf).toLocaleString("en-US")+" HUF",acts:a.monthly_answer||[]};}
else if(k==="amt"){var raw=String(($("p11-amt")||{}).value||"").replace(/\s/g,""),cur=($("p11-cur")||{}).value||"HUF";
raw=/^\d{1,3}([.,]\d{3})+$/.test(raw)?raw.replace(/[.,]/g,""):raw.replace(",",".");var v=parseFloat(raw);
if(!(v>0)){note="Type an amount first.";}else{view=null;send("What should I do with "+(cur==="USD"?"$"+v:v+" HUF")+" now?");return;}}
paint();});
/* a card the action list buys shows its action line on top, so the card and the list say the same thing */
var prevTop=M.cardTop;
M.cardTop=function(c){var h=prevTop?prevTop(c):"",v=c&&c.verdict;if(v&&v.buy)h='<div class="q"><span class="stg live">ACTION '+esc(String(v.n||""))+' IN TODAY\'S LIST</span> '+esc(v.line||"")+'</div>'+h;return h;};
var prev=M.slots["td-dec"];
M.slots["td-dec"]=function(){setTimeout(paint,0);var h=prev?prev():"";return '<div id="p11-host"></div>'+h;};
MC.hooks.push(paint);
M.reload();
})();
