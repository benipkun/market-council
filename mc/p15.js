/* Market Council add-on 15: BOARD (System > Board). The standing review board of twelve strict peers: the latest
   cycle's average and the reality check, the approval cards waiting for your yes or no, the ranked open issues, the
   scoreboard over time, what was fixed on its own and who found it, and the full minutes (twelve reviews and the
   cross-examination). Records: state/board/*.json in the private repository. A yes or no is written to answers/;
   nothing here places an order. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
M.extra.bsb="state/board/scoreboard.json";M.extra.biss="state/board/issues.json";M.extra.bcards="state/board/cards.json";
M.extra.bmin="state/board/latest.json";M.extra.blog="state/board/changelog.json";M.extra.bpeers="state/board/peers.json";
var API="https://api.github.com/repos/benipkun/market-council-state",DASH=String.fromCharCode(8212),DOT=String.fromCharCode(183);
var note={},openPeer=null;
var SEV={4:"CRITICAL",3:"SERIOUS",2:"MODERATE",1:"MINOR"},SEVTAG={4:"stale",3:"stale",2:"lvl",1:"paper"};
function p(t){return '<p style="font-size:13px;line-height:1.5;white-space:normal;margin:5px 0">'+t+'</p>';}
function small(t){return '<div style="font-size:12px;color:var(--dim);white-space:normal;margin:3px 0">'+t+'</div>';}
function put(path,msg,text){var tok=MC.store(MC.K.tok);if(!tok)return Promise.resolve("Add your token in the Log tab first.");
return fetch(API+"/contents/"+path,{method:"PUT",headers:{"Authorization":"Bearer "+tok,"Accept":"application/vnd.github+json","Content-Type":"application/json"},body:JSON.stringify({message:msg,content:btoa(unescape(encodeURIComponent(text)))})})
.then(function(r){return r.ok?null:"Could not be sent ("+r.status+").";}).catch(function(){return "Could not be sent. Check your connection.";});}
function stamp(){return new Date().toISOString().replace(/[-:]/g,"").replace(/[.][0-9]+Z$/,"");}
function head(){
  var sb=M.X.bsb||{},cy=(sb.cycles||[]),c=cy[cy.length-1],pr=cy[cy.length-2];if(!c)return M.blk("REVIEW BOARD","",p("The board has not met yet."),"");
  var ch=pr?(c.avg-pr.avg):null;
  var b='<div style="display:flex;gap:16px;align-items:baseline"><span class="mono" style="font-size:28px;font-weight:800">'+c.avg.toFixed(1)+'</span><span>/10 average'+
    (ch==null?" (first cycle)":' <span class="'+(ch>=0?"up":"dn")+'">'+(ch>=0?"+":"")+ch.toFixed(1)+'</span>')+'</span></div>';
  b+=small("Cycle "+c.n+", "+esc(c.date)+". Written scores before fixes: "+c.avg_first.toFixed(1)+"; after fixes and re-judging: "+c.avg.toFixed(1)+". Open issues: "+c.open_total+" ("+c.opened+" new, "+c.closed+" closed this cycle).");
  if(c.board_wrong)b+='<div class="q" style="color:var(--wn)"><b>Reality check:</b> '+esc(c.board_wrong)+'</div>';
  var r=c.reality||{};b+=small("Reality the board is held to: ideas vs the index "+(r.ideas_vs_index==null?DASH:(Math.round(1000*r.ideas_vs_index)/10)+" points")+DOT+" real money vs the index "+(r.real_money_vs_index==null?DASH:"$"+Number(r.real_money_vs_index).toFixed(2))+DOT+" forecast error "+(r.forecast_error==null?DASH:r.forecast_error)+" (always 50% scores "+(r.forecast_error_always_50==null?DASH:r.forecast_error_always_50)+")");
  if((c.minutes_problems||[]).length)b+=small("Problems with the minutes: "+esc(c.minutes_problems.join("; ")));
  var u=(c.budget||{}).used||{},l=(c.budget||{}).limit||{};b+=small("Budget used: "+esc(Object.keys(u).map(function(k){return k+" "+u[k]+(l[k]!=null?" of "+l[k]:"");}).join(", ")||DASH));
  return M.blk("REVIEW BOARD",'<span class="stg '+(c.board_wrong?"stale":"live")+'">CYCLE '+c.n+'</span>',b,"Twelve strict peers inspect the real app and its real results every week. A fix counts only when the peer who raised it accepts it.");
}
function cards(){
  var cs=((M.X.bcards||{}).cards||[]).filter(function(c){return c.status==="waiting";});
  if(!cs.length)return M.blk("WAITING FOR YOUR YES","",p("No approval card is waiting."),"");
  var b=cs.map(function(c){
    return '<div class="q" style="margin-top:8px"><b>'+esc(c.id)+". "+esc(c.title)+'</b>'+p("<b>Flaw:</b> "+esc(c.flaw))+p("<b>Evidence:</b> "+esc(c.evidence))+p("<b>Proposed change:</b> "+esc(c.proposal))+
      (c.history_test?p("<b>Test on history it was not tuned on:</b> "+esc(c.history_test)):"")+p("<b>Risk:</b> "+esc(c.risk))+small("Raised by "+esc((c.raised_by||[]).join(", ")))+
      '<div class="gap"><button class="btn sm" data-p15="yes" data-id="'+esc(c.id)+'">Yes</button> <button class="btn sm" data-p15="no" data-id="'+esc(c.id)+'">No</button></div>'+(note[c.id]?small(esc(note[c.id])):"")+'</div>';
  }).join("");
  return M.blk("WAITING FOR YOUR YES",'<span class="stg lvl">'+cs.length+' CARD'+(cs.length===1?"":"S")+'</span>',b,"Anything that changes money logic, data sources, spending, privacy or your standing decisions waits for you.");
}
function issues(){
  var is=((M.X.biss||{}).issues||[]).filter(function(i){return i.status==="open";});
  is.sort(function(a,b){return (b.severity-a.severity)||((b.raised_by||[]).length-(a.raised_by||[]).length);});
  var b=is.map(function(i){
    return '<div style="margin:6px 0"><span class="stg '+(SEVTAG[i.severity]||"paper")+'" style="font-size:10px">'+(SEV[i.severity]||"")+'</span> <b>'+esc(i.id)+". "+esc(i.title)+'</b>'+
      small(esc((i.raised_by||[]).length+" peer"+((i.raised_by||[]).length===1?"":"s")+" ("+(i.raised_by||[]).join(", ")+")"+" "+DOT+" effort "+i.effort+" "+DOT+" "+(i.lane==="approval"?"needs your yes":"safe lane")+" "+DOT+" "+(i.first_cycle===i.last_cycle?"new":"carried over since cycle "+i.first_cycle)))+'</div>';
  }).join("");
  return M.blk("OPEN ISSUES, WORST FIRST",'<span class="stg paper">'+is.length+'</span>',b||p("No open issue."),"Issues stay open until fixed and accepted, or dropped with a reason.");
}
function board(){
  var cy=((M.X.bsb||{}).cycles||[]).slice(-6),peers=(M.X.bpeers||{}).peers||[];if(!cy.length)return "";
  var h='<div class="tw"><table><thead><tr><th>Peer</th>'+cy.map(function(c){return '<th class="r">'+c.n+'</th>';}).join("")+'</tr></thead><tbody>';
  peers.forEach(function(pe){h+='<tr><td>'+esc(pe.name)+' <span style="color:var(--dim)">'+esc(pe.role)+'</span></td>'+cy.map(function(c){var s=(c.scores||{})[pe.id];return '<td class="r mono">'+(s==null?DASH:s)+'</td>';}).join("")+'</tr>';});
  h+='<tr><td><b>Average</b></td>'+cy.map(function(c){return '<td class="r mono"><b>'+c.avg.toFixed(1)+'</b></td>';}).join("")+'</tr>';
  h+='<tr><td>Issues opened / closed</td>'+cy.map(function(c){return '<td class="r mono">'+c.opened+"/"+c.closed+'</td>';}).join("")+'</tr></tbody></table></div>';
  return M.blk("SCOREBOARD","",h,"Scores after re-judging, per cycle.");
}
function fixed(){
  var l=((M.X.blog||{}).entries||[]).slice(-12).reverse();if(!l.length)return "";
  return M.blk("FIXED ON ITS OWN (CHANGELOG)","",l.map(function(x){return '<div style="margin:5px 0"><b>'+esc(x.issue)+'</b> '+esc(x.what)+small(esc("Cycle "+x.cycle+DOT+" found by "+x.found_by+DOT+" accepted by "+(x.accepted_by||DASH)+DOT+" tests "+x.tests+(x.commit?DOT+" "+x.commit:"")))+'</div>';}).join(""),"");
}
function minutes(){
  var m=M.X.bmin;if(!m||!m.peers)return "";
  var b=m.peers.map(function(pe){var o=openPeer===pe.id;
    var h='<div style="margin:6px 0"><button class="btn sm" data-p15="peer" data-id="'+esc(pe.id)+'">'+esc(pe.name)+DOT+esc(pe.role)+": "+pe.score+(pe.rescore!=null&&pe.rescore!==pe.score?" "+String.fromCharCode(8594)+" "+pe.rescore:"")+"/10"+'</button>';
    if(o){h+=p("<b>Checked:</b> "+esc((pe.checked||[]).join("; ")))+p("<b>Worst flaw:</b> "+esc((pe.worst||{}).text))+small("Evidence: "+esc((pe.worst||{}).evidence))+p("<b>Weak point:</b> "+esc(pe.weak))+p("<b>Fix:</b> "+esc(pe.fix))+(pe.after?p("<b>After the fixes:</b> "+esc(pe.after)):"");}
    return h+'</div>';}).join("");
  var x=(m.cross||[]).map(function(c){return '<div style="margin:6px 0"><b>'+esc(c.from)+" on "+esc(c.to)+':</b> '+esc(c.attack)+(c.answer?small(esc(c.to)+": "+esc(c.answer)):"")+'</div>';}).join("");
  return M.blk("MINUTES: THE TWELVE REVIEWS","",b,"Tap a peer to read the review.")+(x?M.blk("CROSS-EXAMINATION","",x,"Each peer attacks the weakest point of another's review."):"");
}
function render(){var el=$("v-board");if(!el)return;var h=head()+cards()+issues()+board()+fixed()+minutes();if(el.__h!==h){el.innerHTML=h;el.__h=h;}}
document.addEventListener("click",function(e){var b=e.target.closest?e.target.closest("[data-p15]"):null;if(!b)return;var k=b.getAttribute("data-p15"),id=b.getAttribute("data-id");
  if(k==="peer"){openPeer=openPeer===id?null:id;render();return;}
  note[id]="Sending"+String.fromCharCode(8230);render();
  put("answers/"+stamp()+"-board-"+id+".json","Market Council answer: board card "+id,JSON.stringify({kind:"board",id:id,answer:k,at:new Date().toISOString().replace(/[.][0-9]+Z$/,"Z")}))
  .then(function(err){note[id]=err||("Your "+k+" is recorded. The board acts on it at its next cycle.");render();});});
MC.hooks.push(render);
setTimeout(render,0);
M.reload();
})();
