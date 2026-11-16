/* Market Council add-on 23 (16 Nov 2026): the target split between STOCKS, BONDS and ETFs. On PORTFOLIO: three sliders
   that always add up to 100% (moving one adjusts the unlocked others), presets, the tolerance band, whether sales may be
   suggested, the actual split next to the target in % and money, and BEFORE saving the outcome range, bad year and
   profile check of the new split against the current one (the same lognormal formula as ops/engine/allocation.py, from
   its part assumptions). Saving writes answers/alloc-*.json; the engine logs every change with its date and plans toward
   it. On TODAY: a bar of target against actual. UBER is never sold to reach the target (standing decision). */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DASH=String.fromCharCode(8212),DOT=" "+String.fromCharCode(183)+" ";
M.extra.alloc="state/allocation.json";
var API="https://api.github.com/repos/benipkun/market-council-state",P=["stocks","bonds","etfs"],NAME={stocks:"STOCKS",bonds:"BONDS",etfs:"ETFs"};
var draft=null,lock={},note="",band=null,sales=null,confirmBreak=false;
function pct(v){return v==null?DASH:(v<0?String.fromCharCode(8722):"+")+Math.abs(100*v).toFixed(1)+"%";}
function erf(x){var t=1/(1+0.3275911*Math.abs(x)),y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return x>=0?y:-y;}
function preview(s,A,maxLoss){var w=P.map(function(k){return s[k]/100;}),mu=0,v=0,i,j;for(i=0;i<3;i++){mu+=w[i]*A.mu[P[i]];for(j=0;j<3;j++)v+=w[i]*w[j]*A.cov[i][j];}
var sd=Math.sqrt(Math.max(v,1e-12));function out(T){var m=(mu-v/2)*T,s2=sd*Math.sqrt(T);function q(z){return Math.exp(m+z*s2)-1;}return {typical:q(0),bad:q(-1.2816),good:q(1.2816),loss:0.5*(1+erf((-m/s2)/Math.SQRT2))};}
var bad=Math.exp(mu-v/2-1.6449*sd)-1;return {y1:out(1),y5:out(5),bad_year:bad,breaks:bad<-maxLoss/100};}
function cur(a){var x={};P.forEach(function(k){x[k]=a.actual.pct[k];});return x;}
function tgt(a){if(draft)return draft;var t=a.target;if(t)return {stocks:t.stocks,bonds:t.bonds,etfs:t.etfs};return cur(a);}
function setPart(k,val){var s=tgt(M.X.alloc),others=P.filter(function(o){return o!==k&&!lock[o];});val=Math.max(0,Math.min(100,Math.round(val)));
var fixed=P.filter(function(o){return o!==k&&lock[o];}).reduce(function(t,o){return t+s[o];},0);val=Math.min(val,100-fixed);
var rest=100-fixed-val,sumO=others.reduce(function(t,o){return t+s[o];},0),n={};n[k]=val;P.forEach(function(o){if(lock[o]&&o!==k)n[o]=s[o];});
if(!others.length){n[k]=100-fixed;}else{var acc=0;others.forEach(function(o,i){var v=i===others.length-1?rest-acc:Math.round(sumO?rest*s[o]/sumO:rest/others.length);n[o]=v;acc+=v;});}
draft=n;paint();}
function row(lbl,a,b){return '<tr><td>'+lbl+'</td><td>'+a+'</td><td>'+b+'</td></tr>';}
function compare(a,s){var A=a.assumptions;if(!A)return '<div class="src">The outcome comparison appears once the engine has three years of prices for each part.</div>';
var c=preview(cur(a),A,a.max_loss),n=preview(s,A,a.max_loss);
return '<table class="tb" style="font-size:12px;margin-top:6px"><tr><th></th><th>CURRENT</th><th>NEW SPLIT</th></tr>'+
row("1 year, typical",pct(c.y1.typical),pct(n.y1.typical))+row("1 year, bad (1 in 10)",pct(c.y1.bad),pct(n.y1.bad))+row("1 year, good (1 in 10)",pct(c.y1.good),pct(n.y1.good))+row("Chance of a loss, 1 year",Math.round(100*c.y1.loss)+"%",Math.round(100*n.y1.loss)+"%")+
row("5 years, typical",pct(c.y5.typical),pct(n.y5.typical))+row("5 years, bad (1 in 10)",pct(c.y5.bad),pct(n.y5.bad))+row("5 years, good (1 in 10)",pct(c.y5.good),pct(n.y5.good))+row("Chance of a loss, 5 years",Math.round(100*c.y5.loss)+"%",Math.round(100*n.y5.loss)+"%")+
row("Bad year (1 in 20)",pct(c.bad_year),pct(n.bad_year))+row("Your maximum loss",pct(-a.max_loss/100),pct(-a.max_loss/100))+'</table>'+
(n.breaks?'<div class="q gap" style="color:var(--wn);white-space:normal">This split breaks your risk profile: its bad year ('+pct(n.bad_year)+') is worse than your maximum loss ('+a.max_loss+'%). <button class="btn sm" data-p23="anyway">Save it anyway</button> <a class="btn sm" href="#system">Adjust the profile</a></div>':"")+
'<div class="src" style="white-space:normal">Estimate. '+esc(A.method||"")+'</div>';}
function moves(a,s){var tot=a.actual.invested+a.actual.cash,h="";P.forEach(function(k){var g=s[k]/100*tot-a.actual.usd[k];h+='<div class="src">'+NAME[k]+": "+(g>=0?"add about $"+g.toFixed(0):"about $"+(-g).toFixed(0)+" above target")+'</div>';});
return h+'<div class="src" style="white-space:normal">New money goes first to the part furthest below target. Sales are suggested only if you allow them below; UBER is never sold or trimmed to reach the target. The exact orders, fees and tax estimate appear as action cards after saving.</div>';}
function control(){var a=M.X.alloc;if(!a||!a.actual)return "";var s=tgt(a),t=a.target,ac=a.actual,tot=ac.invested;band=band==null?((t&&t.band)||5):band;sales=sales==null?!!(t&&t.allow_sales):sales;
var bars=P.map(function(k){return '<div class="q" style="margin-top:6px"><div style="display:flex;justify-content:space-between;align-items:center"><b style="color:var(--tx)">'+NAME[k]+'</b><span><input type="number" min="0" max="100" value="'+s[k]+'" data-p23n="'+k+'" style="width:64px"> % <label class="src"><input type="checkbox" data-p23l="'+k+'"'+(lock[k]?" checked":"")+'> lock</label></span></div>'+
'<input type="range" min="0" max="100" value="'+s[k]+'" data-p23r="'+k+'" style="width:100%">'+
'<div class="src">Actual '+ac.pct[k].toFixed(0)+'% ($'+ac.usd[k].toFixed(0)+')'+DOT+'target '+s[k]+'% ($'+(s[k]/100*tot).toFixed(0)+')</div><div class="src" style="opacity:.75;white-space:normal">'+esc(a.definitions[k])+'</div></div>';}).join("");
var pre=(a.presets||[]).map(function(p){return '<button class="btn sm" data-p23p="'+p.stocks+'|'+p.bonds+'|'+p.etfs+'">'+esc(p.name)+" "+p.stocks+"/"+p.bonds+"/"+p.etfs+'</button>';}).join(" ");
var changed=!t||P.some(function(k){return s[k]!==t[k];})||band!==(t.band||5)||sales!==!!t.allow_sales;
return M.blk("TARGET SPLIT",'<span class="stg '+(t?"live":"paper")+'">'+(t?"SET "+esc(String(t.set_at||"").slice(0,10)):"NOT SET")+'</span>',
'<div class="src" style="white-space:normal">Set your own split: drag a slider or type a number; the unlocked parts adjust so the total stays 100%.</div>'+bars+
'<div class="q gap" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center"><span class="src">Tolerance band +-<input type="number" min="1" max="20" value="'+band+'" data-p23b="1" style="width:52px"> points</span><label class="src"><input type="checkbox" data-p23s="1"'+(sales?" checked":"")+'> allow sales to reach the target</label></div>'+
(changed?'<div class="fl" style="margin-top:8px">BEFORE YOU SAVE: THIS SPLIT AGAINST YOUR CURRENT ONE</div>'+compare(a,s)+moves(a,s)+'<div class="gap"><button class="btn" data-p23="save">Save this split</button> <button class="btn sm" data-p23="reset">Reset</button></div>':"")+
(note?'<div class="src">'+esc(note)+'</div>':"")+plan(a),
"Cash ($"+ac.cash.toFixed(0)+") is shown apart and counts as new money. Every change is logged with its date. "+esc(a.method||""));}
function plan(a){var p=a.plan;if(!p)return "";return '<div class="fl" style="margin-top:10px">PLAN TO REACH THE SAVED TARGET</div>'+(p.facts||[]).map(function(f){return '<div class="q" style="white-space:normal;color:var(--wn)">'+esc(f)+'</div>';}).join("")+
((p.steps||[]).length?p.steps.map(function(s){return '<div class="src" style="white-space:normal">'+s.step+". "+esc(s.line)+'</div>';}).join("")+'<div class="src">Fees $'+p.fees.toFixed(2)+DOT+'tax estimate $'+p.tax_estimate.toFixed(2)+DOT+esc(p.note)+'</div>':'<div class="src">Inside the band: nothing to do.</div>')+
(a.history&&a.history.length?'<details class="src"><summary>Target history</summary>'+a.history.slice().reverse().map(function(h){return '<div>'+esc(String(h.set_at||"").slice(0,16))+": "+h.stocks+"/"+h.bonds+"/"+h.etfs+" band +-"+h.band+(h.allow_sales?", sales allowed":"")+'</div>';}).join("")+'</details>':"");}
function bar(){var a=M.X.alloc;if(!a||!a.target||!a.actual)return "";var t=a.target,ac=a.actual,col={stocks:"var(--ac)",bonds:"var(--ok)",etfs:"var(--wn)"};
function strip(v){return '<div style="display:flex;height:12px;border-radius:4px;overflow:hidden;margin:3px 0">'+P.map(function(k){return '<div title="'+NAME[k]+'" style="width:'+v[k]+'%;background:'+col[k]+'"></div>';}).join("")+'</div>';}
var out=(a.plan||{}).outside_band||[];
return M.blk("TARGET SPLIT",'<span class="stg '+(out.length?"stale":"live")+'">'+(out.length?"OUTSIDE THE BAND":"IN THE BAND")+'</span>','<div class="src">Target '+t.stocks+"/"+t.bonds+"/"+t.etfs+'</div>'+strip(t)+'<div class="src">Actual '+P.map(function(k){return ac.pct[k].toFixed(0);}).join("/")+'</div>'+strip(ac.pct)+
'<div class="src">'+P.map(function(k){return '<span style="color:'+col[k]+'">'+String.fromCharCode(9632)+'</span> '+NAME[k];}).join("  ")+'</div>',"STOCKS/BONDS/ETFs, % of the invested money. Details and the plan on PORTFOLIO.");}
function save(){var a=M.X.alloc,s=tgt(a),tok=MC.store(MC.K.tok);if(!tok){note="Add your token in the Log tab first.";paint();return;}
if(P.reduce(function(t,k){return t+s[k];},0)!==100){note="The three parts must add up to 100%.";paint();return;}
if(a.assumptions&&preview(s,a.assumptions,a.max_loss).breaks&&!confirmBreak){note="This split breaks your risk profile: press 'Save it anyway' or adjust the profile.";paint();return;}
var ts=new Date().toISOString().replace(/[-:]/g,"").slice(0,15)+"Z",id="alloc-"+ts,obj={kind:"allocation",id:id,stocks:s.stocks,bonds:s.bonds,etfs:s.etfs,band:band,allow_sales:sales,at:new Date().toISOString().slice(0,19)+"Z"};
note="Saving"+String.fromCharCode(8230);paint();
fetch(API+"/contents/answers/"+id+".json",{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:"Market Council: target split "+s.stocks+"/"+s.bonds+"/"+s.etfs,content:btoa(JSON.stringify(obj))})})
.then(function(r){note=r.ok?"Saved. The engine logs it and plans toward it within a few minutes.":"Could not be saved ("+r.status+").";if(r.ok){confirmBreak=false;[90,180,300].forEach(function(x){setTimeout(M.reload,x*1000);});}paint();}).catch(function(){note="Could not be saved. Check your connection.";paint();});}
function paint(){var el=$("v-portfolio");if(!el)return;var h=control();if(!h)return;var box=$("p23-port");if(!box){box=document.createElement("div");box.id="p23-port";var after=$("p22-port");if(after&&after.nextSibling)el.insertBefore(box,after.nextSibling);else el.insertBefore(box,el.firstChild);}
if(box.__h!==h){var f=document.activeElement&&document.activeElement.getAttribute&&(document.activeElement.getAttribute("data-p23n")||document.activeElement.getAttribute("data-p23r"));box.innerHTML=h;box.__h=h;if(f){var e=box.querySelector('[data-p23r="'+f+'"]')||box.querySelector('[data-p23n="'+f+'"]');if(e)e.focus();}}}
document.addEventListener("input",function(e){var t=e.target;if(!t.getAttribute)return;var k=t.getAttribute("data-p23r");
if(k){var n=document.querySelector('[data-p23n="'+k+'"]');if(n)n.value=t.value;}});   /* while dragging: only the number moves */
document.addEventListener("change",function(e){var t=e.target;if(!t.getAttribute)return;var k=t.getAttribute("data-p23r")||t.getAttribute("data-p23n");if(k){setPart(k,+t.value);return;}
if(t.getAttribute("data-p23b")){band=Math.max(1,Math.min(20,+t.value||5));paint();return;}
var l=t.getAttribute("data-p23l");if(l){lock[l]=t.checked;paint();}if(t.getAttribute("data-p23s")){sales=t.checked;paint();}});
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p23],[data-p23p]"):null;if(!b)return;var p=b.getAttribute("data-p23p");
if(p){var v=p.split("|").map(Number);draft={stocks:v[0],bonds:v[1],etfs:v[2]};paint();return;}var k=b.getAttribute("data-p23");
if(k==="save")save();else if(k==="anyway"){confirmBreak=true;save();}else if(k==="reset"){draft=null;band=null;sales=null;note="";paint();}});
var prevTd=M.slots["td-dec"];M.slots["td-dec"]=function(){var h=prevTd?prevTd():"";return h+bar();};
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);paint();};
MC.hooks.push(paint);
M.reload();
})();
