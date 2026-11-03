/* Market Council add-on 16: EARNINGS (Research > Earnings) and the earnings card on TODAY. Before each call of a share
   you hold or watch: what the company is likely to report, how the share may react, and what it means for your
   position; after the call: the result, the read of the transcript and the drift. Every figure is counted by plain
   code (ops/engine/earnings.py, state/earnings.json); estimates, never promises. Nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.earn="state/earnings.json";
var DASH=String.fromCharCode(8212),DOT=" "+String.fromCharCode(183)+" ",open={};
function pc(v,d){return v==null?DASH:(Math.round(1000*v)/10).toFixed(d==null?1:d)+"%";}
function sp(v){return v==null?DASH:(v>=0?"+":"")+(Math.round(1000*v)/10).toFixed(1)+"%";}
function money(v){return v==null?DASH:(v<0?"-":"")+"$"+Math.abs(Number(v)).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});}
function when(c){return esc(c.date)+" "+(c.time==="bmo"?"before the open":c.time==="amc"?"after the close":"time not known");}
function p(t){return '<p style="font-size:13px;line-height:1.5;white-space:normal;margin:5px 0">'+t+'</p>';}
function small(t){return '<div style="font-size:12px;color:var(--dim);white-space:normal;margin:3px 0">'+t+'</div>';}
function head(t){return '<div class="fl" style="margin-top:10px;font-weight:800;font-size:11px;letter-spacing:.06em">'+esc(t)+'</div>';}
function few(x){return x?' <span class="stg stale" style="font-size:10px">TOO FEW CASES</span>':"";}
function cal(e){
  var rows=(e.calendar||[]).map(function(c){var q=(e.predictions||{})[c.ticker]||{},o=q.overall||{},eps=q.eps||{};
    return '<tr><td><b>'+esc(c.ticker)+'</b>'+(q.position?' <span class="stg live" style="font-size:10px">HELD</span>':"")+'<br><span style="color:var(--dim)">'+when(c)+'</span></td>'+
      '<td class="r mono">'+pc(eps.p_beat,0)+'</td><td class="r mono">'+pc(o.p_up_next_day,0)+'</td><td class="r mono">'+(q.implied_move!=null?String.fromCharCode(177)+pc(q.implied_move):DASH)+'</td>'+
      '<td>'+(c.sources_agree===true?"2 sources agree":c.sources_agree===false?'<span style="color:var(--wn)">sources differ ('+esc(c.second_source)+')</span>':"1 source")+'</td></tr>';}).join("");
  return M.blk("EARNINGS: NEXT 30 DAYS","",(rows?'<div class="tw"><table><thead><tr><th>Share</th><th class="r">Beat EPS</th><th class="r">Up next day</th><th class="r">Options expect</th><th>Date check</th></tr></thead><tbody>'+rows+'</tbody></table></div>':p("No call of your shares in the next 30 days.")),
    "Dates from Nasdaq's calendar, checked against the pipeline's Twelve Data date. "+esc(e.honesty||""));
}
function scen(q){
  var r=(q.scenarios||[]).map(function(s){var n=s.next_day||{},f=s.five_days||{};
    return '<tr><td>'+esc(s.words)+few(s.few)+'</td><td class="r mono">'+pc(s.chance,0)+'</td><td class="r mono">'+sp(n.p10)+" to "+sp(n.p90)+'<br><span style="color:var(--dim)">middle '+sp(n.median)+'</span></td><td class="r mono">'+sp(f.p10)+" to "+sp(f.p90)+'</td><td class="r">'+s.own_cases+"+"+s.pool_cases+'</td></tr>';}).join("");
  return '<div class="tw"><table><thead><tr><th>If it</th><th class="r">Chance</th><th class="r">Next day</th><th class="r">After 5 days</th><th class="r">Cases</th></tr></thead><tbody>'+r+'</tbody></table></div>'+
    small("Cases: this share's own calls + other shares' calls. Beat and raise against beat with weak guidance cannot be told apart yet: guidance is recorded from each call's transcript from now on.");
}
function pos(x){if(!x)return "";
  var h=head("YOUR POSITION THROUGH THE CALL")+p("You hold "+esc(String(x.shares))+" shares worth "+money(x.value)+".");
  if(x.stop!=null)h+=p("Order-plan stop "+money(x.stop)+" ("+sp(x.stop_gap)+"): chance of a next-day close under it "+(x.p_below_stop_words||pc(x.p_below_stop,0))+". "+esc(x.stop_jump||""));
  h+='<div class="tw"><table><thead><tr><th>Before the call</th><th class="r">Middle case</th><th class="r">Worst 10%</th><th class="r">Best 10%</th><th class="r">Cost</th></tr></thead><tbody>'+
    (x.choices||[]).map(function(c){return '<tr><td>'+esc(c.choice)+'</td><td class="r mono">'+money(c.expected_next_day)+'</td><td class="r mono">'+money(c.worst_10)+'</td><td class="r mono">'+money(c.best_10)+'</td><td class="r mono">'+money(c.cost)+'</td></tr>';}).join("")+'</tbody></table></div>';
  if(x.note)h+=small(esc(x.note));
  return h;}
function pred(t,q){
  var c=q.call||{},e=q.eps||{},r=q.revenue||{},g=q.guidance||{},d=q.drivers||{},pr=q.past_reactions||{},o=q.overall||{},n=o.next_day||{},b=open[t];
  var h=p("<b>"+esc(t)+"</b> reports "+when(c)+". EPS consensus "+(e.consensus!=null?"$"+e.consensus:DASH)+(e.analysts?" ("+e.analysts+" analysts)":"")+"; our estimate "+(e.ours!=null?"$"+e.ours:DASH)+". "+
    "Chance to beat "+pc(e.p_beat,0)+", in line "+pc(e.p_inline,0)+", miss "+pc(e.p_miss,0)+". Up the next day: "+pc(o.p_up_next_day,0)+", likely range "+sp(n.p10)+" to "+sp(n.p90)+
    (q.implied_move!=null?"; the options market expects "+String.fromCharCode(177)+pc(q.implied_move)+" (options to "+esc(q.implied_expiry||DASH)+"), chance of a bigger move "+pc(o.p_bigger_than_implied,0):"")+"."+few(q.few));
  h+='<div class="gap"><button class="btn sm" data-p16="'+esc(t)+'">'+(b?"Less":"The full prediction")+'</button></div>';
  if(b){
    h+=head("WHAT WILL THEY REPORT?")+p("Our EPS estimate: "+esc(e.ours_method||""))+
      p("Revenue: "+(r.consensus?"consensus $"+(r.consensus/1e9).toFixed(2)+"bn ("+esc(r.source||"")+"), chance to beat "+pc(r.p_beat,0)+few(r.few):esc(r.note||"")))+
      p("Guidance: "+(g.cases?"raised "+pc(g.p_raised,0)+", kept "+pc(g.p_kept,0)+", cut "+pc(g.p_cut,0)+few(g.few):esc(g.note||"")))+
      p("Most likely to move the share: "+((d.items||[]).length?(d.items||[]).map(function(x){return esc(typeof x==="string"?x:(x.what||x.text||""));}).join("; "):esc(d.note||"")));
    h+=head("HOW THE PRICE MAY REACT")+p("Its own last "+pr.cases+" calls: average move "+pc(pr.mean_abs_next_day)+" either way, from "+sp((pr.range_next_day||[])[0])+" to "+sp((pr.range_next_day||[])[1])+"; average five-day move "+sp(pr.mean_five_day)+".")+scen(q)+
      p("Overall: up the next day "+pc(o.p_up_next_day,0)+"; next-day range "+sp(n.p10)+" to "+sp(n.p90)+" (middle "+sp(n.median)+"); after five days "+sp((o.five_days||{}).p10)+" to "+sp((o.five_days||{}).p90)+".")+pos(q.position)+
      small(esc(q.method||""))+small(esc(q.honesty||""))+(q.logged?small("Logged as "+esc(q.logged)+": written once, never edited, scored after the call."):"");
  }
  return h;
}
function after(t,a){
  var d=a.drift||{},rd=a.read||{};
  var h=p("<b>"+esc(t)+"</b> reported "+esc(a.call_date)+": EPS "+(a.eps!=null?"$"+a.eps:DASH)+" against consensus "+(a.consensus!=null?"$"+a.consensus:DASH)+" ("+sp(a.surprise)+", "+esc(a.scenario||DASH)+")"+
    (a.predicted?"; our estimate was $"+a.our_estimate+" and the chance to beat "+pc(a.our_p_beat,0):"; no prediction was logged before this call")+". Next day "+sp(a.next_day)+", five days "+sp(a.five_days)+".");
  if(d.cases)h+=p("Drift: in "+d.cases+" similar past cases the share kept the first day's direction over the next five days "+pc(d.p_keeps_direction_5d,0)+" of the time; next 5 days "+sp((d.next_5_days||[])[0])+" to "+sp((d.next_5_days||[])[2])+", next 20 days "+sp((d.next_20_days||[])[0])+" to "+sp((d.next_20_days||[])[2])+"."+few(d.few));
  else if(d.note)h+=small(esc(d.note));
  if(rd.summary||(rd.points||[]).length){h+=p("<b>From the call:</b> "+esc(rd.summary||""));
    (rd.points||[]).slice(0,6).forEach(function(x){h+=small(esc(x.text||"")+(x.quote?" "+String.fromCharCode(8212)+" “"+esc(x.quote)+"”":""));});
    if(rd.guidance)h+=small("Guidance: "+esc(rd.guidance)+(rd.guidance_quote?" — “"+esc(rd.guidance_quote)+"”":""));
    if(rd.tone)h+=small("Tone against the previous call: "+esc(rd.tone));}
  else if(rd.note)h+=small(esc(rd.note));
  return h;
}
function scoreBlk(e){var s=e.score||{},b=e.backtest||{};
  function line(x){return x.calls?p(esc(x.verdict||"")+" Size-of-move error: ours "+pc(x.move_error_ours,2)+DOT+"options market "+pc(x.move_error_implied,2)+DOT+"own average "+pc(x.move_error_own_avg,2)+". Direction right "+pc(x.right_direction,0)+"; inside the 10-90% range "+pc(x.in_range_10_90,0)+"."):p(esc(x.verdict||"No call scored yet."));}
  var cal=(s.calibration||[]).map(function(c){return '<tr><td>'+esc(c.said)+'</td><td class="r">'+c.calls+'</td><td class="r mono">'+pc(c.said_avg,0)+'</td><td class="r mono">'+pc(c.happened,0)+'</td></tr>';}).join("");
  return M.blk("DO THE PREDICTIONS WORK?","",head("LIVE")+line(s)+(cal?'<div class="tw"><table><thead><tr><th>Said up</th><th class="r">Calls</th><th class="r">Said</th><th class="r">Happened</th></tr></thead><tbody>'+cal+'</tbody></table></div>':"")+
    head("BACK-TEST ON PAST CALLS")+line(b)+(b.note?small(esc(b.note)):""),"Rivals: (a) the options market's expected move, (b) the share's own average past reaction. Judged after 30 scored calls.");}
function html(){var e=M.X.earn;if(!e)return "";
  var ps=e.predictions||{},ks=Object.keys(ps).sort(function(a,b){return String(ps[a].call.date).localeCompare(String(ps[b].call.date));});
  var af=e.after||{},ka=Object.keys(af);
  return cal(e)+(ks.length?M.blk("BEFORE THE CALL","",ks.map(function(t){return pred(t,ps[t]);}).join('<hr style="border:0;border-top:1px solid var(--line);margin:10px 0">'),"Estimates, never promises."):"")+
    (ka.length?M.blk("AFTER THE CALL","",ka.map(function(t){return after(t,af[t]);}).join('<hr style="border:0;border-top:1px solid var(--line);margin:10px 0">'),"Results from Nasdaq; the read is by the Earnings Reader, with the lines it quotes."):"")+scoreBlk(e);}
function render(){var el=$("v-earnings");if(!el)return;var h=html()||'<div class="msg">The earnings predictions appear after the next engine run.</div>';if(el.__h!==h){el.innerHTML=h;el.__h=h;}paintToday();}
function paintToday(){var el=$("p16-host");if(!el)return;var e=M.X.earn,h="";
  if(e){var ps=e.predictions||{},soon=Object.keys(ps).filter(function(t){var c=ps[t].call||{},d=(new Date(c.date+"T12:00:00Z")-Date.now())/864e5;return d>-1&&d<=7;});
    if(soon.length)h=M.blk("EARNINGS SOON",'<span class="stg lvl">'+soon.length+'</span>',soon.map(function(t){var q=ps[t],o=q.overall||{},n=o.next_day||{};
      return p("<b>"+esc(t)+"</b> "+when(q.call)+": beat EPS "+pc((q.eps||{}).p_beat,0)+DOT+"up next day "+pc(o.p_up_next_day,0)+DOT+"range "+sp(n.p10)+" to "+sp(n.p90)+(q.implied_move!=null?DOT+"options "+String.fromCharCode(177)+pc(q.implied_move):"")+(q.position&&q.position.p_below_stop!=null?DOT+"chance under your stop "+(q.position.p_below_stop_words||pc(q.position.p_below_stop,0)):"")+few(q.few));}).join("")+
      '<div class="gap"><a class="btn sm" href="#earnings">Open EARNINGS</a></div>',"Estimates, never promises.");}
  if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
document.addEventListener("click",function(ev){var b=ev.target.closest?ev.target.closest("[data-p16]"):null;if(!b)return;var t=b.getAttribute("data-p16");open[t]=!open[t];render();});
var prev=M.slots["td-dec"];
M.slots["td-dec"]=function(){setTimeout(paintToday,0);var h=prev?prev():"";return '<div id="p16-host"></div>'+h;};
MC.hooks.push(render);
var prevRender=M.render;M.render=function(){var o=prevRender.apply(this,arguments);try{render();}catch(e){}return o;};
setTimeout(render,0);
M.reload();
})();
