/* Market Council add-on 13: GUIDE (System > Guide). The whole app explained screen by screen, so its owner can
   understand it and explain it to others. Plain text, no figures from the records. */
(function(){
"use strict";
var M=window.MCX,MC=window.MC;if(!M||!MC)return;var esc=MC.esc,$=MC.$;
var G=[
["IN ONE MINUTE",[
"Market Council is a personal system for watching one portfolio and deciding what to do with it. It reads prices, company figures and news, works out risk and value with plain code, and turns what it finds into a short, numbered list of actions: buy this many shares at this price, sell, swap one share for another, or do nothing.",
"It never trades. It suggests; you place every order yourself at your broker and log it in the app.",
"Every number comes from written rules run as code that anyone can re-run. AI agents read, argue, explain and keep the books, but they never make up a figure.",
"It is built to be honest about itself: every idea is written down on the day it is raised and checked later, every forecast is scored when its date arrives, and anything without enough evidence carries the word unproven."]],
["HOW IT IS BUILT",[
"The app is a web page on GitHub Pages, made for the phone. It opens like an app from the home screen.",
"Two repositories: a public one with the app and the code, and a private one with the records (holdings, cash, every trade, every answer, every result). The app reads the private records with your own access token, so nobody else sees the money.",
"Jobs on GitHub's servers do the arithmetic on a timetable: the calculation engine three times every weekday, the wide screen of about 300 large companies every morning, the back-checks every night, a health check every half hour, and a listener for messages from the phone.",
"AI routines do the reading and writing: the hourly analysts look for news and mispricings, the Trade Inbox keeps the books and answers questions, the daily books routine reconciles cash and prices, and the partners meet every Saturday.",
"Messages reach the phone through ntfy. They are short: alerts and answers say that something needs a look and the detail is in the app; trade confirmations repeat what you logged.",
"If a job fails or data goes stale, the health check sends one phone message, and the STATUS screen shows what is wrong."]],
["TODAY > NOW",[
"WHAT TO DO NOW is the heart of the app: the ranked action list, worked out by plain code from everything below. Each line is exactly one of BUY, SELL, SWAP or HOLD, with shares, limit price, total in dollars and forints, fees, what pays for it, stop-loss and take-profit, the Forecaster's chances, the expected result after fees, the effect on the whole portfolio and how strong the evidence is.",
"The rule for a BUY: the idea must be expected to do better than the same money in the S&P 500 index fund over the same time, after fees, and the Forecaster must not rate it below an even chance of beating that fund. When nothing qualifies, the top line is HOLD with the reason. Doing nothing is an answer.",
"Two questions can be asked right there: What should I do with an amount now? and Should I sell a holding? The answer always comes in the same numbered format, sized to your cash, fees and risk profile. A holding you decided to keep is never argued for sale; it shows its target, review date and what keeping it does to the risk.",
"The DECISION DESK below shows the idea cards. A card only asks for your yes when the action list would buy it, so the desk and the list never disagree. Ideas that do not qualify stay visible under NOT A BUY NOW, each with its reason. The morning check also asks whether a trade is missing from the books."]],
["TODAY > BRIEF",[
"The daily brief is the same picture as a readable page: what to do now, the cards, new picks from the analysts, market stress and data problems. It is rebuilt three times every weekday."]],
["PORTFOLIO",[
"MAP shows what is held, how much of the portfolio each part is, and how the parts move together.",
"RISK puts the whole portfolio first: the share of the largest holding, the one-in-ten bad year from thousands of simulated years, a stress test, and for every idea what it would do to those figures compared with the same money in the index fund.",
"BOOKS holds cash, positions, cost, realised and unrealised gains in dollars and forints, the monthly contribution and the goal: how likely it is to be reached at the planned saving.",
"PLANS gives every holding and idea a written order plan: a label (short-term, medium-term or long-term, which you can change), the stop-loss with the loss in money and as a share of the portfolio, the take-profit, reward to risk, a time limit, the Forecaster's chance for each level, the expected result after fees and the orders written in Revolut's own steps. Stops come from how much the share normally moves and from past lows, never from a round number, and are never lowered. Once a holding is up by its first risk, the plan tells you to move the stop up to the entry. It warns when results are due inside a plan and messages the phone only when a plan needs you. A back-test shows how the stop and take-profit rules did on 25 years of prices against simply holding.",
"LOG A TRADE is where every buy, sell, deposit and withdrawal is entered; the books update within a minute or two."]],
["RESEARCH",[
"DESK holds a research card for every share the system looks at: our own fair value as a range across reasonable assumptions, the seven-point checklist with the reading behind each check, earnings, insider and large-fund activity, and news.",
"WATCHLIST lists shares to keep an eye on, with price alerts that message the phone.",
"QUANT holds the tools: ranges of outcomes from simulation, an options calculator, pairs that move together, the cost of trading each share, and an experimental learned signal that is shown but not used until it proves itself."]],
["COUNCIL",[
"TEAM shows who does what: the analysts propose, the Councillor argues against each pick before it reaches you, the Forecaster puts a probability on everything, the bookkeeper keeps the records, and the partners judge the whole operation. Each one's job and limits are written down.",
"STRATEGY is the written approach: the risk profile, the limits per share, the core of index funds, and when the system may suggest anything at all.",
"CHECKS shows each of the seven checks a share is scored on and whether it has worked in the past: a check counts as working only if, in both halves of its history, the shares that passed beat those that failed and the index fund. Otherwise it is unproven and labelled so everywhere.",
"FORECASTS is the Forecaster's log: yes-or-no questions with a date and a probability, written once and never edited (each entry carries a fingerprint of the one before), scored automatically when the date arrives, and compared with two simple rivals: always saying 50%, and the plain base rate. A back-test over twelve years of past forecasts shows how well calibrated it is.",
"RECORD is the live track record: every idea raised is logged at that day's price, offered or not, and measured against the index fund and the average share. Under 20 finished cases it says: too few cases to rely on.",
"PARTNERS are five critics, the Managing Partner, the Sceptic, the Numbers Partner, the Contrarian and the Operator, who meet every Saturday and judge whether the whole thing is profitable after every cost. They work from a statement written by plain code: real money against the same money in the index fund, payments in and out with their dates, fees, running costs, the bad year and the state of the machine. Problems they raise stay in a register until fixed or voted down.",
"CHAT answers questions about the records; questions about what to do are answered with the action list."]],
["SYSTEM",[
"STATUS shows every job, when it last ran, whether the data is fresh, and whether the prices of every card and holding agree across two sources. A card whose price fails that check is held back.",
"TRACK RECORD is the older practice record of the analysts' picks against the index fund."]],
["THE RULES IT LIVES BY",[
"No automatic trading. Nothing connects to the broker. You place every order.",
"Plain code for every number; AI for reading, arguing and explaining. Agents never invent a figure.",
"One judge: only the action list says buy or sell, so every screen and every message agrees with it.",
"The index fund is the yardstick. An idea has to beat it after fees, or the answer is to hold or to buy the index fund.",
"Your risk profile sets the size of every idea, the limit per share and the largest loss you accept. Asking for more shows the numbers with a one-line warning.",
"Your standing decisions are respected: a position you chose to keep is shown with its effect, never argued for sale.",
"Honesty labels stay on: unproven, too few cases to rely on, stale data, estimate. Fewer than 20 cases is never presented as evidence.",
"Signals are not shared with other people before a legal check."]],
["HOW TO EXPLAIN IT TO SOMEONE",[
"Short version: It is my own investment system. Code does the maths, AI agents argue about it, and every morning it gives me a numbered list of what to do, or tells me to do nothing. I place the orders myself.",
"What makes it different: it writes down every idea and every forecast on the day and scores them later, so it cannot quietly forget its mistakes; and five critic agents meet every week to say whether it is actually making money compared with simply buying the index fund.",
"Is it making money? Honestly: too early to say. The record is only weeks old, no forecast has come due yet, and today no idea beats the index fund after fees, so the system itself says hold. That is the point: it is built to tell you when it does not have an edge.",
"Is it AI picking stocks? No. The ideas come from written rules and checks that are tested on 25 years of prices; the AI reads news, challenges the ideas and explains the numbers.",
"Can I use it? Not yet. Sharing signals with others waits for a legal check."]]];
function html(){return G.map(function(s){return M.blk(esc(s[0]),"",s[1].map(function(p){return '<p style="font-size:13px;line-height:1.55;white-space:normal;margin:6px 0">'+esc(p)+'</p>';}).join(""),"");}).join("");}
function render(){var el=$("v-guide");if(!el)return;if(!el.__h){el.innerHTML=html();el.__h=1;}}
MC.hooks.push(render);
setTimeout(render,0);
})();
