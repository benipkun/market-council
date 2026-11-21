/* Market Council add-on 25 (21 Nov 2026): the news desk and the company files.
   TODAY: "NEWS THAT MATTERS", at most five items, each with what it means for your money and the event study's
   past-cases line (state/news/today.json, built by ops/engine/news.py, plain code).
   RESEARCH > FILES: a file per holding, watchlist share and best new idea (state/files/), the sector briefs, the
   thesis tracker, the event study and the three-book comparison (with news, without news, S&P 500 fund). */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DOT=" "+String.fromCharCode(183)+" ";
M.extra.newsToday="state/news/today.json";M.extra.filesIx="state/files/index.json";M.extra.sectors="state/files/sectors.json";
M.extra.thesis="state/files/thesis_log.json";M.extra.study="state/news/event_study.json";M.extra.nbooks="state/news/books.json";M.extra.nbudget="state/news/budget.json";
var css=document.createElement("style");css.textContent=
".p25i{border-top:1px solid var(--bd);padding:8px 0}.p25i:first-child{border-top:0}.p25i a{color:var(--tx);text-decoration:none;font-weight:600}"+
".p25m{font-size:12px;color:var(--dim);margin-top:3px;line-height:1.4}.p25k{display:inline-block;font-size:10px;letter-spacing:.04em;border:1px solid var(--bd);border-radius:3px;padding:1px 5px;margin-right:5px;color:var(--dim)}"+
".p25k.up{color:var(--ok,#3c9);border-color:currentColor}.p25k.dn{color:var(--wn,#e85);border-color:currentColor}"+
".p25f{border-top:1px solid var(--bd);padding:8px 0;cursor:pointer}.p25f b{color:var(--tx)}.p25d{font-size:12.5px;line-height:1.45;margin:6px 0 2px}.p25d h4{font-size:11px;color:var(--dim);margin:10px 0 3px;letter-spacing:.05em}"+
".p25t{width:100%;border-collapse:collapse;font-size:12px}.p25t td{padding:4px;border-top:1px solid var(--bd)}.p25t tr:first-child td{color:var(--dim);font-size:10.5px}";
document.head.appendChild(css);
function X(k){return (M.X||{})[k]||null;}
function mark(t){return t?'<span class="p25k '+(t==="strengthens"?"up":t==="weakens"?"dn":"")+'">THESIS '+esc(String(t).toUpperCase())+'</span>':"";}
function link(t,u){return u?'<a href="'+esc(u)+'" target="_blank" rel="noopener">'+esc(t)+'</a>':'<b>'+esc(t)+'</b>';}
function newsBlock(){var d=X("newsToday");if(!d)return "";var it=d.items||[];
var body=it.length?it.map(function(x){return '<div class="p25i"><span class="p25k">'+esc(x.ticker)+'</span><span class="p25k">'+esc(String(x.type||"").toUpperCase())+'</span>'+(x.keep?'<span class="p25k">FACTS ONLY</span>':mark(x.thesis))+
'<div style="margin-top:4px">'+link(x.title,x.url)+'</div><div class="p25m">'+esc(x.money||"")+'</div><div class="p25m">'+esc(x.past||"")+'</div><div class="p25m">'+esc(x.source||"")+DOT+"importance "+Number((x.scores||{}).importance||0).toFixed(2)+'</div></div>';}).join("")
:'<div class="p25m">Nothing scored as important in the last three days. The desk read every filing, analyst change and headline for your holdings and ideas.</div>';
return M.blk("NEWS THAT MATTERS",'<span class="stg live">'+it.length+' OF 5</span>',body,'<div class="src">'+esc(d.rule||"")+' News desk, plain code; estimates, not forecasts.</div>');}
var prevTd=M.slots["td-dec"];M.slots["td-dec"]=function(){var h=prevTd?prevTd():"";return newsBlock()+h;};
var openF={},files={};
function fileHtml(f){if(!f)return '<div class="p25m">Loading'+String.fromCharCode(8230)+'</div>';var v=f.valuation||{},o=v.ours||{},a=v.analysts||{},n=f.numbers||{},rec=((f.management||{}).record)||{};
function sec(h,txt,src){return '<h4>'+h+'</h4>'+(txt?'<div>'+esc(txt)+'</div>':'<div class="p25m">Not in the file yet: the committee’s next memo adds it.</div>')+(src&&txt?'<div class="p25m">'+esc(src)+'</div>':"");}
var h='<div class="p25d"><div class="p25m">From the file, updated '+esc(String(f.updated||"").slice(0,10))+DOT+"why: "+esc((f.why_updated||[]).join("; "))+'</div>';
if(f.standing)h+='<div class="p25m" style="color:var(--tx)">'+esc(f.standing)+'</div>';
h+=sec("HOW IT MAKES MONEY",(f.business||{}).text,(f.business||{}).source);
var seg=(f.segments||{}).text;h+=sec("SEGMENTS",seg&&typeof seg!=="string"?seg.map(function(s){return s.name+(s.share!=null?" "+Math.round(100*s.share)+"%":"");}).join(", "):seg,(f.segments||{}).source);
h+='<h4>KEY NUMBERS AND TREND</h4><div>'+esc(n.trend||n.note||"")+'</div><div class="p25m">'+esc(n.source||"")+(n.read_at?" (read "+esc(n.read_at)+")":"")+'</div>';
h+=sec("COMPETITORS",typeof (f.competitors||{}).text==="string"?(f.competitors||{}).text:JSON.stringify((f.competitors||{}).text||""),(f.competitors||{}).source);
h+=sec("WHAT DRIVES THE PRICE",typeof (f.drivers||{}).text==="string"?(f.drivers||{}).text:((f.drivers||{}).text||[]).join("; "),(f.drivers||{}).source);
h+='<h4>MANAGEMENT AND ITS RECORD</h4><div>'+esc(typeof (f.management||{}).text==="string"?(f.management||{}).text:"")+'</div><div>'+esc(rec.text||"")+'</div>';
h+='<h4>VALUATION</h4><div>'+(o.base?"Our model: $"+o.base+" (range $"+o.low+" to $"+o.high+"; "+esc(o.main_assumption||"")+"). Estimate.":esc(o.reason||"Not valued."))+'</div><div>'+(a.mean?"Analysts: $"+a.low+" to $"+a.high+", average $"+a.mean+" ("+esc(a.count||"?")+" brokers, "+esc(a.rating||"")+")":"")+(v.price?DOT+"price $"+v.price:"")+'</div>';
h+=sec("BULL CASE",(f.bull||{}).text,(f.bull||{}).source);
var bear=(f.bear||{}).items;h+=sec("BEAR CASE",bear&&bear.map?bear.map(function(r){return r.risk||r;}).join("; "):bear,(f.bear||{}).source);
var wc=(f.would_change||{}).text;h+=sec("WHAT WOULD CHANGE OUR MIND",wc&&wc.map?wc.map(function(r){return typeof r==="string"?r:(r.what||r.item||JSON.stringify(r));}).join("; "):wc,(f.would_change||{}).source);
if(f.checks)h+='<h4>THE 7 CHECKS</h4><div>Passes '+esc(f.checks.score)+" of "+esc(f.checks.of)+'</div>';
if(f.forecast)h+='<h4>FORECASTER</h4><div>'+esc(f.forecast.text)+'</div>';
h+='<h4>EVENT STUDY</h4><div>'+esc((f.event_study||{}).text||"")+'</div>';
h+='<h4>COMING DATES</h4><div>'+((f.dates||[]).map(function(d){return esc(d.date+" "+d.what);}).join("<br>")||"None on file.")+'</div>';
h+='<h4>NEWS, LAST 30 DAYS</h4>'+((f.news||[]).map(function(x){return '<div class="p25i">'+(f.keep?"":mark(x.thesis))+link(x.title,x.url)+'<div class="p25m">'+esc(String(x.first_seen||"").slice(0,10))+DOT+esc(x.type)+(x.thesis_how?DOT+esc(x.thesis_how):"")+'</div></div>';}).join("")||'<div class="p25m">No important news.</div>');
if((f.missing||[]).length)h+='<div class="p25m" style="margin-top:8px">Not in the file yet: '+esc(f.missing.join(", "))+'. The Advisor says so instead of guessing.</div>';
return h+'</div>';}
function loadFile(t){if(files[t])return;MC.get("state/files/"+t+".json").then(function(f){files[t]=f;paint();}).catch(function(){files[t]={missing:["the file could not be loaded"]};paint();});}
function pct(x){return x==null?"-":(x>=0?"+":"")+(100*x).toFixed(1)+"%";}
function paint(){var el=$("v-files");if(!el||el.hidden)return;var ix=X("filesIx")||{},sc=X("sectors")||{},th=X("thesis")||{},st=X("study")||{},bk=X("nbooks")||{},bu=X("nbudget")||{};
var h='<div class="hd"><h2>FILES</h2></div>';
var b=bk.books||{},w=b["with"]||{},wo=b.without||{};
h+=M.blk("PROOF OF PROFIT",'<span class="stg paper">PAPER</span>','<table class="p25t"><tr><td>Book</td><td>Cases</td><td>Result</td><td>S&amp;P 500 fund</td><td>Against it</td></tr>'+
[["System with news and files",w],["System without them",wo]].map(function(r){return "<tr><td>"+r[0]+"</td><td>"+(r[1].cases||0)+(r[1].cases<20?" (too few cases)":"")+"</td><td>"+pct(r[1].avg)+"</td><td>"+pct(r[1].spy)+"</td><td>"+pct(r[1].vs_spy)+"</td></tr>";}).join("")+'</table><div class="p25m">'+esc(bk.verdict||"Starts with the next engine run.")+'</div>','<div class="src">'+esc(bk.method||"")+'</div>');
var br=(ix.broken||[]);h+=M.blk("THESIS TRACKER",'<span class="stg '+(br.length?"stale":"live")+'">'+(br.length?br.length+" BROKEN":"NONE BROKEN")+'</span>',
(br.map(function(x){return '<div class="p25i"><b>'+esc(x.ticker)+'</b>: '+esc(x.why)+'. Review the file.</div>';}).join(""))+((th.marks||[]).slice(-8).reverse().map(function(m){return '<div class="p25i">'+mark(m.mark)+'<span class="p25k">'+esc(m.t)+'</span>'+link(m.title,m.url)+'<div class="p25m">'+esc(String(m.at).slice(0,10))+DOT+esc(m.how||"")+'</div></div>';}).join("")||'<div class="p25m">No important item checked yet.</div>'),'<div class="src">'+esc(th.rule||"")+'</div>');
h+=M.blk("COMPANY FILES",'<span class="stg live">'+(ix.files||[]).length+'</span>',(ix.files||[]).map(function(f){var o=openF[f.ticker];return '<div class="p25f" data-p25f="'+esc(f.ticker)+'"><b>'+esc(f.ticker)+'</b> '+esc(f.name||"")+(f.held?' <span class="p25k">HELD</span>':"")+(f.keep?' <span class="p25k">FACTS ONLY</span>':"")+'<div class="p25m">updated '+esc(String(f.updated||"").slice(0,10))+(f.memo_date?DOT+"memo "+esc(f.memo_date):DOT+"no memo yet")+(f.news?DOT+f.news+" news":"")+((f.missing||[]).length?DOT+"missing: "+esc(f.missing.join(", ")):"")+'</div>'+(o?fileHtml(files[f.ticker]):"")+'</div>';}).join("")||'<div class="p25m">Built by the next engine run.</div>',"");
h+=M.blk("SECTOR BRIEFS","",(sc.briefs||[]).map(function(s){return '<div class="p25i"><b>'+esc(s.sector)+'</b><div class="p25m">'+esc(s.text)+'</div>'+(s.news||[]).map(function(x){return '<div class="p25m">'+link(x.title,x.url)+'</div>';}).join("")+'</div>';}).join("")||'<div class="p25m">Built by the next engine run.</div>',"");
var ty=st.types||{};h+=M.blk("EVENT STUDY",'<span class="stg live">'+esc(st.shares||0)+' SHARES</span>','<table class="p25t"><tr><td>Event</td><td>Cases</td><td>5 days, typical</td><td>Range</td></tr>'+Object.keys(ty).sort(function(a,b){return ((ty[b]["5d"]||{}).n||0)-((ty[a]["5d"]||{}).n||0);}).map(function(k){var x=ty[k]["5d"]||{};return "<tr><td>"+esc(ty[k].name||k)+"</td><td>"+(x.n||0)+(x.n<20?" (too few)":"")+"</td><td>"+pct(x.median)+"</td><td>"+pct(x.p10)+" to "+pct(x.p90)+"</td></tr>";}).join("")+'</table>','<div class="src">Since '+esc(st.since||"")+". "+esc(st.method||"")+' More in RESEARCH > QUANT LAB > Event study.</div>');
var sp=bu.spent||{},cp=bu.cap||{};h+='<div class="src">Model budget today: sorting $'+Number(sp.sort||0).toFixed(3)+' of $'+Number(cp.sort||0).toFixed(2)+DOT+'thesis checks $'+Number(sp.thesis||0).toFixed(3)+' of $'+Number(cp.thesis||0).toFixed(2)+'. Hard caps; past them plain rules decide.</div>';
el.innerHTML=h;}
document.addEventListener("click",function(e){var t=e.target.closest&&e.target.closest("[data-p25f]");if(!t||e.target.closest("a"))return;var k=t.getAttribute("data-p25f");openF[k]=!openF[k];if(openF[k])loadFile(k);paint();});
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);paint();};
var prevShow=MC.onShow;MC.onShow=function(t){if(prevShow)prevShow(t);if(t==="files"){M.reload();paint();}};
})();
