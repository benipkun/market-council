/* Market Council add-on 21 (10 Nov 2026): the LEARN page, kept apart from the professional memos. Your call on the next
   companies before the committee votes (scored like the committee's), one question per memo with feedback on your
   answer, the weekly lesson card, and plain-word explanations of the terms the memos use.
   Data: state/learn/index.json (ops/engine/memos.py). Your calls and answers go to answers/learn-*.json in the private
   records; the Investment Committee routine writes the feedback and the lessons (ops/COMMITTEE.md). */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$,DOT=" "+String.fromCharCode(183)+" ",DASH=String.fromCharCode(8212);
M.extra.learn="state/learn/index.json";
var API="https://api.github.com/repos/benipkun/market-council-state",note="",sent={};
var TERMS=[["DCF (discounted cash flow)","What a business is worth today from the cash it should make in future years, with later cash counted for less. Our model forecasts five years, then adds a value for the years after."],
["Discount rate","How much less future cash is worth than cash today, per year. A higher rate gives a lower value. It is the main assumption in our DCF, so memos show the value at plus and minus one point."],
["Free cash flow","Cash the business has left after running costs and investment in equipment. It can pay dividends, buy back shares or repay debt."],
["Moat","What stops competitors taking a company's profits: brands, patents, switching costs, scale. In the numbers it shows as high margins that last for years."],
["Margin of safety","How far the price is below our estimate of value. A bigger gap leaves room for our estimate to be wrong."],
["Net debt / EBITDA","Debt minus cash, divided by yearly operating profit before depreciation. Around 3 or more means the debt takes a lot of profit to carry."],
["Forward P/E","The share price divided by next year's expected earnings per share. Lower means cheaper, if the earnings forecast is right."],
["Organic growth","Sales growth without the effect of buying or selling businesses and of currency moves; the growth the company made itself."],
["Guidance","The company's own forecast of its results. A cut often moves the price more than the latest results do."],
["Paper idea","An idea tracked as if bought, with no real money, to see whether the signal behind it works before it is trusted."],
["S&P 500 fund","A fund holding the 500 largest US companies. Every idea is measured against it: if an idea cannot beat it after fees, the fund is the better choice."],
["Stop-loss and take-profit","Prices set before buying: sell if it falls to the stop, or rises to the take-profit. Deciding the exit before the entry keeps emotions out."],
["Case count","How many past examples a result rests on. Under 20 is too few to rely on."]];
function pct(x){return x==null?DASH:(x>=0?"+":String.fromCharCode(8722))+Math.abs(100*x).toFixed(1)+"%";}
function send(obj,key){var tok=MC.store(MC.K.tok);if(!tok){note="Add your token in the Log tab first.";paint();return;}
var ts=new Date().toISOString().replace(/[-:]/g,"").slice(0,15)+"Z",id="learn-"+ts+"-"+Math.random().toString(36).slice(2,7);obj.id=id;obj.at=new Date().toISOString().slice(0,19)+"Z";
note="Saving"+String.fromCharCode(8230);paint();
fetch(API+"/contents/answers/"+id+".json",{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:"Market Council: learn "+obj.type,content:btoa(unescape(encodeURIComponent(JSON.stringify(obj))))})})
.then(function(r){note=r.ok?(obj.type==="call"?"Your call is saved. The committee votes without seeing it.":"Saved. Feedback appears here after the committee's next run."):"Could not be saved ("+r.status+").";if(r.ok)sent[key]=obj;paint();})
.catch(function(){note="Could not be saved. Check your connection.";paint();});}
function calls(x){var nx=x.next_up||[];if(!nx.length)return "";
return M.blk("YOUR CALL FIRST",'<span class="stg lvl">BEFORE THE VOTE</span>','<div class="src" style="white-space:normal">The committee writes these memos next. Make your call now; it is scored against what happens, next to the committee\'s.</div>'+
nx.map(function(t){var s=sent["call|"+t];return '<div class="q gap" style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"><b style="color:var(--tx);min-width:56px">'+esc(t)+'</b>'+
(s?'<span class="stg live">YOUR CALL: '+esc(s.vote)+'</span>':["APPROVE","DECLINE","MORE WORK"].map(function(v){return '<button class="btn sm" data-p21c="'+esc(t)+'|'+v+'">'+v+'</button>';}).join(""))+'</div>';}).join(""),"APPROVE = worth owning at this price for three years, DECLINE = not at this price, MORE WORK = not enough known yet.");}
function questions(x){var qs=(x.questions||[]).filter(function(q){return q.question;});if(!qs.length)return M.blk("QUESTIONS","",'<div class="msg">The first question comes with the next memo.</div>',"");
return M.blk("QUESTIONS",'<span class="stg lvl">'+qs.length+'</span>',qs.map(function(q,i){var k="ans|"+q.ticker+"|"+q.memo_date,s=sent[k],mine=q.your_answer||(s&&s.text);
return '<div class="q gap"><div class="fl">'+esc(q.ticker)+DOT+esc(q.memo_date)+DOT+"committee: "+esc(q.decision||"")+'</div><div style="white-space:normal;font-size:13px;color:var(--tx);margin:4px 0">'+esc(q.question)+'</div>'+
(mine?'<div class="src" style="white-space:normal">Your answer: '+esc(mine)+'</div>'+(q.feedback?'<div class="q" style="white-space:normal;border-left:3px solid var(--ac);padding-left:8px">'+esc(q.feedback)+'</div>':'<div class="src">Feedback comes with the committee\'s next run.</div>')+
((q.answer_points||[]).length?'<div class="fl" style="margin-top:6px">A GOOD ANSWER COVERS</div>'+q.answer_points.map(function(p){return '<div class="src" style="white-space:normal">'+String.fromCharCode(8226)+" "+esc(p)+'</div>';}).join(""):"")
:'<textarea id="p21-a'+i+'" rows="3" style="width:100%;margin-top:4px" placeholder="Two or three sentences"></textarea><button class="btn sm" data-p21a="'+i+'">Send answer</button>')+
(q.lesson?'<details style="margin-top:6px"><summary class="src">The lesson in this memo</summary><div class="src" style="white-space:normal">'+esc(q.lesson)+'</div></details>':"")+'</div>';}).join(""),"Answer in your own words; the answer points open after you answer.");}
function lessons(x){var ls=x.lessons||[];if(!ls.length)return "";
return M.blk("LESSON OF THE WEEK","",ls.map(function(l,i){return '<details class="q gap"'+(i===0?" open":"")+'><summary><b style="color:var(--tx)">'+esc(l.title||"")+'</b>'+DOT+esc(l.date||"")+'</summary><div style="white-space:normal;font-size:13px;margin-top:6px">'+esc(l.idea||"")+'</div>'+
(l.example?'<div class="src" style="white-space:normal;margin-top:6px">Example: '+esc(l.example)+'</div>':"")+(l.check_yourself?'<div class="src" style="white-space:normal;margin-top:6px">Check yourself: '+esc(typeof l.check_yourself==="string"?l.check_yourself:(l.check_yourself.question||"")+" "+(l.check_yourself.answer?"(Answer: "+l.check_yourself.answer+")":""))+'</div>':"")+'</details>';}).join(""),"");}
function record(x){var c=x.calls||[],r=x.your_record||{};if(!c.length)return "";
return M.blk("YOUR CALLS AGAINST THE COMMITTEE",'<span class="stg paper">'+esc(String(r.right||0))+" OF "+esc(String(r.scored||0))+' RIGHT</span>',c.map(function(k){var m=k.marks||{},ks=Object.keys(m),last=ks.length?m[ks[ks.length-1]]:null;
return '<div class="src" style="white-space:normal">'+esc(k.ticker)+DOT+esc(k.at)+DOT+"you: "+esc(k.your_vote)+DOT+"committee: "+esc(k.committee||"not voted yet")+DOT+(last?ks[ks.length-1]+" "+pct(last.vs_spy)+" vs S&P"+(last.right==null?"":(last.right?" (you were right)":" (you were wrong)")):"not scored yet")+'</div>';}).join("")+(r.honesty?'<div class="src">'+esc(r.honesty)+'</div>':""),esc(x.method||""));}
function terms(){return M.blk("TERMS IN PLAIN WORDS","",TERMS.map(function(t){return '<details class="q"><summary>'+esc(t[0])+'</summary><div class="src" style="white-space:normal">'+esc(t[1])+'</div></details>';}).join(""),"");}
function html(){var x=M.X.learn||{questions:[],calls:[],lessons:[],next_up:[]};return (note?'<div class="src">'+esc(note)+'</div>':"")+calls(x)+questions(x)+lessons(x)+record(x)+terms();}
function paint(){var el=$("v-learn");if(!el)return;var v={};(el.querySelectorAll("textarea")||[]).forEach(function(t){v[t.id]=t.value;});var h=html();if(el.__h!==h){el.innerHTML=h;el.__h=h;Object.keys(v).forEach(function(k){if($(k))$(k).value=v[k];});}}
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p21c],[data-p21a]"):null;if(!b)return;var x=M.X.learn||{};
if(b.hasAttribute("data-p21c")){var p=b.getAttribute("data-p21c").split("|");send({type:"call",ticker:p[0],vote:p[1]},"call|"+p[0]);}
else{var i=+b.getAttribute("data-p21a"),q=((x.questions||[]).filter(function(z){return z.question;}))[i],t=String(($("p21-a"+i)||{}).value||"").trim();if(!q)return;if(t.length<5){note="Write a sentence or two first.";paint();return;}
send({type:"answer",ticker:q.ticker,memo_date:q.memo_date,question:q.question,text:t.slice(0,1500)},"ans|"+q.ticker+"|"+q.memo_date);}});
var prevRender=M.render;M.render=function(){if(prevRender)prevRender.apply(this,arguments);paint();};
MC.hooks.push(paint);
M.reload();
})();
