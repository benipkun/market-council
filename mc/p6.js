/* Market Council add-on 6: quant tools, all on paper (data: state/ranges.json, options.json, pairs.json, learned.json).
   Outcome ranges from 10,000 simulated futures with assumptions you can change; an options calculator; pairs tested on
   years the fit never saw; a learned signal validated walk-forward; and what an order costs. Evidence, not forecasts. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;
var esc=MC.esc,num=MC.num,$=MC.$,MID=String.fromCharCode(183),DASH=String.fromCharCode(8212),MINUS=String.fromCharCode(8722);
M.extra.rng="state/ranges.json";M.extra.opt="state/options.json";M.extra.pairs="state/pairs.json";M.extra.learn="state/learned.json";
var css=document.createElement("style");css.textContent=
".p6f{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.p6f label{font-size:10.5px;color:var(--dim);display:flex;flex-direction:column;gap:3px;flex:1;min-width:84px;letter-spacing:.03em}"+
".p6f input,.p6f select{background:var(--bg);border:1px solid var(--bd);color:var(--tx);border-radius:3px;padding:9px 8px;font:inherit;font-size:13px;width:100%;box-sizing:border-box}"+
".p6g{display:grid;grid-template-columns:1fr auto;gap:2px 10px;font-size:12.5px;padding:7px 0;border-top:1px solid var(--bd)}.p6g:first-child{border-top:0}.p6g b{color:var(--tx)}.p6g .x{grid-column:1/3;font-size:11.5px;color:var(--dim);white-space:normal}";
document.head.appendChild(css);
function sg(v,d){var n=num(v);if(n==null)return DASH;var s=Math.abs(100*n).toFixed(d==null?1:d);return (Number(s)===0?"":(n>0?"+":MINUS))+s+"%";}
function p0(v){var n=num(v);return n==null?DASH:Math.round(100*n)+"%";}
function p1(v){var n=num(v);return n==null?DASH:(100*n).toFixed(1)+"%";}
function of100(v){var n=num(v);return n==null?DASH:String(Math.round(100*n));}
function nn(v){var n=num(v);return n==null?DASH:Math.round(n).toLocaleString("en-US");}
function usd(v,d){var n=num(v);return n==null?DASH:(n<0?MINUS:"")+"$"+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:d==null?2:d,maximumFractionDigits:d==null?2:d});}
function big(v){var n=num(v);return n==null?DASH:n>=1e9?"$"+(n/1e9).toFixed(1)+"bn":n>=1e6?"$"+(n/1e6).toFixed(0)+"m":"$"+nn(n);}
function dl(s){return s?M.sd(s)+" "+String(s).slice(0,4):DASH;}
function para(l,t){return t?'<div class="p5p"><b>'+l+'</b> '+t+'</div>':"";}
function det(sum,body){return '<details class="p3d"><summary>'+sum+'</summary>'+body+'</details>';}
function R(){var r=M.X.rng;return r&&r.items?r:null;}

/* ---------- simulation in the browser, the same method as the engine ---------- */
function rnd32(seed){var a=seed>>>0;return function(){a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296;};}
function gauss(r){var u=0,v=0;while(u===0)u=r();while(v===0)v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);}
function stat(a){var s=Array.prototype.slice.call(a).sort(function(x,y){return x-y;}),n=s.length,loss=0,sum=0,i;for(i=0;i<n;i++){if(s[i]<0)loss++;sum+=s[i];}
return {med:s[Math.floor(n/2)],lo:s[Math.floor(n*0.1)],hi:s[Math.floor(n*0.9)],loss:loss/n,avg:sum/n};}
var RUNS=10000,HZ=[["1m","1 month",21],["1y","1 year",252],["5y","5 years",1260]];
function simulate(r,mu,vol,years,plans){var n=Math.min(r.length,Math.max(252,Math.round(years*252))),x=r.slice(r.length-n),i,m=0,v=0,rr=rnd32(20261011);
for(i=0;i<n;i++)m+=x[i];m/=n;for(i=0;i<n;i++)v+=(x[i]-m)*(x[i]-m);var sd=Math.sqrt(v/(n-1)),sc=vol>0?(vol/Math.sqrt(252))/sd:1,sd2=sd*sc;
var rc=new Float64Array(n),cs=new Float64Array(n+1);for(i=0;i<n;i++){var y=(x[i]-m)*sc+mu/252;if(y<-0.95)y=-0.95;rc[i]=y;cs[i+1]=cs[i]+Math.log(1+y);}
var nb=n-20,out={boot:{},bell:{},used:n/252,vol:sd2*Math.sqrt(252)};
HZ.forEach(function(h){var a=new Float64Array(RUNS),b=new Float64Array(RUNS),k=h[2]/21,run,j,s;
for(run=0;run<RUNS;run++){s=0;for(j=0;j<k;j++){var st=Math.floor(rr()*nb);s+=cs[st+21]-cs[st];}a[run]=Math.exp(s)-1;b[run]=Math.exp(h[2]*(mu/252-sd2*sd2/2)+sd2*Math.sqrt(h[2])*gauss(rr))-1;}
out.boot[h[0]]=stat(a);out.bell[h[0]]=stat(b);});
function touch(price,target,stop,days,bell){var tf=0,sf=0,no=0,tt=0,ab=0,run,d,p,j,st,hit,drift=mu/252-sd2*sd2/2;
for(run=0;run<RUNS;run++){p=price;hit=0;var touched=false;d=0;while(d<days){st=Math.floor(rr()*nb);for(j=0;j<21&&d<days;j++,d++){p*=bell?Math.exp(drift+sd2*gauss(rr)):1+rc[st+j];
if(!hit){if(stop&&p<=stop)hit=2;else if(p>=target)hit=1;}if(p>=target)touched=true;}}
if(hit===1)tf++;else if(hit===2)sf++;else no++;if(touched)tt++;if(p>=target)ab++;}
return {target_first:tf/RUNS,stop_first:sf/RUNS,neither:no/RUNS,touch_target:tt/RUNS,above_on_date:ab/RUNS};}
(plans||[]).forEach(function(pl){if(pl&&pl.src)out[pl.name]={days:pl.src.days,kind:pl.src.kind,target:pl.src.target,stop:pl.src.stop,by:pl.src.by,entry:pl.src.entry,stop_name:pl.src.stop_name,
boot:touch(pl.price,pl.src.target,pl.src.stop,pl.src.days,false),bell:touch(pl.price,pl.src.target,pl.src.stop,pl.src.days,true)};});
return out;}
var EDIT={};
function ed(key,it){if(!EDIT[key])EDIT[key]={mu:(100*it.assume.mu).toFixed(1),vol:(100*it.assume.vol).toFixed(1),yrs:String(Math.min(15,it.assume.years))};return EDIT[key];}

/* ---------- outcome ranges ---------- */
function rTable(b){return '<div class="ox"><table class="mt p3w"><tr><th>After</th><th>Bad case (1 in 10 worse)</th><th>Typical (median)</th><th>Good case (1 in 10 better)</th><th>Chance of a loss</th></tr>'+
HZ.map(function(h){var s=b[h[0]];return s?"<tr><td>"+h[1]+"</td><td>"+sg(s.lo,0)+"</td><td><b>"+sg(s.med)+"</b></td><td>"+sg(s.hi,0)+"</td><td>"+p0(s.loss)+"</td></tr>":"";}).join("")+"</table></div>";}
function planText(pl,price){if(!pl||!pl.boot)return "";var b=pl.boot,g=pl.bell||{};
if(pl.kind==="keep")return para("Target and stop.","Target <b>"+usd(pl.target)+"</b> by "+esc(dl(pl.by))+(pl.stop?", stop at "+esc(pl.stop_name||"the stop")+" (<b>"+usd(pl.stop)+"</b>)":"")+". In 100 simulated futures the target is touched "+(pl.stop?"before the stop in <b>"+of100(b.target_first)+"</b>, the stop comes first in <b>"+of100(b.stop_first)+"</b>, neither happens in "+of100(b.neither):"in <b>"+of100(b.touch_target)+"</b>")+
". The price is above the target on the review date itself in <b>"+of100(b.above_on_date)+"</b>. A plain bell curve gives "+of100(g.target_first)+" and "+of100(g.above_on_date)+".");
return para("Target against stop.","From the entry at "+usd(pl.entry)+": in 100 simulated futures over one year the take-profit ("+usd(pl.target)+") is reached first in <b>"+of100(b.target_first)+"</b>, the stop ("+usd(pl.stop)+") first in <b>"+of100(b.stop_first)+"</b>, neither in "+of100(b.neither)+". A plain bell curve gives "+of100(g.target_first)+" and "+of100(g.stop_first)+".");}
function rangeBlock(key){var r=R(),it=r&&r.items[key];if(!it)return "";var e=ed(key,it),res=e.res||it,a=it.assume,h="";
h+=rTable(res.boot);
h+=para(e.res?"Your assumptions.":"Assumptions.","Average return <b>"+(e.res?esc(e.mu)+"%":p1(a.mu))+"</b> a year"+(e.res?"":" ("+esc(a.mu_note)+")")+"; volatility <b>"+p1(e.res?res.vol:a.vol)+"</b> a year; history used: <b>"+(e.res?res.used.toFixed(1):a.years)+" years</b>"+(e.res?"":" ("+esc(dl(a.from))+" to "+esc(dl(a.to))+")")+". Its own history averaged "+sg(a.hist_mu)+" a year; past averages rarely repeat, so the cautious figure is the starting point."+(it.note?" "+esc(it.note):""));
var b1=res.boot["1y"],g1=res.bell["1y"],diff=e.res?(Math.abs(b1.lo-g1.lo)>0.05||Math.abs(b1.loss-g1.loss)>0.05):it.differ;
h+=diff?para("History against a bell curve: they differ.","The table above draws from real history. A bell curve with the same average and volatility gives:")+rTable(res.bell):
para("History against a bell curve.","Nearly the same here: over one year the bad case is "+sg(b1.lo,0)+" from history and "+sg(g1.lo,0)+" from a bell curve. The table uses history, which keeps the large moves and the bad runs.");
h+=planText(res.plan||it.plan)+planText(res.card_plan||it.card_plan);
h+=para("Why median, not average.",esc(r.median_note));
h+='<div class="p6f"><label>Average return, % a year<input data-hold="1" data-p6="mu" data-k="'+esc(key)+'" inputmode="decimal" value="'+esc(e.mu)+'"></label><label>Volatility, % a year<input data-hold="1" data-p6="vol" data-k="'+esc(key)+'" inputmode="decimal" value="'+esc(e.vol)+'"></label><label>Years of history (up to 15)<input data-hold="1" data-p6="yrs" data-k="'+esc(key)+'" inputmode="decimal" value="'+esc(e.yrs)+'"></label></div>'+
'<div class="gap"><button class="btn sm" data-p6="run" data-k="'+esc(key)+'">Run 10,000 futures with these</button>'+(e.res?' <button class="btn sm" data-p6="reset" data-k="'+esc(key)+'">Back to the engine\'s figures</button>':"")+'</div><div class="src" id="p6s-'+esc(key)+'">'+esc(e.msg||"Change a number and run it again: the range moves. Simulated outcomes are evidence about the size of the risk, not a forecast.")+"</div>";
return h;}
function rangeLine(key){var r=R(),it=r&&r.items[key];if(!it)return "";var s=it.boot["1y"];return "after one year typically <b>"+sg(s.med)+"</b>, bad case "+sg(s.lo,0)+", good case "+sg(s.hi,0)+"; a loss in "+of100(s.loss)+" of 100 simulated futures";}
function runSim(key){var r=R(),it=r&&r.items[key];if(!it)return;var e=ed(key,it),mu=num(e.mu),vol=num(e.vol),yrs=num(e.yrs),st=$("p6s-"+key);
if(mu==null||vol==null||yrs==null||vol<=0||vol>300||mu<-90||mu>200||yrs<1){e.msg="Enter a return between -90 and 200, a volatility above 0 and at least one year.";M.render();return;}
if(st)st.textContent="Running 10,000 futures...";
MC.get("state/paths/"+key.replace(/[^A-Za-z0-9_]/g,"_")+".json").then(function(p){if(!p||!p.r||p.r.length<300)throw new Error("no path");
var arr=new Float64Array(p.r.length),i;for(i=0;i<p.r.length;i++)arr[i]=p.r[i]/10000;
var plans=[];if(it.plan)plans.push({name:"plan",src:it.plan,price:it.price});if(it.card_plan)plans.push({name:"card_plan",src:it.card_plan,price:it.card_plan.entry||it.price});
e.res=simulate(arr,mu/100,vol/100,Math.min(yrs,15),plans);e.msg="Run with your numbers on "+e.res.used.toFixed(1)+" years of history ("+esc(dl(p.from))+" to "+esc(dl(p.to))+").";M.render();render();})
.catch(function(){e.msg="The price history for this simulation has not been published yet; it appears after the next nightly run.";M.render();render();});}

/* ---------- options: three ways to price, and the Greeks ---------- */
function ncdf(x){var t=1/(1+0.2316419*Math.abs(x)),d=0.3989422804014327*Math.exp(-x*x/2),p=d*t*(0.319381530+t*(-0.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return x>=0?1-p:p;}
function npdf(x){return Math.exp(-x*x/2)/Math.sqrt(2*Math.PI);}
function bs(S,K,T,r,v,call){if(T<=0||v<=0)return Math.max(0,call?S-K:K-S);var d1=(Math.log(S/K)+(r+v*v/2)*T)/(v*Math.sqrt(T)),d2=d1-v*Math.sqrt(T);return call?S*ncdf(d1)-K*Math.exp(-r*T)*ncdf(d2):K*Math.exp(-r*T)*ncdf(-d2)-S*ncdf(-d1);}
function greeks(S,K,T,r,v,call){var d1=(Math.log(S/K)+(r+v*v/2)*T)/(v*Math.sqrt(T)),d2=d1-v*Math.sqrt(T);
return {delta:call?ncdf(d1):ncdf(d1)-1,gamma:npdf(d1)/(S*v*Math.sqrt(T)),vega:S*npdf(d1)*Math.sqrt(T)/100,theta:(-S*npdf(d1)*v/(2*Math.sqrt(T))-(call?r*K*Math.exp(-r*T)*ncdf(d2):-r*K*Math.exp(-r*T)*ncdf(-d2)))/365,rho:(call?K*T*Math.exp(-r*T)*ncdf(d2):-K*T*Math.exp(-r*T)*ncdf(-d2))/100};}
function binom(S,K,T,r,v,call){var n=200,dt=T/n,u=Math.exp(v*Math.sqrt(dt)),d=1/u,disc=Math.exp(-r*dt),p=(Math.exp(r*dt)-d)/(u-d),val=new Float64Array(n+1),i,j,px;
for(j=0;j<=n;j++){px=S*Math.pow(u,n-j)*Math.pow(d,j);val[j]=Math.max(0,call?px-K:K-px);}
for(i=n-1;i>=0;i--)for(j=0;j<=i;j++){px=S*Math.pow(u,i-j)*Math.pow(d,j);val[j]=Math.max(disc*(p*val[j]+(1-p)*val[j+1]),call?px-K:K-px);}return val[0];}
function mcOpt(S,K,T,r,v,call){var rr=rnd32(20261012),n=20000,s=0,i,z,a,b,dr=(r-v*v/2)*T,sq=v*Math.sqrt(T),df=Math.exp(-r*T);
for(i=0;i<n;i++){z=gauss(rr);a=S*Math.exp(dr+sq*z);b=S*Math.exp(dr-sq*z);s+=Math.max(0,call?a-K:K-a)+Math.max(0,call?b-K:K-b);}return df*s/(2*n);}
var OC=null;
function ocInit(t){var o=M.X.opt,sh=o&&o.shares&&o.shares[t],ex=sh&&sh.example;if(!ex)return null;return {t:t,type:ex.type,S:String(ex.spot),K:String(ex.strike),days:String(ex.days),vol:(100*ex.vol).toFixed(1),rate:(100*ex.rate).toFixed(2)};}
function ocOut(){var c=OC;if(!c)return "";var S=num(c.S),K=num(c.K),d=num(c.days),v=num(c.vol),r=num(c.rate),call=c.type==="C";
if(!(S>0&&K>0&&d>0&&v>0&&r!=null))return '<div class="fl" style="font-size:12px">Fill in a share price, a strike, the days left and a volatility above zero.</div>';
var T=d/365,vv=v/100,rr=r/100,g=greeks(S,K,T,rr,vv,call),a=bs(S,K,T,rr,vv,call),b=binom(S,K,T,rr,vv,call),m=mcOpt(S,K,T,rr,vv,call);
return '<div class="ox"><table class="mt p3w"><tr><th>Method</th><th>Fair price of the '+(call?"call":"put")+'</th></tr><tr><td>Black-Scholes formula</td><td><b>'+usd(a,3)+'</b></td></tr><tr><td>Binomial tree, 200 steps</td><td><b>'+usd(b,3)+'</b></td></tr><tr><td>Monte Carlo, 40,000 prices</td><td><b>'+usd(m,3)+"</b></td></tr></table></div>"+
'<div class="src">One contract covers 100 shares, so multiply by 100. The three agree to within a few cents when the inputs are the same; the tree is a little higher for puts because it allows using the option early.</div>'+
[["Delta",g.delta.toFixed(3),"How much the option's price moves when the share moves $1."],["Gamma",g.gamma.toFixed(4),"How much delta itself changes when the share moves $1: high gamma means the option's behaviour shifts quickly."],
["Vega",usd(g.vega,3),"How much the price changes when expected volatility rises by one percentage point."],["Theta",usd(g.theta,3)+" a day","How much value the option loses each day just from time passing."],
["Rho",usd(g.rho,3),"How much the price changes when interest rates rise by one percentage point."]].map(function(x){return '<div class="p6g"><span><b>'+x[0]+'</b></span><span><b>'+x[1]+'</b></span><span class="x">'+x[2]+"</span></div>";}).join("");}
function optBlock(){var o=M.X.opt;if(!o||!o.shares)return '<div class="fl" style="font-size:12px">Option quotes have not been published yet.</div>';var ts=Object.keys(o.shares).sort();if(!ts.length)return '<div class="fl" style="font-size:12px">No option quotes loaded in the last run.</div>';
if(!OC||!o.shares[OC.t])OC=ocInit(ts[0]);var sh=o.shares[OC.t],ex=sh.example,h="";
h+=para("In plain words.","A <b>call</b> is the right to buy a share at a fixed price (the <b>strike</b>) until a set date; a <b>put</b> is the right to sell at it. The price of that right depends on five things: the share price, the strike, the time left, interest rates and how much the share is expected to move (<b>volatility</b>).");
h+='<div class="p6f"><label>Share<select data-hold="1" data-p6o="t">'+ts.map(function(t){return '<option'+(t===OC.t?" selected":"")+">"+esc(t)+"</option>";}).join("")+'</select></label><label>Kind<select data-hold="1" data-p6o="type"><option value="C"'+(OC.type==="C"?" selected":"")+'>Call</option><option value="P"'+(OC.type==="P"?" selected":"")+'>Put</option></select></label><label>Share price, $<input data-hold="1" data-p6o="S" inputmode="decimal" value="'+esc(OC.S)+'"></label></div>'+
'<div class="p6f"><label>Strike, $<input data-hold="1" data-p6o="K" inputmode="decimal" value="'+esc(OC.K)+'"></label><label>Days left<input data-hold="1" data-p6o="days" inputmode="decimal" value="'+esc(OC.days)+'"></label><label>Volatility, % a year<input data-hold="1" data-p6o="vol" inputmode="decimal" value="'+esc(OC.vol)+'"></label><label>Interest rate, %<input data-hold="1" data-p6o="rate" inputmode="decimal" value="'+esc(OC.rate)+'"></label></div>';
h+='<div id="p6-oc">'+ocOut()+"</div>";
if(ex)h+=para("Checked against the market.",esc(OC.t)+" "+(ex.type==="C"?"call":"put")+", strike "+usd(ex.strike)+", "+ex.days+" days ("+esc(dl(ex.exp))+"): market price "+usd(ex.market_mid)+" (middle of bid and ask). At the volatility that price implies ("+p1(ex.vol)+") the engine gets Black-Scholes "+usd(ex.black_scholes,3)+", binomial "+usd(ex.binomial,3)+", Monte Carlo "+usd(ex.monte_carlo,3)+" (give or take "+usd(ex.monte_carlo_error,3)+")."+(ex.at_past_vol!=null?" At the share's actual volatility over the past year it would be worth "+usd(ex.at_past_vol,3)+".":""));
if(sh.reading)h+=para("Implied against actual volatility.",esc(sh.reading)+" Implied volatility is the volatility that makes the formula match the market price: the market's own guess at how much the share will move.");
h+=det("Market quotes for "+esc(OC.t),'<div class="ox"><table class="mt p3w"><tr><th>Expires</th><th>Option</th><th>Bid / ask</th><th>Implied volatility</th><th>Ask as % of share price</th></tr>'+(sh.rows||[]).map(function(x){return "<tr><td>"+esc(dl(x.exp))+'<span class="p5s">'+x.days+" days</span></td><td>"+esc(x.tag)+'<span class="p5s">strike '+usd(x.strike)+"</span></td><td>"+usd(x.bid)+" / "+usd(x.ask)+"</td><td>"+p1(x.iv)+"</td><td>"+p1(x.pct_of_price)+"</td></tr>";}).join("")+"</table></div>"+
'<div class="src">'+esc(o.source||"")+" Quotes from "+esc(sh.quote_at||"")+" (UTC).</div>");
return h+'<div class="src">'+esc(o.method||"")+" "+esc(o.note||"")+"</div>";}
function protectBlock(t){var o=M.X.opt,sh=o&&o.shares&&o.shares[t];if(!sh||!(sh.protect||[]).length)return "";
return M.blk("COST OF PROTECTION",'<span class="stg paper">INFORMATION ONLY</span>',para("What a put would cost today.","A put lets you sell at a fixed price whatever happens, so it puts a floor under the position for as long as it lasts.")+
sh.protect.map(function(p){return '<div class="p6g"><span><b>About '+Math.round(p.days/30.4)+" months</b>, "+esc(p.tag)+'</span><span><b>'+usd(p.price)+"</b> a share</span><span class=\"x\">Strike "+usd(p.strike)+", expires "+esc(dl(p.exp))+" ("+p.days+" days). That is <b>"+p1(p.pct)+"</b> of the position's value, paid up front and gone if the price does not fall.</span></div>";}).join("")+
(sh.reading?para("Is protection dear right now?",esc(sh.reading)):""),"One contract covers 100 shares; with fewer shares one contract over-protects. Your broker does not offer options, so this is a price tag, not a suggestion. "+esc(o.source||""));}

/* ---------- what the order costs ---------- */
function costBlock(c){var k=c.cost;if(!k)return "";
return '<div class="lbl" style="margin-top:10px">What the order itself costs</div>'+M.kv("Typical spread",k.spread==null?"not read in trading hours yet"+(k.off_hours_spread!=null?" (outside hours: "+(100*k.off_hours_spread).toFixed(2)+"%)":""):(k.spread<0.00005?"under 0.01%":(100*k.spread).toFixed(2)+"%")+(k.bid?" (bid "+usd(k.bid)+", ask "+usd(k.ask)+")":""))+
(k.adv_usd?M.kv("Traded on an average day",big(k.adv_usd)):"")+
'<div class="ox"><table class="mt p3w"><tr><th>Amount</th><th>Market order gives up about</th><th>Limit order</th><th>Share of a day\'s trading</th></tr>'+(k.rows||[]).map(function(r){return "<tr><td>"+usd(r.usd,0)+"</td><td>"+(r.market_usd==null?"not known yet":usd(r.market_usd))+"</td><td>$0.00 if it fills</td><td>"+(r.pct_of_volume==null?DASH:(r.pct_of_volume<0.000005?"under 0.001%":(100*r.pct_of_volume).toFixed(3)+"%"))+"</td></tr>";}).join("")+"</table></div>"+
(k.thin?'<div class="p5w"><b>Thinly traded.</b> '+esc(k.order)+"</div>":para("Order type.",esc(k.order)))+'<div class="src">'+esc(k.note||"")+" Broker fees are separate and are in the table above. Estimate.</div>";}

/* ---------- on a card: costs, outcome range, learned signal ---------- */
var prevCard=M.cardExtra;
M.cardExtra=function(c){var h=prevCard?prevCard(c):"";if(!c||c.kind==="test")return h;var t=c.ticker,r=R(),L=M.X.learn;
h+=costBlock(c);
if(t&&r&&r.items[t]){var it=r.items[t];h+='<div class="q"><b style="color:var(--tx)">Outcome range (10,000 simulated futures):</b> '+rangeLine(t)+"."+(it.card_plan?" The take-profit comes before the stop in <b>"+of100(it.card_plan.boot.target_first)+"</b> of 100, the stop first in <b>"+of100(it.card_plan.boot.stop_first)+"</b>.":"")+' <span style="color:var(--dim)">Evidence, not a forecast.</span></div>'+det("See the range and change the assumptions",rangeBlock(t));}
if(t&&L&&L.today&&L.today[t])h+='<div class="q"><b style="color:var(--tx)">Learned signal (on paper, not counted in the score):</b> ranks '+(L.today[t].percentile<=0.5?"in the top "+Math.max(1,Math.round(100*L.today[t].percentile))+"%":"in the bottom "+Math.max(1,Math.round(100*(1-L.today[t].percentile)))+"%")+" of the screened shares by predicted next-month return. "+'<button class="btn sm" data-tab="quant" style="margin-top:6px">How it was tested</button></div>';
return h;};

/* ---------- position panel and risk screen ---------- */
var prevHold=M.slots["pp-hold"];
M.slots["pp-hold"]=function(t){var top=prevHold?prevHold(t):"",r=R();if(r&&r.items[t])top+=M.blk("OUTCOME RANGE",'<span class="stg paper">SIMULATION</span>',rangeBlock(t),esc(r.honesty||""));return top+protectBlock(t);};
var prevRk=M.slots["rk-extra"];
M.slots["rk-extra"]=function(){var top=prevRk?prevRk():"",r=R();if(!r||!r.items.PORT)return top;return top+M.blk("PORTFOLIO OUTCOME RANGE",'<span class="stg paper">SIMULATION</span>',rangeBlock("PORT"),esc(r.method||""));};

/* ---------- pairs ---------- */
function pairCard(p){function col(s){return s&&s.n?nn(s.n)+" trades, "+sg(s.avg)+" each, "+p0(s.win)+" winners, "+sg(s.total)+" in all":"no trades";}
return '<div class="p5k"><div class="p5h">'+esc(p.a)+" and "+esc(p.b)+" "+(p.fails?'<span class="p5t">FAILS OUT OF SAMPLE</span>':'<span class="p5t ok">HELD UP</span>')+(p.few?' <span class="p5t">TOO FEW CASES</span>':"")+'</div>'+
'<div class="ox"><table class="mt p3w"><tr><th></th><th>First six years (fitted)</th><th>Last four years (unseen)</th></tr><tr><td>After costs</td><td>'+col(p.in_sample)+"</td><td>"+col(p.unseen)+"</td></tr></table></div>"+
para("The spread today.",(p.z_now>0?"+":MINUS)+Math.abs(Number(p.z_now)).toFixed(1)+" standard deviations from its average; over the ten years it was nearer the average than this "+p0(p.z_percentile)+" of the time. "+esc(p.signal.charAt(0).toUpperCase()+p.signal.slice(1))+".")+
'<div class="src">'+esc(p.sector)+" "+MID+" for every $1 of "+esc(p.a)+", $"+Number(p.hedge).toFixed(2)+" of "+esc(p.b)+" "+MID+" pulls halfway back in about "+nn(p.half_life_days)+" trading days "+MID+" test statistic "+Number(p.adf).toFixed(2)+" (below "+MINUS+"3.37 passes)</div></div>";}
function pairsBlock(){var p=M.X.pairs;if(!p||!p.window)return '<div class="fl" style="font-size:12px">The pairs scan has not been published yet.</div>';var w=p.window,h="";
h+='<div class="p5w"><b>Read this first.</b> '+esc(p.note||"")+"</div>";
h+=para("What a pair is.","Two shares whose prices are tied together, so the gap between them (the <b>spread</b>) keeps returning to its average. <b>Cointegration</b> is the statistical test for that tie; it is stricter than correlation, which only says two shares tend to move on the same days.");
h+=para("The honest count.","<b>"+nn(p.tested)+"</b> same-sector pairs tested on "+esc(dl(w.from))+" to "+esc(dl(w.split))+". <b>"+nn(p.passed_fit)+"</b> passed and made money there. Traded on the four years the fit never saw ("+esc(dl(w.split))+" to "+esc(dl(w.to))+"), only <b>"+nn(p.held_up)+"</b> still made money. Across all of them: "+nn(p.unseen_trades)+" unseen trades, "+sg(p.unseen_avg)+" each after costs, "+p0(p.unseen_win)+" winners.");
h+='<div class="lbl" style="margin-top:10px">The best three by the first-part test</div>'+(p.best||[]).map(pairCard).join("");
if((p.mine||[]).length)h+=det("Pairs that include a share you watch ("+p.mine.length+")",p.mine.map(pairCard).join(""));
if((p.more||[]).length)h+=det("The next "+p.more.length,p.more.map(pairCard).join(""));
return h+para("The rule.",esc(p.rule||""))+'<div class="src">'+esc(p.method||"")+"</div>";}

/* ---------- the learned signal ---------- */
function learnBlock(){var l=M.X.learn;if(!l)return '<div class="fl" style="font-size:12px">The learned signal has not been published yet.</div>';if(l.status!=="ok")return '<div class="fl" style="font-size:12px">Not enough history yet for a walk-forward test.</div>';var u=l.unseen,h="";
h+=para("What it is.","A simple model that looks at nine numbers the engine already computes for every share and predicts which shares will do best next month. <b>Walk-forward</b> means it is only ever judged on months it had not seen when it was fitted.");
h+=(l.overfit?'<div class="p5w"><b>Overfitting warning.</b> '+esc(l.overfit_note)+"</div>":para("Overfitting check.",esc(l.overfit_note)));
h+='<div class="ox"><table class="mt p3w"><tr><th>On unseen months, '+esc(u.from)+" to "+esc(u.to)+'</th><th>A year, after costs</th></tr><tr><td>Model: top fifth by prediction</td><td><b>'+sg(u.model)+"</b></td></tr><tr><td>Plain score: 3 or 4 of the 4 rebuildable checks<span class='p5s'>exists from 2009, when the earnings history starts</span></td><td><b>"+sg(u.score)+'</b><span class="p5s">the model over those same months: '+sg(u.model_same_months)+"</span></td></tr><tr><td>The average share in the list</td><td><b>"+sg(u.all)+"</b></td></tr><tr><td>S&amp;P 500 fund</td><td><b>"+sg(u.spy)+"</b></td></tr></table></div>";
h+=para("Verdict.",esc(l.verdict)+" It beat the average share in "+p0(u.beat_all_months)+" of "+nn(u.months)+" months.")+para("The Council\'s view.","Do not promote it yet. The model leans most on shares that have fallen far from their high and on volatile shares, and a list made only of companies that survived flatters exactly those. Let it run on paper beside the daily seven-check log for some months, then compare the two on what really followed.")+'<div class="p5w"><b>Read this first.</b> '+esc(l.caveat)+"</div>";
h+=det("The walk-forward table, year by year",'<div class="ox"><table class="mt p3w"><tr><th>Year</th><th>Model</th><th>Plain score</th><th>Average share</th><th>S&amp;P 500</th></tr>'+(l.table||[]).map(function(r){return "<tr><td>"+esc(r.year)+(r.months<12?'<span class="p5s">'+r.months+" months</span>":"")+"</td><td>"+sg(r.model,0)+"</td><td>"+sg(r.score,0)+"</td><td>"+sg(r.all,0)+"</td><td>"+sg(r.spy,0)+"</td></tr>";}).join("")+"</table></div>");
h+=det("Which inputs matter most",(l.importance||[]).map(function(x,i){return '<div class="p6g"><span><b>'+(i+1)+". "+esc(x.name)+'</b></span><span>'+esc(x.direction)+'</span><span class="x">weight '+Number(x.weight).toFixed(4)+"</span></div>";}).join("")+'<div class="src">A larger weight means the model leans on that input more. The heaviest inputs here favour shares that have fallen far from their high and volatile shares, which is where missing failed companies would flatter the result most.</div>');
var ts=Object.keys(l.today||{}).sort(function(a,b){return l.today[a].percentile-l.today[b].percentile;});
if(ts.length)h+=det("Today's reading for your shares",ts.map(function(t){var x=l.today[t];return M.kv("<b>"+esc(t)+"</b>",(x.percentile<=0.5?"top "+Math.max(1,Math.round(100*x.percentile))+"%":"bottom "+Math.max(1,Math.round(100*(1-x.percentile)))+"%")+(x.top?" "+MID+" would pass":""));}).join("")+'<div class="src">Rank among the screened shares by predicted next-month return. Top fifth would count as a pass if it were ever promoted.</div>');
return h+'<div class="gap"><button class="btn sm" data-mc="askq" data-q="Learned signal: ">Tell the Council whether to promote it</button></div><div class="src">'+esc(l.method||"")+"</div>";}

/* ---------- the QUANT page ---------- */
function html(){var r=R(),h="";
h+=M.blk("QUANT LAB",'<span class="stg paper">ON PAPER</span>','<div style="font-size:12.5px;white-space:normal">Four tools that put numbers on risk and test ideas properly. None of them changes a real decision card: each has to prove itself first, and you decide.</div>',"Past and simulated results are evidence, not forecasts. You place every order yourself.");
h+=M.blk("OUTCOME RANGES",'<span class="stg paper">SIMULATION</span>',r?(r.items.PORT?'<div class="p5h">Your portfolio</div>'+rangeBlock("PORT"):"")+Object.keys(r.items).filter(function(k){return k!=="PORT";}).sort().map(function(k){return det(esc(k)+" "+MID+" "+rangeLine(k).replace(/<[^>]+>/g,""),rangeBlock(k));}).join(""):'<div class="fl" style="font-size:12px">The outcome ranges have not been published yet.</div>',r?esc(r.method):"");
h+=M.blk("OPTIONS CALCULATOR",'<span class="stg paper">INFORMATION ONLY</span>',optBlock(),"");
h+=M.blk("PAIRS",'<span class="stg paper">PAPER ONLY</span>',pairsBlock(),"");
h+=M.blk("LEARNED SIGNAL",'<span class="stg paper">ON PAPER</span>',learnBlock(),"");
return h;}
function render(){var el=$("v-quant");if(!el)return;var ae=document.activeElement;if(ae&&ae.getAttribute&&ae.getAttribute("data-hold")&&el.contains(ae))return;
var h=html();if(el.__h!==h){var open={};Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){if(d.open)open[i]=1;});var had=el.__h!=null;el.innerHTML=h;el.__h=h;
if(had)Array.prototype.forEach.call(el.querySelectorAll("details"),function(d,i){d.open=!!open[i];});}}
document.addEventListener("input",function(e){var t=e.target;if(!t||!t.dataset)return;
if(t.dataset.p6&&t.dataset.k){var r=R(),it=r&&r.items[t.dataset.k];if(it)ed(t.dataset.k,it)[t.dataset.p6]=t.value;}
else if(t.dataset.p6o&&OC){if(t.dataset.p6o==="t"){OC=ocInit(t.value)||OC;t.blur();render();return;}OC[t.dataset.p6o]=t.value;var o=$("p6-oc");if(o)o.innerHTML=ocOut();}});
document.addEventListener("change",function(e){var t=e.target;if(t&&t.dataset&&t.dataset.p6o==="type"&&OC){OC.type=t.value;var o=$("p6-oc");if(o)o.innerHTML=ocOut();}});
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p6]"):null;if(!b||b.tagName!=="BUTTON")return;
if(b.dataset.p6==="run")runSim(b.dataset.k);else if(b.dataset.p6==="reset"){delete EDIT[b.dataset.k];M.render();render();}});
var prevRs=M.slots["rs-extra"];
M.slots["rs-extra"]=function(){setTimeout(render,0);var top=prevRs?prevRs():"";
return top+M.blk("QUANT LAB",'<span class="stg paper">ON PAPER</span>','<div style="font-size:12.5px;white-space:normal">Outcome ranges by simulation, an options calculator, pairs tested on unseen years and a learned signal.</div><div class="gap"><button class="btn sm" data-tab="quant">Open the quant lab</button></div>',"Evidence, not forecasts.");};
MC.hooks.push(render);
M.reload();
})();
