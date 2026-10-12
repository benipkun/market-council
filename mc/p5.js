/* Market Council add-on 5: the checklist and the back-checks (data: state/backcheck.json and state/patterns.json).
   It shows what every check is, how it is measured, today's reading, and how the check did in the past; and for a
   share or the market, the past weeks that looked like today and what followed. Evidence, not a forecast. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;
var esc=MC.esc,num=MC.num,$=MC.$,MID=String.fromCharCode(183),DASH=String.fromCharCode(8212),MINUS=String.fromCharCode(8722);
M.extra.bc="state/backcheck.json";M.extra.pat="state/patterns.json";
var css=document.createElement("style");css.textContent=
".p5c{border-top:1px solid var(--bd);padding:7px 0;font-size:12.5px}.p5c:first-of-type{border-top:0}.p5c>summary{list-style:none;cursor:pointer;display:flex;gap:8px;align-items:baseline}.p5c>summary::-webkit-details-marker{display:none}"+
".p5c>summary .nm{flex:1;min-width:0;color:var(--tx)}.p5c.un>summary .nm{color:var(--dim)}.p5c .bd{padding:6px 0 2px;color:var(--dim);font-size:12px;white-space:normal}.p5c .bd b{color:var(--tx)}"+
".p5m{font-size:9.5px;font-weight:800;letter-spacing:.06em;border:1px solid var(--bd);border-radius:2px;padding:1px 5px;white-space:nowrap}.p5m.ok{color:var(--up);border-color:var(--up)}.p5m.no{color:var(--dn);border-color:var(--dn)}.p5m.na{color:var(--dim)}"+
".p5t{font-size:9px;font-weight:800;letter-spacing:.06em;border-radius:2px;padding:1px 5px;white-space:nowrap;border:1px solid var(--bd);color:var(--dim)}.p5t.ok{color:var(--ac);border-color:var(--ac)}"+
".p5p{margin:5px 0;font-size:12px;color:var(--dim);white-space:normal}.p5p b{color:var(--tx)}.p5s{font-size:10.5px;color:var(--dim);display:block}.p5h{font-size:13px;font-weight:700;color:var(--tx);margin:2px 0 4px;white-space:normal}"+
".p5w{border-left:2px solid var(--wn);padding:6px 9px;margin:8px 0;font-size:12px;color:var(--dim);white-space:normal}.p5w b{color:var(--tx)}.p5k{padding:10px 0;border-top:1px solid var(--bd)}.p5k:first-child{border-top:0}";
document.head.appendChild(css);
var H=[["1m","1 month"],["3m","3 months"],["6m","6 months"],["12m","12 months"]];
var FMT={d50:1,d200:1,r21:1,r63:1,dd:1,vol:1};
function sg(v,d){var n=num(v);return n==null?DASH:(n>0?"+":(n<0?MINUS:""))+Math.abs(100*n).toFixed(d==null?1:d)+"%";}
function p0(v){var n=num(v);return n==null?DASH:Math.round(100*n)+"%";}
function nn(v){var n=num(v);return n==null?DASH:Math.round(n).toLocaleString("en-US");}
function dl(s){return s?M.sd(s)+" "+String(s).slice(0,4):DASH;}
function ym(s){var m=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][parseInt(String(s).slice(5,7),10)-1];return m?m+" "+String(s).slice(0,4):String(s||DASH);}
function B(){var b=M.X.bc;return b&&b.status==="ok"&&b.checks?b:null;}
function P(){var p=M.X.pat;return p&&p.shares?p:null;}
function byId(id){var b=B();if(!b)return null;for(var i=0;i<b.checks.length;i++)if(b.checks[i].id===id)return b.checks[i];return null;}
function other(id){var b=B(),o=b?(b.other||[]):[];for(var i=0;i<o.length;i++)if(o[i].id===id)return o[i];return null;}
function vtag(v){return v==="working"?'<span class="p5t ok">WORKS</span>':'<span class="p5t">UNPROVEN</span>';}
function mark(p){return p===true?'<span class="p5m ok">PASS</span>':p===false?'<span class="p5m no">FAIL</span>':'<span class="p5m na">NO DATA</span>';}
function para(label,text){return text?'<div class="p5p"><b>'+label+'</b> '+text+'</div>':"";}
function det(sum,body){return '<details class="p3d"><summary>'+sum+'</summary>'+body+'</details>';}
function rec6(k){var r=k&&k.rows&&k.rows["6m"];if(!r)return "";var p=r.pass,f=r.fail;
return "Over the next six months, after costs: "+(p?sg(p.avg)+" on average after a pass ("+nn(p.n)+" cases, "+p0(p.win)+" made money)":"no passes on record")+"; "+(f?sg(f.avg)+" after a fail ("+nn(f.n)+" cases, "+p0(f.win)+" made money)":"no fails on record")+"; the S&P 500 fund made "+sg(r.spy_pass)+" over the same months as the passes.";}
function halves(k){return (k.halves||[]).map(function(h,i){return (i?"Second":"First")+" half, "+ym(h.from)+" to "+ym(h.to)+": pass "+sg(h.pass)+" ("+nn(h.n_pass)+"), fail "+sg(h.fail)+" ("+nn(h.n_fail)+"), fund "+sg(h.spy)+".";}).join(" ");}
function hist(k){var h=k&&k.history;return h?"Tested on "+nn(h.shares)+" shares from "+ym(h.from)+" to "+ym(h.to)+" ("+h.years+" years, "+nn(h.cases)+" share-months).":"";}

/* ---------- one check row on a card ---------- */
function rowBody(x){var k=byId(x.id),o=other(x.id),h="";
if(k)h+=para("What it measures.",esc(k.what)+" "+esc(k.why))+para("The rule.",esc(k.rule))+para("Data source.",esc(k.source));
else if(o)h+=para("What it is.",esc(o.what))+para("The rule.",esc(o.rule));
h+=para("Today.",(x.reading?esc(x.reading):"no reading")+(x.line?" "+MID+" line: "+esc(x.line):"")+" "+MID+" "+(x.pass===true?"passes":x.pass===false?"fails":"unknown")+(x.margin?" ("+esc(x.margin)+")":"")+(x.needs?". To pass it needs "+esc(x.needs):"")+".");
h+=para("Data age.",x.as_of?esc(x.as_of):"not recorded for this card yet; it appears after the next engine run");
if(k)h+=para("Track record.",(k.history?esc(hist(k))+" "+esc(rec6(k))+" "+esc(halves(k))+" ":"")+"<b>"+(k.verdict==="working"?"Works":"Unproven")+":</b> "+esc(k.verdict_why))+(k.rebuilt?para("How the past was rebuilt.",esc(k.rebuilt)):"");
else if(o)h+=para("Track record.",esc(o.record));
return h+'<div class="gap"><button class="btn sm" data-tab="checks">All checks and full tables</button></div>';}
function checklist(c){var rows=c.checks||[];if(!rows.length)return "";var b=B();
return '<div class="lbl" style="margin-top:10px">Checklist '+MID+" tap a row</div>"+rows.map(function(x){var k=byId(x.id),o=other(x.id),un=k?k.verdict!=="working":(o&&o.verdict==="unproven");
return '<details class="p5c'+(un?" un":"")+'"><summary>'+mark(x.pass)+'<span class="nm">'+esc(x.name)+(x.margin&&x.pass!=null?'<span class="p5s">'+esc(x.margin)+'</span>':"")+'</span>'+(k?vtag(k.verdict):(o&&o.verdict?vtag(o.verdict):""))+'</summary><div class="bd">'+rowBody(x)+'</div></details>';}).join("")+
'<div class="src">'+(b?"Greyed rows are checks the back-test could not prove on both halves of their history. They still count towards the score: the bar has not been changed. ":"The back-check results have not loaded yet. ")+"Past results are evidence, not a forecast.</div>";}

/* ---------- past weeks that looked like today ---------- */
function outTable(rows,base,baseName){if(!rows)return "";var any=false,cmp=[],h='<div class="ox"><table class="mt p3w"><tr><th>After</th><th>Cases</th><th>Average (median)</th><th>Best / worst</th><th>Made money</th></tr>';
H.forEach(function(x){var r=rows[x[0]],b=(base||{})[x[0]]||{};if(!r)return;any=true;h+="<tr><td>"+x[1]+"</td><td>"+nn(r.n)+"</td><td>"+sg(r.avg)+" ("+sg(r.med)+")</td><td>"+sg(r.best,0)+" / "+sg(r.worst,0)+"</td><td>"+p0(r.win)+"</td></tr>";if(b.avg!=null)cmp.push(x[1]+" "+sg(b.avg)+" ("+p0(b.win)+" made money)");});
return any?h+"</table></div>"+(cmp.length?'<div class="p5p"><b>For comparison, '+esc(baseName)+':</b> '+cmp.join("; ")+".</div>":""):"";}
function closest(list,six){return (list||[]).length?'<div class="p5p"><b>The closest five.</b> '+list.map(function(x){return (x[0]==="S&P 500 fund"?"":esc(x[0])+", ")+esc(dl(x[1]))+": "+(x[3]==null?"too recent to say":sg(x[3])+" six months later");}).join("; ")+".</div>":"";}
function setup(s,feats){return (feats||[]).map(function(f){var v=s?s[f.id]:null;return esc(f.name)+": <b>"+(v==null?DASH:(f.id==="vol"?(100*v).toFixed(1)+"%":FMT[f.id]?sg(v):Number(v).toFixed(1)))+"</b>";}).join("; ");}
function patBody(t,p){var pt=P(),h="",c=p.context||{};
h+=para("Today's setup"+(p.as_of?" ("+esc(dl(p.as_of))+")":"")+".",setup(p.setup,pt.features)+".");
var ctx=[];if(c.valuation_gap!=null)ctx.push("price is "+p0(Math.abs(c.valuation_gap))+(c.valuation_gap>=0?" under":" over")+" our fair value");
if(c.surprise_pct!=null)ctx.push("last earnings surprise "+(c.surprise_pct>0?"+":"")+Number(c.surprise_pct).toFixed(0)+"%"+(c.move_5d!=null?", five-day move "+sg(c.move_5d):""));
if(c.insider_buys_90d!=null)ctx.push(c.insider_buys_90d+" insider purchase"+(c.insider_buys_90d===1?"":"s")+" and "+(c.insider_sales_90d||0)+" sale"+(c.insider_sales_90d===1?"":"s")+" in 90 days");
if(c.stress)ctx.push("market stress level "+esc(String(c.stress)));
if(ctx.length)h+=para("Also true today, shown but not used to find matches.",esc(ctx.join("; "))+".");
h+=para("Searched in.",esc(p.group||"")+", week by week.");
h+=outTable(p.rows,p.base,"any week in the same shares");
h+=closest(p.closest);
if(p.same&&p.same.n!=null)h+=para("With the same earnings and insider picture as today.",p.same.n+" of the matches"+(p.same.six?": "+sg(p.same.six.avg)+" on average six months later, "+p0(p.same.six.win)+" made money":"")+"."+(p.same.n<20?" Too few cases to rely on.":""));
return h+'<div class="src">'+esc(pt.method||"")+" "+esc(pt.honesty||"")+"</div>";}
function patLine(t){var pt=P(),p=pt&&pt.shares?pt.shares[t]:null;if(!p||!p.line)return "";
return '<div class="q"><b style="color:var(--tx)">Seen before?</b> '+esc(p.line)+(p.few?"":" After costs.")+' <span style="color:var(--dim)">Evidence, not a forecast.</span></div>'+(p.rows&&p.n?det("See the matches and what followed",patBody(t,p)):"");}
M.cardExtra=function(c){if(!c||c.kind==="test")return "";return checklist(c)+(c.ticker?patLine(c.ticker):"");};
M.patLine=patLine;

/* ---------- the "How the checks work" page ---------- */
function recTable(k){var h='<div class="ox"><table class="mt p3w"><tr><th>After</th><th>Passed</th><th>Failed</th><th>S&amp;P 500 fund</th></tr>';
H.forEach(function(x){var r=k.rows[x[0]];if(!r)return;var p=r.pass,f=r.fail;h+="<tr><td>"+x[1]+"</td><td>"+(p?sg(p.avg)+'<span class="p5s">'+nn(p.n)+" cases, "+p0(p.win)+" up</span>":DASH)+"</td><td>"+(f?sg(f.avg)+'<span class="p5s">'+nn(f.n)+" cases, "+p0(f.win)+" up</span>":DASH)+"</td><td>"+sg(r.spy_pass)+"</td></tr>";});
return h+"</table></div>";}
function fullTable(k){var h='<div class="ox"><table class="mt p3w"><tr><th>After</th><th>Group</th><th>Cases</th><th>Average</th><th>Median</th><th>Made money</th><th>Worst case</th></tr>';
H.forEach(function(x){var r=k.rows[x[0]];if(!r)return;[["Passed",r.pass],["Failed",r.fail]].forEach(function(g){var s=g[1];if(s)h+="<tr><td>"+x[1]+"</td><td>"+g[0]+"</td><td>"+nn(s.n)+"</td><td>"+sg(s.avg)+"</td><td>"+sg(s.med)+"</td><td>"+p0(s.win)+"</td><td>"+sg(s.worst,0)+"</td></tr>";});});
return h+"</table></div>";}
function checkBlock(k){var h='<div class="p5k"><div class="p5h">'+esc(k.name)+" "+vtag(k.verdict)+'</div>'+para("What it measures.",esc(k.what)+" "+esc(k.why))+para("The rule.",esc(k.rule))+para("Data source.",esc(k.source));
if(k.rows){h+=para("History used.",esc(hist(k)))+recTable(k)+para(k.verdict==="working"?"Verdict: works.":"Verdict: unproven.",esc(k.verdict_why))+
det("Both halves, medians and worst cases",para("The two halves, six months after.",esc(halves(k)))+fullTable(k)+para("How the past was rebuilt.",esc(k.rebuilt||"")));}
else h+=para("Verdict: unproven.",esc(k.verdict_why));
return h+"</div>";}
function comboBlock(b){var c=b.combined||{},rows=c.by_k||[];if(!rows.length)return '<div class="fl" style="font-size:12px">The combined table needs the earnings and insider history, which is still being fetched. It appears after the next run.</div>';
var h=para("What can be tested.",esc(c.note||""))+para("The four checks counted.",esc((c.names||[]).join("; "))+".")+(c.history?para("History used.",ym(c.history.from)+" to "+ym(c.history.to)+" ("+c.history.years+" years, "+nn(c.history.cases)+" share-months).") :"")+
'<div class="ox"><table class="mt p3w"><tr><th>Passes</th><th>Cases</th><th>After 6 months</th><th>Fund, same months</th><th>After 12 months</th></tr>';
rows.forEach(function(r){var s=r.rows["6m"]||{},a=s.at,y=(r.rows["12m"]||{}).at;h+="<tr><td>"+r.k+" of "+(c.set||[]).length+"</td><td>"+(a?nn(a.n):"0")+"</td><td>"+(a?sg(a.avg)+'<span class="p5s">'+p0(a.win)+" made money</span>":DASH)+"</td><td>"+sg(s.spy)+"</td><td>"+(y?sg(y.avg):DASH)+"</td></tr>";});
h+="</table></div>"+det("Each half separately, and the other horizons",rows.map(function(r){return para(r.k+" passes.",(r.halves||[]).map(function(x,i){return (i?"second half ":"first half ")+sg(x.avg)+" against "+sg(x.spy)+" for the fund ("+nn(x.n)+" cases)";}).join("; ")+". "+H.map(function(x){var a=(r.rows[x[0]]||{}).at;return x[1]+": "+(a?sg(a.avg)+", median "+sg(a.med)+", worst "+sg(a.worst,0):DASH);}).join("; ")+".");}).join(""));
var l=b.live_score;if(l)h+=para("The full seven-check score.",esc(l.note)+" Days logged so far: "+l.days+".");
return h;}
function marketBlock(pt){var m=pt.market;if(!m)return "";var h=para("Today ("+esc(dl(m.as_of))+").","Stress level <b>"+esc(String(m.level||DASH))+"</b>; "+setup(m.setup,pt.market_features)+(m.cape!=null?"; ten-year price-to-earnings ratio of the S&P 500: <b>"+Number(m.cape).toFixed(1)+"</b>":"")+".");
[["stress_trend","Stress level and trend like today"],["with_valuation","Stress level, trend and valuation like today"]].forEach(function(x){var r=m[x[0]];if(!r)return;
h+='<div class="p5k"><div class="p5h">'+x[1]+'</div><div class="p5p">'+esc(r.line||"")+(r.n&&!r.few?" After costs.":"")+'</div>'+outTable(r.rows,m.base,"any week since 2001")+closest(r.closest)+(r.matched_on?para("Matched on.",esc(r.matched_on.join("; "))+"."):"")+"</div>";});
return h+'<div class="src">Past patterns are evidence, not a forecast. One market, 26 years: the cases are few and overlap.</div>';}
function html(){var b=M.X.bc,pt=P(),h="";
if(!b)return '<div class="msg">The back-checks have not been published yet. The first run reads about 26 years of prices and takes most of an hour.</div>';
if(b.status!=="ok"||!b.checks)return M.blk("HOW THE CHECKS WORK","",'<div class="fl" style="font-size:12.5px">'+esc((b.limits||["The last back-check run did not finish."]).join(" "))+"</div>",M.upd(b.as_of));
var cv=b.coverage||{},works=b.checks.filter(function(k){return k.verdict==="working";}).length;
h+=M.blk("HOW THE CHECKS WORK",'<span class="stg '+(works?"live":"paper")+'">'+works+" OF "+b.checks.length+" PROVEN</span>",
'<div style="font-size:12.5px;white-space:normal">Every check on a card is listed here: what it measures, the exact rule, and what shares did afterwards when it passed and when it failed. Tested on <b>'+nn(cv.shares)+" shares</b> over <b>"+cv.years+" years</b> of prices ("+esc(dl(cv.from))+" to "+esc(dl(cv.to))+").</div>"+
'<div class="p5w"><b>Read this first.</b> '+esc(cv.survivorship||"")+"</div>"+para("What counts as working.",esc(b.verdict_rule||""))+para("Costs.",esc((b.cost||{}).note||"")),
"Past results are evidence, not a forecast. You place every order yourself. "+M.upd(b.as_of)+".");
h+=M.blk("THE SEVEN CHECKS",'',b.checks.map(checkBlock).join(""),esc(b.method||""));
h+=M.blk("THE COMBINED SCORE",'',comboBlock(b),"More passes should go with better results if the score means something. Read the pass column against the fund column.");
if(pt&&pt.market)h+=M.blk("THE MARKET: SEEN BEFORE?",'',marketBlock(pt),esc(pt.method||""));
if(pt){var ts=Object.keys(pt.shares||{}).sort();if(ts.length)h+=M.blk("YOUR SHARES: SEEN BEFORE?",'<span class="stg">'+ts.length+" SHARES</span>",ts.map(function(t){var p=pt.shares[t];
return '<div class="p5k"><div class="p5h">'+esc(t)+(p.name&&p.name!==t?' <span style="font-weight:400;color:var(--dim)">'+esc(p.name)+"</span>":"")+'</div><div class="p5p">'+esc(p.line||"")+"</div>"+(p.rows&&p.n?det("See the matches and what followed",patBody(t,p)):"")+"</div>";}).join(""),esc(pt.not_matched||""));}
h+=M.blk("OTHER CHECKS A CARD DEPENDS ON",'',(b.other||[]).map(function(o){return '<div class="p5k"><div class="p5h">'+esc(o.name)+(o.verdict?" "+vtag(o.verdict):"")+'</div>'+para("What it is.",esc(o.what))+para("The rule.",esc(o.rule))+para("Track record.",esc(o.record))+"</div>";}).join(""),"");
h+=M.blk("WHAT COULD NOT BE TESTED",'',(b.untested||[]).map(function(u){return para(esc(u.what)+".",esc(u.why));}).join("")+((b.limits||[]).length?para("Limits hit in the last run.",esc(b.limits.join(" "))):""),esc(b.sources||""));
return h;}
function render(){var el=$("v-checks");if(!el)return;var h=html();if(el.__h!==h){var open={};Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){if(d.open)open[i]=1;});var had=el.__h!=null;el.innerHTML=h;el.__h=h;
if(had)Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){d.open=!!open[i];});}}
var prevCc=M.slots["cc-extra"];
M.slots["cc-extra"]=function(){setTimeout(render,0);var top=prevCc?prevCc():"",b=B();if(!b)return top;
var works=b.checks.filter(function(k){return k.verdict==="working";}).length;
return top+M.blk("HOW THE CHECKS WORK",'<span class="stg '+(works?"live":"paper")+'">'+works+" OF "+b.checks.length+" PROVEN</span>",'<div style="font-size:12.5px;white-space:normal">Every check on a card, the exact rule behind it, and how it did over '+((b.coverage||{}).years||DASH)+' years of history.</div><div class="gap"><button class="btn sm" data-tab="checks">Open the checks</button></div>',"Back-tested on two separate halves of the history, after costs.");};
MC.hooks.push(render);
M.reload();
})();
