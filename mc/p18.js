/* Market Council add-on 18: YOUR BOOKS AGAINST YOUR BROKER (on TODAY). Shows when the prices were last refreshed
   (one source for every holding: Cboe's delayed quotes, every half hour while the US market is open), a button to
   refresh them now, and "Match my broker": the books' share counts, average prices and cash, prefilled, which you
   can correct by hand or by pasting your broker's positions, then send with one tap. The Trade Inbox applies each
   change as a correction ("set" and "cash" commands), never as a buy, sell or deposit. Nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.snapb="treasury/snapshot.json";
var API="https://api.github.com/repos/benipkun/market-council-state",DASH=String.fromCharCode(8212),NL=String.fromCharCode(10);
var openForm=false,note="",draft=null;
function put(path,msg,text){var tok=MC.store(MC.K.tok);if(!tok)return Promise.resolve("Add your token in the Log tab first.");
return fetch(API+"/contents/"+path,{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:msg,content:btoa(unescape(encodeURIComponent(text)))})})
.then(function(r){return r.ok?null:"Could not be sent ("+r.status+").";}).catch(function(){return "Could not be sent. Check your connection.";});}
function stamp(){return new Date().toISOString().replace(/[-:]/g,"").replace(/[.][0-9]+Z$/,"Z");}
function n(s){s=String(s==null?"":s).replace(/\s/g,"").replace(/[^0-9.,-]/g,"");if(s.indexOf(",")>=0&&s.indexOf(".")>=0)s=s.replace(/\./g,"").replace(",",".");else s=s.replace(",",".");var v=parseFloat(s);return isNaN(v)?null:v;}
function fmt(v,d){return v==null?"":String(Math.round(v*Math.pow(10,d))/Math.pow(10,d));}
function books(){var s=M.X.snapb||{};return {cash:Number(s.cash||0),rows:(s.positions||[]).map(function(p){var q=Number(p.qty||0);return {t:p.ticker,q:q,avg:q?Number(p.cost_basis||0)/q:0,px:Number(p.last_price||0),at:p.price_as_of,src:p.price_source};})};}
function start(){var b=books();draft={cash:fmt(b.cash,2),rows:b.rows.map(function(r){return {t:r.t,q:fmt(r.q,8),avg:fmt(r.avg,2)};})};}
function parsePaste(txt){
  // "9,27660496 UBER 75,66 USD" style rows and "Egyenleg ... 245,64 USD" / "Cash ... 245.64" for cash
  var found=0,re=/([0-9][0-9.,]*)\s+([A-Z]{1,5})\s+([0-9][0-9.,]*)\s*USD/g,m;
  while((m=re.exec(txt))){var t=m[2],q=n(m[1]),a=n(m[3]);if(q==null||a==null)continue;found++;
    var row=draft.rows.filter(function(r){return r.t===t;})[0];if(row){row.q=String(q);row.avg=String(a);}else draft.rows.push({t:t,q:String(q),avg:String(a),isNew:true});}
  var c=/(Egyenleg[^0-9]*|Cash[^0-9]*|Balance[^0-9]*)([0-9][0-9.,]*)\s*USD/i.exec(txt);if(c){draft.cash=String(n(c[2]));found++;}
  return found;}
function changes(){var b=books(),out=[];
  draft.rows.forEach(function(r){var o=b.rows.filter(function(x){return x.t===r.t;})[0],q=n(r.q),a=n(r.avg);if(q==null||a==null)return;
    if(!o||Math.abs(o.q-q)>1e-6||Math.abs(o.avg-a)>0.005)out.push({line:"set "+r.t+" "+q+" @ "+a,what:r.t+": "+(o?fmt(o.q,8)+" @ "+fmt(o.avg,2)+" to ":"new, ")+q+" @ "+a});});
  var c=n(draft.cash);if(c!=null&&Math.abs(c-b.cash)>0.005)out.push({line:"cash "+c+" usd",what:"cash: "+fmt(b.cash,2)+" to "+c});
  return out;}
function html(){var s=M.X.snapb;if(!s)return "";var b=books();
  var last=b.rows.map(function(r){return r.at;}).filter(Boolean).sort().pop();
  var old=b.rows.filter(function(r){return r.at&&last&&String(r.at).slice(0,13)!==String(last).slice(0,13);}).map(function(r){return r.t;});
  var h='<div style="font-size:12px;margin:4px 0">Prices as of '+esc(String(last||DASH).slice(0,16).replace("T"," "))+' UTC'+(old.length?' <span style="color:var(--wn)">(older for '+esc(old.join(", "))+')</span>':"")+
    '. One source for every holding: Cboe delayed quotes, about 15 minutes behind, refreshed every half hour while the US market is open.</div>'+
    '<div class="gap"><button class="btn sm" data-p18="prices">Refresh prices now</button> <button class="btn sm" data-p18="form">'+(openForm?"Close":"Match my broker")+'</button></div>';
  if(openForm){if(!draft)start();
    h+='<div style="font-size:12px;margin:6px 0">Paste your broker\'s positions here (optional), or correct the numbers below by hand:</div>'+
      '<textarea id="p18-paste" rows="3" style="width:100%;font-size:12px" placeholder="Paste the positions table from Revolut"></textarea>'+
      '<div class="gap"><button class="btn sm" data-p18="read">Read the pasted text</button></div>'+
      '<div class="tw"><table><thead><tr><th>Share</th><th class="r">Shares</th><th class="r">Average price $</th></tr></thead><tbody>'+
      draft.rows.map(function(r,i){return '<tr><td><b>'+esc(r.t)+'</b>'+(r.isNew?' <span class="stg lvl" style="font-size:10px">NEW</span>':"")+'</td><td class="r"><input data-p18q="'+i+'" value="'+esc(r.q)+'" style="width:110px;text-align:right"></td><td class="r"><input data-p18a="'+i+'" value="'+esc(r.avg)+'" style="width:80px;text-align:right"></td></tr>';}).join("")+
      '<tr><td><b>Cash</b></td><td class="r" colspan="2"><input data-p18c="1" value="'+esc(draft.cash)+'" style="width:110px;text-align:right"> $</td></tr></tbody></table></div>';
    var ch=changes();
    h+=(ch.length?'<div style="font-size:12px;margin:6px 0">Will change: '+esc(ch.map(function(c){return c.what;}).join("; "))+'</div>':'<div style="font-size:12px;margin:6px 0">The books already match these numbers.</div>')+
      '<div class="gap"><button class="btn sm" data-p18="send"'+(ch.length?"":" disabled")+'>Update my books to these numbers</button></div>';}
  if(note)h+='<div style="font-size:12px;color:var(--dim);margin:4px 0">'+esc(note)+'</div>';
  return M.blk("YOUR BOOKS AGAINST YOUR BROKER","",h,"A correction changes share counts, average prices or cash only; it is never recorded as a buy, sell or deposit.");}
function paint(){var el=$("p18-host");if(el){var h=html();if(el.__h!==h){el.innerHTML=h;el.__h=h;}}}
document.addEventListener("input",function(e){var t=e.target;if(!draft||!t.getAttribute)return;var i=t.getAttribute("data-p18q"),j=t.getAttribute("data-p18a");
  if(i!=null)draft.rows[+i].q=t.value;else if(j!=null)draft.rows[+j].avg=t.value;else if(t.getAttribute("data-p18c"))draft.cash=t.value;else return;
  var el=$("p18-host");if(el){var keep=t.getAttribute("data-p18q")!=null?"[data-p18q='"+i+"']":t.getAttribute("data-p18a")!=null?"[data-p18a='"+j+"']":"[data-p18c='1']";el.__h=null;paint();var f=el.querySelector(keep);if(f){f.focus();try{f.setSelectionRange(f.value.length,f.value.length);}catch(x){}}}});
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p18]"):null;if(!b)return;var k=b.getAttribute("data-p18");
  if(k==="form"){openForm=!openForm;if(openForm)start();note="";paint();return;}
  if(k==="read"){var txt=($("p18-paste")||{}).value||"";var f=parsePaste(txt);note=f?"Read "+f+" figures from the pasted text. Check them, then tap Update.":"No positions found in the pasted text.";paint();return;}
  if(k==="prices"){note="Sending"+String.fromCharCode(8230);paint();put("requests/prices-"+stamp()+".json","Market Council: refresh prices",JSON.stringify({at:new Date().toISOString()})+NL)
    .then(function(err){note=err||"Asked for fresh prices: they arrive within a few minutes.";paint();if(!err)[90,180,300].forEach(function(s){setTimeout(M.reload,s*1000);});});return;}
  if(k==="send"){var ch=changes();if(!ch.length)return;note="Sending"+String.fromCharCode(8230);paint();var i=0,errs=[];
    (function next(){if(i>=ch.length){note=errs.length?errs[0]:"Sent "+ch.length+" correction"+(ch.length===1?"":"s")+". The Trade Inbox applies them within a few minutes.";openForm=!!errs.length;draft=null;paint();if(!errs.length)[120,240].forEach(function(s){setTimeout(M.reload,s*1000);});return;}
      var c=ch[i++];put("inbox/queue/"+stamp()+"-"+i+"-set.md","Market Council: "+c.line,c.line+NL+"why: matched to my broker"+NL).then(function(err){if(err)errs.push(err);next();});})();}});
var prev=M.slots["td-dec"];
M.slots["td-dec"]=function(){setTimeout(paint,0);var h=prev?prev():"";return h+'<div id="p18-host"></div>';};
MC.hooks.push(paint);
var prevRender=M.render;M.render=function(){var o=prevRender.apply(this,arguments);try{paint();}catch(e){}return o;};
M.reload();
})();
