"""Market Council order plans. Plain code; nothing here places an order.

For every holding and every open idea: a label (short, medium or long term; you can change it and the plan is worked
out again), an order plan (limit entry and how long it is valid, stop-loss with the loss in money, in % and as a share
of the portfolio, take-profit, reward to risk as one number, a time limit), the Forecaster's chance for each level,
the expected result after fees, the size from the stop and your risk profile, and the orders written the way Revolut
takes them.

Stops come from how much the share normally moves and from past price levels, never from a habitual round
percentage: twice the normal daily movement over the label's window (at least 5%), moved to just under the lowest
close of that window when that low sits close by. A stop is never lowered. Once a holding is up by its first risk,
the stop moves up to the entry price (the trailing rule).

Every engine run watches the plans and sends one phone message only when something needs you: a stop that should
move up, a level that was hit, a time limit that ran out, a forecast that moved more than 15 points, or results due
inside the plan. The nightly back-check job also tests the stop and take-profit rules on past prices (backtest()).
Written to state/plans.json and state/plans_backtest.json."""
import datetime
import math

import engine as E

FEE_PCT, FEE_MIN = 0.0025, 1.12
COST = 0.005                      # round trip used in the back-test, as in the back-checks (0.25% each way)
PROB_MOVE = 0.15                  # a forecast that moves this much is worth a message
SOON_DAYS = 14                    # results this close are warned about
REVOLUT_MAX_DAYS = 182            # Revolut limit orders can be set to expire up to about six months ahead
LABELS = {
    "short": {"name": "short-term", "words": "days to about four weeks", "vol_days": 10, "low_days": 20, "days": 28, "trading_days": 20},
    "medium": {"name": "medium-term", "words": "one to six months", "vol_days": 21, "low_days": 60, "days": 182, "trading_days": 126},
    "long": {"name": "long-term", "words": "longer than six months", "vol_days": 63, "low_days": 250, "days": 365, "trading_days": 252}}
REVOLUT = ("Revolut takes market, limit and stop orders for shares. Limit orders are for whole shares only and can be "
           "set to expire up to about six months ahead (check the date picker in the app). A stop order turns into a market "
           "order when its price is reached, and only in regular US hours, so a price that opens lower fills lower. There is "
           "no take-profit order for shares, and the shares under a stop order cannot also sit in a limit sell, so the "
           "take-profit is a price alert: when it rings, cancel the stop and sell with a limit order.")


def fee(usd):
    return round(max(FEE_PCT * usd, FEE_MIN), 2) if usd > 0 else 0.0


def r2(x, n=2):
    return None if x is None else round(float(x), n)


def day(s):
    return datetime.date.fromisoformat(str(s)[:10])


def daily_vol(closes, n=20):
    xs = [float(c) for d, c in closes[-(n + 1):] if c]
    r = [math.log(xs[i + 1] / xs[i]) for i in range(len(xs) - 1)]
    if len(r) < 5:
        return None
    m = sum(r) / len(r)
    return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))


def stop_level(price, closes, label):
    # normal movement first, then the nearest past low if it sits close to that line
    h = LABELS[label]
    v = daily_vol(closes) or 0.02
    dist = max(0.05, 2 * v * math.sqrt(h["vol_days"]))
    line = price * (1 - dist)
    lows = [float(c) for d, c in closes[-h["low_days"]:] if c]
    low = min(lows) if lows else None
    if low and low < price and abs(low - line) <= 0.25 * (price - line):
        return round(low * 0.99, 2), "1%% under the lowest close of the last %d trading days ($%.2f), which sits close to the normal-movement line ($%.2f)" % (h["low_days"], low, line)
    return round(line, 2), "twice the normal daily movement over %d trading days (%.1f%% under today's price)" % (h["vol_days"], 100 * dist)


def forecast_for(fct, t, stop, tp):
    # the Forecaster's chances for exactly these levels, if it has worked them out
    f = (fct or {}).get(t) or {}
    plan, h = f.get("plan") or {}, f.get("h") or {}
    if not plan or not stop or not tp or not plan.get("target") or not plan.get("stop"):
        return None
    if abs(float(plan["target"]) / tp - 1) > 0.01 or abs(float(plan["stop"]) / stop - 1) > 0.01:
        return None
    fh = (h.get(plan.get("horizon")) or {}).get("f") or {}
    a, b = fh.get("tp_first") or {}, fh.get("stop_first") or {}
    if a.get("p") is None:
        return None
    return {"tp_first": a.get("p"), "stop_first": b.get("p"), "range": [a.get("lo"), a.get("hi")], "cases": a.get("cases"), "few": bool(a.get("few")), "due": plan.get("due")}


def revolut_steps(t, shares, limit, stop, tp, until, held):
    n = "%s share%s" % (("%g" % shares), "" if shares == 1 else "s")
    s = []
    if not held:
        s.append("Buy: Revolut > Invest > %s > Buy > Limit order. Limit price $%.2f, %s, expiry %s. Review and confirm." % (t, limit, n, until))
    s.append("Stop-loss: %s > Sell > Stop order. Stop price $%.2f, %s. It becomes a market order at $%.2f, in regular US hours only." % (t, stop, n, stop))
    s.append("Take-profit: set a price alert for %s at $%.2f. When it rings, cancel the stop order and sell %s with a limit order at $%.2f." % (t, tp, n, tp))
    return s


def holding_plan(p, hold, keep, label, closes, fct, nav, prev, today):
    t = p["ticker"]
    price = float(p.get("last_price") or 0)
    mv = float(p.get("market_value") or 0)
    qty = float(p.get("qty") or (mv / price if price else 0))
    if not price or not qty:
        return None
    avg = float(p.get("cost_basis") or 0) / qty if qty else None
    same = prev and prev.get("label") == label
    if keep:
        floor = next((lv.get("price") for lv in (hold or {}).get("levels") or [] if str(lv.get("name") or "").startswith("Maximum-loss")), None)
        stop, stop_why = (round(float(floor), 2), "your maximum-loss line (30% under your average cost); your rules raise a sell card below it") if floor else stop_level(price, closes, label)
        tp, tp_why = float(keep["target"]), "your own target"
        until, why_until = str(keep.get("by") or "")[:10], "your review date"
    else:
        stop, stop_why = stop_level(price, closes, label)
        if same and prev.get("stop") and float(prev["stop"]) > stop:
            stop, stop_why = float(prev["stop"]), "kept from the earlier plan: a stop is never lowered"
        tp, tp_why = round(price + 2 * (price - stop), 2), "twice the stop distance above today's price"
        until = prev.get("until") if same and prev.get("until") else (today + datetime.timedelta(days=LABELS[label]["days"])).isoformat()
        why_until = "the %s window (%s)" % (LABELS[label]["name"], LABELS[label]["words"])
    initial = float(prev["initial_stop"]) if same and prev.get("initial_stop") else stop
    loss = qty * (price - stop) + fee(qty * stop)
    fc = forecast_for(fct, t, stop, tp)
    up, dn = tp / price - 1, 1 - stop / price
    exp = (mv * (fc["tp_first"] * up - (fc.get("stop_first") or 0) * dn) - fee(mv)) if fc else None
    plan = {"id": "H:" + t, "ticker": t, "held": True, "kept": bool(keep), "label": label, "shares": r2(qty, 6), "price": r2(price), "average_cost": r2(avg),
            "stop": r2(stop), "stop_why": stop_why, "initial_stop": r2(initial), "take_profit": r2(tp), "take_profit_why": tp_why,
            "loss_at_stop": r2(loss), "loss_pct": r2(dn, 4), "loss_share_of_portfolio": r2(loss / nav, 4) if nav else None,
            "gain_at_take_profit": r2(qty * (tp - price) - fee(qty * tp)), "reward_risk": r2(up / dn, 2) if dn > 0 else None,
            "until": until, "until_why": why_until, "forecast": fc, "expected_after_fees": r2(exp),
            "forecast_note": None if fc else "The Forecaster works out the chances for these levels in its next nightly run.",
            "revolut": revolut_steps(t, float(math.floor(qty)) if qty >= 1 else qty, price, stop, tp, until, True)}
    if not float(qty).is_integer():
        plan["fraction_note"] = ("You hold %g shares. Revolut limit orders take whole shares only, so the orders above cover %d; the remaining %g of a share is sold with a market order "
                                 "when a level is reached. If the app also takes the fraction in the stop order, include it there.") % (qty, math.floor(qty), round(qty - math.floor(qty), 6))
    return plan


def idea_plan(c, label, fct, nav, lim, today):
    t = c.get("ticker")
    limit = float((c.get("cost") or {}).get("limit") or ((c.get("legs") or [{}])[0].get("limit")) or c.get("entry") or 0)
    stop, tp = c.get("stop"), c.get("take_profit")
    if not t or not limit or not stop or not tp:
        return None
    stop, tp = float(stop), float(tp)
    dn, up = 1 - stop / limit, tp / limit - 1
    size = float(c.get("profile_size") or 0) or (float(lim.get("risk_per_trade") or 0.015) * nav / dn if dn > 0 else 0)
    shares = math.floor(size / limit) if limit else 0
    cost = shares * limit
    valid = min(day(c["expires"]) if c.get("expires") else today + datetime.timedelta(days=14), today + datetime.timedelta(days=min(LABELS[label]["days"], REVOLUT_MAX_DAYS)))
    fc = forecast_for(fct, t, stop, tp)
    f_in, f_out = fee(cost), fee(cost * (1 + up))
    exp = (cost * (fc["tp_first"] * up - (fc.get("stop_first") or 0) * dn) - f_in - f_out) if (fc and cost) else None
    v = c.get("verdict") or {}
    plan = {"id": c.get("key"), "card": c.get("id"), "ticker": t, "held": False, "label": label, "title": c.get("title"), "limit": r2(limit), "valid_until": valid.isoformat(),
            "shares": shares, "cost": r2(cost), "size_allowed": r2(size), "stop": r2(stop), "take_profit": r2(tp),
            "stop_why": "twice the share's normal movement over ten days (at least 5%), from the card", "loss_at_stop": r2(shares * (limit - stop) + f_in + fee(shares * stop)) if shares else None,
            "loss_share_of_portfolio": r2((shares * (limit - stop)) / nav, 4) if (nav and shares) else None, "reward_risk": r2(up / dn, 2) if dn > 0 else None,
            "fees_in": f_in, "fees_out": f_out, "smallest_paying": c.get("min_size"), "pays": any(s.get("pays") for s in c.get("sizes") or []),
            "forecast": fc, "expected_after_fees": r2(exp), "verdict": v, "unproven": True,
            "revolut": revolut_steps(t, shares, limit, stop, tp, valid.isoformat(), False) if shares else [],
            "note": None if shares else "One share at $%.2f costs more than the $%.2f your risk profile allows for this stop, and Revolut limit orders take whole shares only." % (limit, size)}
    return plan


def default_label(plan_id, kept):
    if kept:
        return "long"
    if str(plan_id).startswith("RULE:"):
        return "short"
    if str(plan_id).startswith("H:"):
        return "long"
    return "medium"


def chosen_labels(answers, old):
    out = dict(old or {})
    for a in answers or []:
        if a.get("kind") == "label" and a.get("label") in LABELS and a.get("id"):
            out[a["id"]] = {"label": a["label"], "at": a.get("at")}
    return out


def watch(plans, prev, holds, today):
    # what needs you today: each event once, and a phone message only for new ones
    events = []
    old = dict((p["id"], p) for p in (prev or {}).get("holdings") or [] if p.get("id"))
    for p in plans:
        t, price = p["ticker"], p["price"]
        if p.get("stop") and price <= p["stop"]:
            events.append({"type": "hit", "id": p["id"], "key": "hit-stop:%s:%s" % (p["id"], p["stop"]),
                           "text": "%s closed at or under its stop ($%.2f)%s." % (t, p["stop"], ": your rules raise a sell card" if p.get("kept") else ": sell, or write down why you keep it")})
        if p.get("take_profit") and price >= p["take_profit"]:
            events.append({"type": "hit", "id": p["id"], "key": "hit-tp:%s:%s" % (p["id"], p["take_profit"]),
                           "text": "%s reached its take-profit ($%.2f)%s." % (t, p["take_profit"], ": your target, review your decision" if p.get("kept") else ": sell with a limit order, or move the stop up")})
        avg, first = p.get("average_cost"), p.get("initial_stop")
        if not p.get("kept") and avg and first and avg > first and price >= avg + (avg - first) and p["stop"] < avg:
            events.append({"type": "move", "id": p["id"], "key": "move:%s:%s" % (p["id"], r2(avg)),
                           "text": "Move the stop on %s up to $%.2f, your average cost: it is up by its first risk (trailing rule)." % (t, avg)})
            p["stop_should_be"] = r2(avg)
        if p.get("until") and day(p["until"]) < today:
            events.append({"type": "time", "id": p["id"], "key": "time:%s:%s" % (p["id"], p["until"]), "text": "%s: the plan's time limit (%s) has passed; review it." % (t, p["until"])})
        o = old.get(p["id"]) or {}
        a, b = (p.get("forecast") or {}).get("tp_first"), (o.get("forecast") or {}).get("tp_first")
        if a is not None and b is not None and abs(a - b) > PROB_MOVE:
            events.append({"type": "prob", "id": p["id"], "key": "prob:%s:%s" % (p["id"], today.isoformat()),
                           "text": "The Forecaster moved %s from %d%% to %d%% for reaching the take-profit first." % (t, round(100 * b), round(100 * a))})
        ne = (holds.get(t) or {}).get("next_earnings")
        if ne and 0 <= (day(ne) - today).days <= SOON_DAYS and (not p.get("until") or day(ne) <= day(p["until"])):
            gap = p["shares"] * price * 0.10
            act = "hold, your decision" if p.get("kept") else {"short": "close before the results", "medium": "reduce to half before the results", "long": "hold through the results"}[p["label"]]
            p["earnings"] = {"date": ne, "action": act, "gap_10pct": r2(gap)}
            events.append({"type": "earnings", "id": p["id"], "key": "earn:%s:%s" % (p["id"], ne),
                           "text": "%s reports on %s, inside its plan: %s. A 10%% gap at the open would cost about $%.2f and can open past the stop." % (t, ne, act, gap)})
    return events


def run(now, dec, answers=None, push=None):
    snap = E.rj("treasury/snapshot.json", {}) or {}
    prev = E.rj("state/plans.json", {}) or {}
    fct = (E.rj("state/forecasts.json", {}) or {}).get("targets") or {}
    nav = float(snap.get("nav") or 0)
    lim = ((dec.get("profile") or {}).get("limits")) or {}
    keeps, holds = dec.get("keeps") or {}, dec.get("holds") or {}
    labels = chosen_labels(answers, prev.get("labels"))
    today = day(now)
    old = dict((p["id"], p) for p in prev.get("holdings") or [] if p.get("id"))
    hp = []
    for p in snap.get("positions") or []:
        t = p.get("ticker")
        if not t:
            continue
        pid = "H:" + t
        lab = (labels.get(pid) or {}).get("label") or default_label(pid, t in keeps)
        x = holding_plan(p, holds.get(t), keeps.get(t), lab, E.read_cache(t), fct, nav, old.get(pid), today)
        if x:
            hp.append(x)
    ip = []
    for c in dec.get("cards") or []:
        if c.get("status") != "open" or c.get("kind") != "idea" or not c.get("ticker"):
            continue
        lab = (labels.get(c.get("key")) or {}).get("label") or default_label(c.get("key"), False)
        x = idea_plan(c, lab, fct, nav, lim, today)
        if x:
            ip.append(x)
    events = watch(hp, prev, holds, today)
    sent = dict((k, v) for k, v in (prev.get("sent") or {}).items() if (today - day(v)).days < 60)
    fresh = [e for e in events if e["key"] not in sent]
    note = prev.get("push_note")
    if fresh and push:
        kinds = {"hit": "a level was hit", "move": "a stop should move up", "time": "a time limit ran out", "prob": "a forecast moved", "earnings": "results are due inside a plan"}
        what = sorted(set(kinds[e["type"]] for e in fresh))
        note = push("Order plans: %d change%s" % (len(fresh), "" if len(fresh) == 1 else "s"), "Your order plans need a look: %s. Open the app, Portfolio > Plans." % ", ".join(what), "clipboard", now)
        if str(note).startswith("sent"):
            for e in fresh:
                sent[e["key"]] = today.isoformat()
    out = {"as_of": now, "holdings": hp, "ideas": ip, "short_term": [x for x in ip if x["label"] == "short"], "events": events, "sent": sent, "push_note": note,
           "labels": labels, "label_words": dict((k, v["name"] + ": " + v["words"]) for k, v in LABELS.items()), "revolut": REVOLUT,
           "method": __doc__.split("\n\n")[1].replace("\n", " ") + " " + __doc__.split("\n\n")[2].replace("\n", " ")}
    E.wj("state/plans.json", out)
    return out


def backtest(shares, step=5, cost=COST):
    # every fifth trading day of every share: enter at the close, stop and take-profit by the rule, exit at whichever is
    # reached first (the stop at that day's close, so a gap shows), or at the time limit; against simply holding the
    # same days. Prices only; dividends left out; today's survivors only, so results are flattered.
    import numpy as np
    rules = []
    for lab in ("short", "medium"):
        h = LABELS[lab]
        T, w = h["trading_days"], h["vol_days"]
        plan_r, hold_r, outcome, rec, gaps = [], [], [], [], []
        for s in shares:
            x = np.asarray(s.get("x"), dtype=float)
            if x.size < 300 or not np.all(np.isfinite(x)) or np.any(x <= 0):
                continue
            lr = np.diff(np.log(x))
            idx = np.arange(260, x.size - T - 1, step)
            if idx.size == 0:
                continue
            vol = np.array([lr[i - 20:i].std(ddof=1) for i in idx])
            dist = np.maximum(0.05, 2 * vol * np.sqrt(w))
            p0 = x[idx]
            path = np.stack([x[i + 1:i + 1 + T] for i in idx])
            stop, tp = p0 * (1 - dist), p0 * (1 + 2 * dist)
            hs, ht = path <= stop[:, None], path >= tp[:, None]
            ks = np.where(hs.any(1), hs.argmax(1), T)
            kt = np.where(ht.any(1), ht.argmax(1), T)
            for j in range(idx.size):
                if kt[j] < ks[j]:
                    ex, o = tp[j], "tp"
                elif ks[j] < T:
                    ex, o = path[j, ks[j]], "stop"
                    gaps.append(max(0.0, (stop[j] - ex) / p0[j]))
                    rec.append(bool((path[j, ks[j] + 1:] >= p0[j]).any()))
                else:
                    ex, o = path[j, -1], "time"
                plan_r.append(ex / p0[j] - 1 - cost)
                hold_r.append(path[j, -1] / p0[j] - 1 - cost)
                outcome.append(o)
        n = len(plan_r)
        if not n:
            continue
        pr, hr = np.array(plan_r), np.array(hold_r)
        st = outcome.count("stop")
        g = np.array(gaps) if gaps else np.array([0.0])
        rules.append({"id": lab, "name": "%s: stop at twice the normal movement over %d trading days (at least 5%%), take-profit at twice that distance, sell after %d trading days" % (h["name"].capitalize(), w, T),
                      "cases": n, "take_profit_first": r2(outcome.count("tp") / n, 3), "stop_first": r2(st / n, 3), "time_limit": r2(outcome.count("time") / n, 3),
                      "with_plan": r2(float(pr.mean()), 4), "without_plan": r2(float(hr.mean()), 4), "with_plan_median": r2(float(np.median(pr)), 4), "without_plan_median": r2(float(np.median(hr)), 4),
                      "plan_better_share": r2(float((pr > hr).mean()), 3), "stopped_then_recovered": r2(sum(rec) / st, 3) if st else None,
                      "gapped_past_stop": r2(float((g > 0.02).mean()), 3) if st else None, "average_gap": r2(float(g.mean()), 4) if st else None,
                      "verdict": ("With the plan the average case did %s than simply holding the same days, after costs (%+.2f%% against %+.2f%%)." % (
                          "better" if pr.mean() > hr.mean() else "worse", 100 * pr.mean(), 100 * hr.mean())) if n >= 20 else "Too few cases to rely on."})
    return {"rules": rules, "cost": cost,
            "method": "Every fifth trading day of every share in the back-check list since 2000 is a test entry at that day's close. The stop and take-profit follow the rule; the exit is whichever is reached first, the stop at that day's close (so gaps past the stop count), the take-profit at its price, otherwise the close at the time limit. Without the plan means holding the same days. Every result is after half a percent for buying and selling.",
            "honesty": "Entries are a fixed calendar, not the signals that raise cards, so this tests the stop and take-profit rule, not when to buy. Prices only: dividends are left out. The list is today's largest companies, so every share survived; that flatters holding more than stopping out. Neighbouring entries overlap, so cases are not independent."}
