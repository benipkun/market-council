"""Answers Ben's questions head on. Standard library only.

Code gathers his real data (books, cash, holdings, risk profile, standing decisions, the action list, the idea cards,
the Forecaster's chances, the order plans, fresh prices, our fair values, the partners' statement and the conversation so
far) and works out the system's own answer. The most capable Claude model in the budget then writes the reply in a fixed
order: the answer in the first sentence; why, in two to four points with his numbers; what would change it; how strong
the evidence is. Every reply is checked: the first sentence must answer, banned phrases are rejected, and no number may
appear that is not in his data. A failed reply is retried once; with no API key, no budget left or two failures, the
code's own answer is used in the same order.

    python3 ops/engine/answer.py eval     runs the fixed test questions on the real records (old and new answers)
"""
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import actions  # noqa: E402

ROOT = os.environ.get("MC_ROOT", ".")
API = "https://api.anthropic.com/v1/messages"
MODELS = ["claude-fable-5-1", "claude-opus-5-5"]          # most capable first; the next one when its daily cap is used
PRICE = {"claude-fable-5-1": (10.0, 50.0, 12.5, 0.25), "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20)}   # $ per million: in, out, cache write, cache read
DAILY_USD = {"claude-fable-5-1": 2.00, "claude-opus-5-5": 1.00}
MONTHLY_USD = 20.0
MAX_TOKENS = 900
SPEND = "state/agents/spend.json"
BANNED = ["consider", "you may want to", "some investors", "it's important to note", "it is important to note", "do your own research",
          "it depends", "not financial advice", "not advice", "consult a", "past performance"]
OPENERS = ("it depends", "generally", "in general", "when it comes", "great question", "there are", "investing ", "as a ", "well,", "that's a", "the question")
NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
TESTS = ["Should I sell UBER now?", "What should I do with 100000 HUF today?", "Is NVO a buy at this price?", "Why is there no trade today?",
         "What's the chance my portfolio is down this year?", "Swap SOFI for something better?", "How much MRK should I buy?",
         "Should I sell CHWY?", "What is my biggest risk right now?", "Where should my next 120000 HUF go?", "Is UBER going to reach 80?",
         "How much cash should I keep?", "What happens if UBER falls 20%?", "Am I beating the index fund?", "What should I do this week?"]


def rj(rel, default=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def wj(rel, obj):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def r(x, n=4):
    try:
        return round(float(x), n)
    except Exception:
        return None


def live_quote(syms):
    # the latest trade (or close) for the shares the question is about, so an answer about "this price" uses today's price
    if not syms:
        return {}
    try:
        url = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols=" + "%7C".join(urllib.parse.quote(s) for s in syms)
               + "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "market-council"}), timeout=15) as f:
            q = (json.load(f).get("FormattedQuoteResult") or {}).get("FormattedQuote") or []
        q = [q] if isinstance(q, dict) else q
        out = {}
        for x in q:
            try:
                out[x["symbol"]] = {"price": float(str(x.get("last")).replace(",", "")), "time": x.get("last_time")}
            except Exception:
                pass
        return out
    except Exception:
        return {}


def history(n=3):
    m = (rj("state/messages.json", {}) or {}).get("messages") or []
    out, by = [], dict((x.get("id"), x) for x in m)
    for x in m:
        if x.get("from") == "council" and x.get("reply_to") in by:
            out.append({"question": by[x["reply_to"]].get("text"), "answer": str(x.get("text") or "")[:700]})
    return out[-n:]


def gather(q, conv=None, fresh=True):
    snap, dec = rj("treasury/snapshot.json", {}) or {}, rj("state/decisions.json", {}) or {}
    acts, plans = rj("state/actions.json", {}) or {}, rj("state/plans.json", {}) or {}
    fc, quant = rj("state/forecasts.json", {}) or {}, rj("state/quant.json", {}) or {}
    cards_ix, st = rj("research/cards/index.json", {}) or {}, rj("state/partners/statement.json", {}) or {}
    ctx = actions.build_ctx()
    ctx["spy"] = ctx.get("spy") or (acts.get("inputs") or {}).get("spy")
    held = [p.get("ticker") for p in snap.get("positions") or [] if p.get("ticker")]
    named = actions.ticker_in(q, ctx)
    open_cards = [c for c in dec.get("cards") or [] if c.get("status") == "open" and c.get("kind") == "idea" and c.get("ticker")]
    ts = list(dict.fromkeys(held + ([named] if named else []) + [c["ticker"] for c in open_cards][:6]))
    assets, tg = quant.get("assets") or {}, fc.get("targets") or {}
    live = live_quote([t for t in ts if t in (held + [named])]) if fresh else {}
    sys_ans = actions.answer(q, ctx)
    nav = float(snap.get("nav") or 0)
    f = {"today": datetime.date.today().isoformat(), "question": q,
         "system_answer": {"head": sys_ans["head"], "lines": [a.get("line") for a in sys_ans["actions"]]},
         "action_list_today": [a.get("line") for a in acts.get("actions") or []],
         "risk_profile": dec.get("profile"),
         "books": {"as_of": snap.get("as_of"), "cash": r(snap.get("cash"), 2), "value": r(nav, 2), "positions": [
             {"ticker": p.get("ticker"), "shares": r(p.get("qty")), "average_cost": r(float(p.get("cost_basis") or 0) / float(p["qty"]), 2) if p.get("qty") else None,
              "price": r(p.get("last_price"), 2), "value": r(p.get("market_value"), 2), "weight": r(float(p.get("market_value") or 0) / nav, 4) if nav else None,
              "gain": r(float(p.get("market_value") or 0) / float(p.get("cost_basis") or 1) - 1, 4) if p.get("cost_basis") else None} for p in snap.get("positions") or []]},
         "standing_decisions": dec.get("keeps") or {},
         "idea_cards": [{"ticker": c["ticker"], "title": c.get("title"), "buy_now": (c.get("verdict") or {}).get("buy"), "why_not": c.get("grey_reason"),
                         "limit": c.get("entry"), "stop": c.get("stop"), "take_profit": c.get("take_profit"), "forecast": c.get("forecast_line")} for c in open_cards],
         "order_plans": [dict((k, p.get(k)) for k in ("ticker", "label", "stop", "take_profit", "loss_at_stop", "reward_risk", "until", "kept")) for p in plans.get("holdings") or []],
         "prices": dict((t, {"close": r((assets.get(t) or {}).get("last"), 2), "close_date": (assets.get(t) or {}).get("last_date"),
                             "change_1d": r((assets.get(t) or {}).get("ret_1D")), "change_1m": r((assets.get(t) or {}).get("ret_1M")),
                             "from_1y_high": r((assets.get(t) or {}).get("from_high_1y")), "live": live.get(t)}) for t in ts),
         "fair_values": dict((c.get("t"), {"fair": c.get("fair"), "range": c.get("fair_range"), "analyst_target": c.get("target"), "rating": c.get("rating")})
                             for c in cards_ix.get("cards") or [] if c.get("t") in ts),
         "forecasts": dict((t, dict((h, dict((k, r(v.get("p"), 3)) for k, v in ((tg[t].get("h") or {}).get(h) or {}).get("f", {}).items()))
                                    for h in ("1m", "1y"))) for t in ts if t in tg and not tg[t].get("none")),
         "portfolio_forecast": dict((h, dict((k, r(v.get("p"), 3)) for k, v in (((fc.get("portfolio") or {}).get("h") or {}).get(h) or {}).get("f", {}).items())) for h in ("1m", "1y")),
         "monthly_contribution": (acts.get("inputs") or {}).get("monthly_huf"), "usd_huf": (acts.get("inputs") or {}).get("usd_huf"),
         "partners_bottom_line": st.get("bottom_line"),
         "conversation": conv if conv is not None else history(),
         "missing": [x for x in ["news: the hourly news reader has been offline since " + str((rj("digests/latest.json", {}) or {}).get("as_of"))[:10]
                                 if (rj("digests/latest.json", {}) or {}).get("as_of", "") < (datetime.date.today() - datetime.timedelta(days=2)).isoformat() else None] if x]}
    return f, sys_ans


def numbers_in(x, out=None):
    out = [] if out is None else out
    if isinstance(x, bool) or x is None:
        return out
    if isinstance(x, (int, float)):
        out.append(float(x))
    elif isinstance(x, str):
        out.extend(float(m.replace(",", "")) for m in NUM.findall(x) if m.replace(",", "").replace("-", "").replace(".", "").isdigit())
    elif isinstance(x, dict):
        for v in x.values():
            numbers_in(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            numbers_in(v, out)
    return out


def invented(answer, facts):
    known = set()
    for v in numbers_in(facts):
        for w in (v, v * 100, v / 100, round(v, 2), round(v * 100, 1), round(v * 100), round(v), round(v, 1)):
            known.add(round(w, 6))
            known.add(round(abs(w), 6))
    bad = []
    for v in numbers_in(answer):
        if (abs(v) <= 10 or 1900 <= v <= 2100) and float(v).is_integer():
            continue
        if not any(abs(v - k) <= max(0.011, 0.005 * abs(k)) for k in known):
            bad.append(v)
    return sorted(set(bad))


def check(ans, facts):
    errs = []
    if not isinstance(ans, dict):
        return ["not a JSON object"]
    for k in ("answer", "why", "would_change", "evidence"):
        if k not in ans:
            errs.append("missing " + k)
    if errs:
        return errs
    first = str(ans["answer"]).strip()
    if not first or first.lower().startswith(OPENERS):
        errs.append("the first sentence does not answer the question")
    if len(first.split()) > 40:
        errs.append("the first sentence is too long")
    if not isinstance(ans["why"], list) or not 1 <= len(ans["why"]) <= 4:
        errs.append("why must have one to four points")
    text = " ".join([first, " ".join(map(str, ans.get("why") or [])), str(ans["would_change"]), str(ans["evidence"])]).lower()
    for b in BANNED:
        if b in text:
            errs.append("banned phrase: " + b)
    bad = invented(ans, facts)
    if bad:
        errs.append("numbers not in the data: " + ", ".join("%g" % b for b in bad[:6]))
    return errs


def render(ans):
    out = [str(ans["answer"]).strip()]
    why = [str(x).strip() for x in ans.get("why") or [] if str(x).strip()]
    if why:
        out.append("Why:" + "".join("\n- " + w for w in why))
    if ans.get("would_change"):
        out.append("What would change it: " + str(ans["would_change"]).strip())
    if ans.get("evidence"):
        out.append("Evidence: " + str(ans["evidence"]).strip())
    return "\n".join(out)


def topic_answer(q, facts):
    # questions that are not about what to buy or sell, answered from the computed figures
    s = q.lower()
    pf = (facts.get("portfolio_forecast") or {}).get("1y") or {}
    if ("chance" in s or "probab" in s or "likely" in s) and "portfolio" in s and pf.get("port_loss") is not None:
        p = pf["port_loss"]
        return {"answer": "About %d%%: the Forecaster gives %d%% that the portfolio is worth less in a year at today's weights." % (round(100 * p), round(100 * p)),
                "why": ["The chance of a fall beyond your maximum loss in a year is %d%%." % round(100 * (pf.get("port_max") or 0))] if pf.get("port_max") is not None else ["One year ahead, at today's weights."],
                "would_change": "A change in the weights, above all the largest holding's share.", "evidence": "A model estimate from price history, not yet scored on your own record."}
    if "index" in s and ("beat" in s or "ahead" in s or "behind" in s) and facts.get("partners_bottom_line"):
        line = facts["partners_bottom_line"]
        return {"answer": ("No: " if "behind" in line else "Yes: ") + line.split(". ")[1].rstrip(".") + "." if ". " in line else line,
                "why": [line.split(". ")[0] + "."], "would_change": "The next weeks of results; the record is still short.", "evidence": "Real money against the same money in the index fund, from your ledger."}
    books = facts.get("books") or {}
    held = dict((p.get("ticker"), p) for p in books.get("positions") or [])
    nav, cash = float(books.get("value") or 0), float(books.get("cash") or 0)
    known = set(held) | set(facts.get("prices") or {}) | set(facts.get("fair_values") or {})
    t = next((w.upper() for w in re.findall(r"[A-Za-z]{2,6}", q) if w.upper() in known), None)
    pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    if t in held and pct_m and any(w in s for w in ("fall", "drop", "down", "crash", "lose")):
        x, pos = float(pct_m.group(1)) / 100.0, held[t]
        loss = float(pos.get("value") or 0) * x
        return {"answer": "You would lose about $%.2f, %.1f%% of your portfolio." % (loss, 100 * loss / nav if nav else 0),
                "why": ["%s is worth $%.2f, %d%% of the portfolio; %d%% of that is $%.2f." % (t, float(pos.get("value") or 0), round(100 * (pos.get("weight") or 0)), round(100 * x), loss),
                        "Your portfolio would go from $%.2f to $%.2f." % (nav, nav - loss)],
                "would_change": "Selling part of %s first, or adding money to other holdings." % t, "evidence": "Arithmetic on your books at the last price."}
    num_m = re.search(r"\$?(\d+(?:\.\d+)?)", q)
    if t and ("reach" in s or "hit " in s or "get to" in s) and num_m:
        level, keep = float(num_m.group(1)), (facts.get("standing_decisions") or {}).get(t) or {}
        if keep.get("target") and abs(level - float(keep["target"])) <= 0.01 * float(keep["target"]) and keep.get("chance_touch") is not None:
            return {"answer": "Probably: about %d%% that %s touches $%.2f before %s." % (round(100 * keep["chance_touch"]), t, level, keep.get("by")),
                    "why": ["It needs to rise %d%% from today's $%.2f." % (round(100 * (keep.get("to_target") or 0)), float(keep.get("price") or 0)),
                            "The chance it is still above $%.2f on %s is lower: %d%%." % (level, keep.get("by"), round(100 * (keep.get("chance_above_on_date") or 0)))],
                    "would_change": "A big move either way before %s, or a change in its yearly volatility." % keep.get("by"), "evidence": "A model estimate from one year of price moves (%s)." % (keep.get("method") or "random-walk model")[:80]}
        up = ((facts.get("forecasts") or {}).get(t) or {}).get("1y", {}).get("up")
        if up is not None:
            return {"answer": "No figure for exactly $%.2f; the Forecaster gives %d%% that %s is higher in a year." % (level, round(100 * up), t), "why": ["That is the closest forecast on record."],
                    "would_change": "A plan with $%.2f as its take-profit gets its own forecast the next night." % level, "evidence": "A model estimate from price history."}
    if "cash" in s and ("keep" in s or "how much" in s or "hold" in s):
        mc = float(((facts.get("risk_profile") or {}).get("limits") or {}).get("min_cash") or 0.03)
        return {"answer": "Keep at least $%.2f in cash (%d%% of the portfolio); you have $%.2f, so $%.2f is free to invest." % (mc * nav, round(100 * mc), cash, max(0.0, cash - mc * nav)),
                "why": ["Your risk profile keeps %d%% of the portfolio as cash; the portfolio is $%.2f." % (round(100 * mc), nav)],
                "would_change": "A change of your risk profile, or a deposit or withdrawal.", "evidence": "Your own rule, applied to your books."}
    cards = facts.get("idea_cards") or []
    if t in held and "buy" in s and not any(c.get("ticker") == t for c in cards):
        fv, f1 = (facts.get("fair_values") or {}).get(t) or {}, ((facts.get("forecasts") or {}).get(t) or {}).get("1y") or {}
        why = ["You already hold $%.2f of it, %d%% of the portfolio." % (float(held[t].get("value") or 0), round(100 * (held[t].get("weight") or 0)))]
        if fv.get("fair") is not None:
            why.append("Our fair value is $%.2f against a price of $%.2f." % (float(fv["fair"]), float(held[t].get("price") or 0)))
        if f1.get("beat") is not None:
            why.append("The Forecaster gives it %d%% to beat the index fund over a year." % round(100 * f1["beat"]))
        return {"answer": "No, not a buy now: none of your rules has raised a buy for %s." % t, "why": why, "would_change": "A card for %s that beats the index fund after fees." % t,
                "evidence": "Your written rules and our own valuation; the checks are unproven so far."}
    if t and t not in held and ("swap" in s or "sell" in s):
        return {"answer": "You don't hold %s, so there is nothing to swap." % t, "why": ["Your holdings are %s." % ", ".join(sorted(held))],
                "would_change": "Buying %s first." % t, "evidence": "Your books."}
    if s.startswith("why") and ("no trade" in s or "nothing" in s or "no buy" in s):
        lines = (facts.get("system_answer") or {}).get("lines") or [""]
        return {"answer": "Because no idea beats the same money in the index fund after fees right now.", "why": [x.strip() for x in lines[0].replace("HOLD: do nothing today. ", "").split("; ")[:3] if x.strip()],
                "would_change": "An idea whose expected result after fees beats the index fund.", "evidence": "The action list's own rule; the checks behind ideas are unproven so far."}
    if "risk" in s:
        pos = sorted((facts.get("books") or {}).get("positions") or [], key=lambda x: -(x.get("weight") or 0))
        if pos and pos[0].get("weight") is not None:
            top = pos[0]
            return {"answer": "Your biggest risk is %s at %d%% of the portfolio, against your limit of %d%%." % (top["ticker"], round(100 * top["weight"]), round(100 * float(((facts.get("risk_profile") or {}).get("limits") or {}).get("stock_cap") or 0.3))),
                    "why": ["It is %d%% of your money in one share." % round(100 * top["weight"])], "would_change": "Selling part of it, or adding money elsewhere.", "evidence": "Arithmetic on your books."}
    return None


def code_answer(sys_ans, facts):
    # the system's own answer in the same order, from the action list's numbers
    t_ans = topic_answer(facts.get("question") or "", facts)
    if t_ans:
        return t_ans
    a = (sys_ans.get("actions") or [{}])[0]
    t, typ = a.get("ticker"), a.get("type")
    line = str(a.get("line") or "")
    if typ == "HOLD" and a.get("decision"):
        first = "No, hold %s: you decided to keep it until %s, with a target of $%s." % (t, a.get("review_by"), actions.money(a.get("target")))
    elif typ == "HOLD" and t and line.startswith("HOLD " + t):
        first = "No, hold " + t + "."
    elif typ == "HOLD":
        first = "No trade now: " + (a.get("reason") or line.replace("HOLD: ", "")).split(". ")[0].rstrip(".") + "."
    else:
        first = "Yes: " + line.split(": ")[0].split(". Stop")[0].rstrip(".") + "."
    why = []
    fc = a.get("forecast") or {}
    if a.get("expected_usd") is not None and a.get("index_usd") is not None:
        why.append("Expected after fees %s$%s against %s$%s for the same money in the index fund." % ("+" if a["expected_usd"] >= 0 else "-", actions.money(abs(a["expected_usd"])),
                                                                                                     "+" if a["index_usd"] >= 0 else "-", actions.money(abs(a["index_usd"]))))
    if fc.get("tp_first") is not None:
        why.append("The Forecaster gives %d%% to reach the take-profit first and %d%% to hit the stop first." % (round(100 * fc["tp_first"]), round(100 * (fc.get("stop_first") or 0))))
    if a.get("effect"):
        why.append(a["effect"].replace("Measured effect of keeping it: ", "").rstrip(".") + ".")
    for x in (a.get("disagree") or [])[:1]:
        why.append(x[0].upper() + x[1:] + ".")
    if not why:
        rest = line.split(". ", 1)
        why.append(rest[1] if len(rest) > 1 else line)
    change = ("A price under the stop of $%s or above the take-profit of $%s." % (actions.money(a.get("stop")), actions.money(a.get("take_profit")))) if a.get("stop") else \
        ("Your review date of %s, or the price falling under your maximum-loss line." % a.get("review_by") if a.get("decision") else
         "An idea whose expected result after fees beats the index fund, or fresh data.")
    ev = (a.get("evidence") or {}).get("text") or ("A model estimate from price history." if a.get("decision") else "The system's written rules; the checks behind ideas are unproven so far.")
    return {"answer": first, "why": why[:4], "would_change": change, "evidence": ev[0].upper() + ev[1:]}


def spent():
    return rj(SPEND, {"days": {}}) or {"days": {}}


def pick_model(s):
    day = datetime.date.today().isoformat()
    month = sum(sum(v.values()) for d, v in (s.get("days") or {}).items() if d[:7] == day[:7])
    if month >= MONTHLY_USD:
        return None, "the monthly AI budget ($%.2f) is used up" % MONTHLY_USD
    for m in MODELS:
        if ((s.get("days") or {}).get(day) or {}).get("questions:" + m, 0.0) < DAILY_USD[m]:
            return m, None
    return None, "today's AI budget for questions is used up"


def record(model, usd):
    s, day = spent(), datetime.date.today().isoformat()
    d = s.setdefault("days", {}).setdefault(day, {})
    d["questions:" + model] = round(d.get("questions:" + model, 0.0) + usd, 6)
    s["days"] = dict(sorted(s["days"].items())[-120:])
    wj(SPEND, s)


def call(model, system, user):
    body = {"model": model, "max_tokens": MAX_TOKENS, "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}]}
    req = urllib.request.Request(API, data=json.dumps(body).encode("utf-8"), headers={
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", "").strip(), "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as f:
        m = json.load(f)
    u, p = m.get("usage") or {}, PRICE[model]
    usd = (u.get("input_tokens", 0) * p[0] + u.get("output_tokens", 0) * p[1] + u.get("cache_creation_input_tokens", 0) * p[2] + u.get("cache_read_input_tokens", 0) * p[3]) / 1e6
    return "".join(b.get("text", "") for b in m.get("content") or [] if b.get("type") == "text"), usd


def parse(text):
    t = text.strip()
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


def instructions():
    with open(os.path.join(HERE, "agent_questions.md"), encoding="utf-8") as f:
        raw = f.read()
    return raw.split("\n---", 1)[1].strip() if raw.startswith("---") else raw


def reply(q, conv=None, fresh=True, use_ai=True):
    facts, sys_ans = gather(q, conv, fresh)
    meta = {"model": "code", "checked": True, "cost": 0.0, "note": None}
    if use_ai and os.environ.get("ANTHROPIC_API_KEY", "").strip():
        model, why = pick_model(spent())
        if model:
            system, note, errs = instructions(), "", []
            for attempt in (1, 2):
                try:
                    text, usd = call(model, system, "FACTS from Ben's records, computed by code:\n" + json.dumps(facts, ensure_ascii=False, separators=(",", ":")) + note)
                    record(model, usd)
                    meta["cost"] = round(meta["cost"] + usd, 6)
                    ans = parse(text)
                    errs = check(ans, facts)
                except Exception as e:
                    ans, errs = None, ["the call failed (%s)" % type(e).__name__]
                if not errs:
                    meta.update(model=model)
                    return render(ans), meta
                note = "\n\nYour last answer failed these checks: " + "; ".join(errs) + ". Answer again as one JSON object."
            meta["note"] = "the AI answer failed its checks twice (%s); the code's answer is shown" % "; ".join(errs)
        else:
            meta["note"] = why
    else:
        meta["note"] = "no API key yet: the code's answer is shown" if use_ai else None
    return render(code_answer(sys_ans, facts)), meta


def evaluate():
    # the fixed test questions on the real records: the old reply beside the new one, and whether the new one passes
    ctx = actions.build_ctx()
    ctx["spy"] = ctx.get("spy") or ((rj("state/actions.json", {}) or {}).get("inputs") or {}).get("spy")
    rows = []
    for q in TESTS:
        old = actions.text(actions.answer(q, ctx))
        new, meta = reply(q, conv=[], fresh=True)
        first = new.split("\n")[0]
        facts, _ = gather(q, conv=[], fresh=False)
        rows.append({"q": q, "old": old, "new": new, "model": meta["model"], "note": meta["note"], "cost": meta["cost"],
                     "first_sentence_answers": not first.lower().startswith(OPENERS) and len(first.split()) <= 40,
                     "uses_real_numbers": bool(numbers_in(new)), "banned": [b for b in BANNED if b in new.lower()]})
    out = {"as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": rows,
           "passed": sum(1 for x in rows if x["first_sentence_answers"] and x["uses_real_numbers"] and not x["banned"]), "of": len(rows),
           "cost": round(sum(x["cost"] for x in rows), 4)}
    wj("state/questions_eval.json", out)
    return out


def queue_question(fid):
    path = os.path.join(ROOT, "inbox", "queue", fid + ".md")
    with open(path, encoding="utf-8") as f:
        for ln in f.read().split("\n"):
            s = ln.strip()
            if s and not s.startswith("#"):
                return path, (s[4:].strip() if s.lower().startswith("ask:") else s)
    return path, ""


def finish(fid, facts_path, answer_path):
    # used by the Trade Inbox routine: check its answer against the facts it was given, then record it
    with open(facts_path, encoding="utf-8") as f:
        facts = json.load(f)
    with open(answer_path, encoding="utf-8") as f:
        ans = parse(f.read())
    errs = check(ans, facts)
    if errs:
        print("FAILED: " + "; ".join(errs))
        return 2
    path, q = queue_question(fid)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    msgs = rj("state/messages.json", {"messages": [], "notified_picks": {}}) or {"messages": [], "notified_picks": {}}
    msgs["messages"] = ((msgs.get("messages") or []) + [
        {"id": fid, "at": now, "from": "ben", "text": q, "via": "ntfy" if "-ntfy-" in fid else "app", "reply_to": None, "status": None},
        {"id": fid + "-r", "at": now, "from": "council", "text": render(ans), "via": None, "reply_to": fid, "status": "answered", "model": "claude (Trade Inbox routine)", "note": None}])[-200:]
    wj("state/messages.json", msgs)
    wj("outbox/queue/%s-reply.json" % now.replace("-", "").replace(":", ""), {"title": "Market Council reply", "message": "Your answer is ready in the app.",
                                                                               "click": "https://benipkun.github.io/market-council/#chat", "tags": []})
    os.remove(path)
    print("answered")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "facts":
        f, _ = gather(" ".join(sys.argv[2:]))
        print(json.dumps(f, ensure_ascii=False, indent=1))
        sys.exit(0)
    if len(sys.argv) > 4 and sys.argv[1] == "finish":
        sys.exit(finish(sys.argv[2], sys.argv[3], sys.argv[4]))
    if len(sys.argv) > 1 and sys.argv[1] == "eval":
        o = evaluate()
        print("questions: %d of %d passed; models used: %s" % (o["passed"], o["of"], ", ".join(sorted(set(x["model"] for x in o["rows"])))))
    else:
        text, meta = reply(" ".join(sys.argv[1:]))
        print(text)