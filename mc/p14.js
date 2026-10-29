/* Market Council add-on 14: YOUR TRADES AND EXPOSURE. Every logged trade is read back against the books, the last
   price, the risk profile and its order plan, and its share is classified (ops/engine/tradecheck.py, state/exposure.json).
   This block shows the latest trades with their checks and the whole portfolio's exposure by sector, region, how jumpy
   the shares are and where the ideas came from. Nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.expo="state/exposure.json";
var DASH=String.fromCharCode(8212),open=false;
var TAG={ok:"live",warn:"lvl",fail:"stale"},WORD={ok:"CHECKED",warn:"CHECKED, NOTES",fail:"NEEDS A LOOK"};
function money(v){return v==null?DASH:"$"+Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});}
function pct(v){return v==null?DASH:(Math.round(1000*v)/10)+"%";}
function bars(title,rows){
  if(!rows||!rows.length)return "";
  var h='<div class="fl" style="margin-top:10px;font-weight:800;font-size:11px;letter-spacing:.06em">'+esc(title)+'</div>';
  rows.forEach(function(r){
    var w=Math.max(0,Math.min(100,Math.round(100*(r.pct||0))));
    h+='<div style="margin:4px 0"><div style="display:flex;justify-content:space-between;font-size:12px"><span>'+esc(r.name)+
       (r.tickers&&r.tickers.length?' <span style="color:var(--dim)">'+esc(r.tickers.join(", "))+'</span>':"")+'</span><span class="mono">'+pct(r.pct)+'</span></div>'+
       '<div style="height:6px;border-radius:3px;background:var(--bd);overflow:hidden"><div style="height:6px;width:'+w+'%;background:var(--ac)"></div></div></div>';
  });
  return h;
}
function trade(t){
  var cl=t.class||{},h='<div class="q" style="margin-top:8px"><span class="stg '+(TAG[t.status]||"paper")+'">'+(WORD[t.status]||"")+'</span> '+
    '<b>'+esc(String(t.action||"").toUpperCase())+' '+esc(t.ticker)+'</b> '+money(t.usd)+' <span style="color:var(--dim)">'+esc(String(t.at||"").slice(0,16).replace("T"," "))+'</span>';
  h+='<div style="font-size:12px;margin:3px 0">'+esc([cl.name,cl.type,cl.sector,cl.country].filter(Boolean).join(" "+String.fromCharCode(183)+" "))+
     (cl.risk?' '+String.fromCharCode(183)+' '+esc(cl.risk)+' ('+esc(cl.risk_why||"")+')':"")+'</div>';
  if(cl.note)h+='<div style="font-size:12px;color:var(--dim)">'+esc(cl.note)+'</div>';
  h+='<div style="font-size:12px;margin:3px 0">Idea from: '+esc(t.origin||DASH)+'</div>';
  (t.checks||[]).forEach(function(c){
    h+='<div style="font-size:12px;margin:2px 0"><span class="stg '+(TAG[c.status]||"paper")+'" style="font-size:10px">'+esc(String(c.status).toUpperCase())+'</span> '+esc(c.text)+'</div>';
  });
  return h+'</div>';
}
function html(){
  var o=M.X.expo;if(!o||!o.exposure)return "";
  var x=o.exposure,tr=o.trades||[],last=tr[0],body="";
  if(last)body+=trade(last);
  if(open)tr.slice(1).forEach(function(t){body+=trade(t);});
  if(tr.length>1)body+='<div class="gap"><button class="btn sm" data-p14="more">'+(open?"Show only the latest trade":"Show the last "+tr.length+" trades")+'</button></div>';
  body+=bars("BY SECTOR (OF YOUR WHOLE PORTFOLIO, CASH INCLUDED)",x.by_sector)+bars("BY REGION",x.by_region)+bars("HOW JUMPY",x.by_risk)+bars("WHERE THE IDEAS CAME FROM",x.by_origin);
  var lg=x.largest;
  body+='<div style="font-size:12px;margin-top:8px">Largest holding: '+(lg?esc(lg.ticker)+" "+pct(lg.pct):DASH)+'. Your three largest: '+pct(x.top3_pct)+' of the portfolio.'+
        (x.unknown&&x.unknown.length?' Not classified yet: '+esc(x.unknown.join(", "))+'.':"")+'</div>';
  var bad=tr.filter(function(t){return t.status==="fail";}).length;
  return M.blk("YOUR TRADES AND EXPOSURE",'<span class="stg '+(bad?"stale":"live")+'">'+(bad?bad+" NEED A LOOK":"BOOKS MATCH")+'</span>',body,
    "Checked "+M.upd(o.as_of)+" from the books of "+esc(String(o.books_as_of||"").slice(0,16))+". "+esc(o.method||""));
}
function paint(){var el=$("p14-host");if(el){var h=html();if(el.__h!==h){el.innerHTML=h;el.__h=h;}}}
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p14]"):null;if(!b)return;open=!open;paint();});
var prev=M.slots["td-dec"];
M.slots["td-dec"]=function(){setTimeout(paint,0);var h=prev?prev():"";return h+'<div id="p14-host"></div>';};
MC.hooks.push(paint);
M.reload();
})();
