"""Market Council action list: what to do right now, in numbers. Plain code; the agent only explains the result.

It invents no method. It takes what the system already has: the open decision cards (with their order plans: limit,
stop, take-profit, the size the risk profile allows, the paired sale that pays for them), the Forecaster's
probabilities, the back-check record of each check, the whole-portfolio figures (largest holding, bad year), the cash
in the books, the monthly contribution, the broker's fees and your standing decisions (a kept position is never
offered for sale). From these it builds numbered actions, each exactly one of BUY, SELL, SWAP or HOLD, ranked by the
expected result after fees:

    expected result = amount x (P(take-profit first) x gain at take-profit - P(stop first) x loss at stop) - fees both ways

Rule of 23 Oct 2026 (Ben): ideas that beat the same money in the index fund over the same time (the engine's index
assumption, after the same fees, with the Forecaster not below an even chance of beating it) always come first. An
idea that is expected to make money after fees is a BUY too, at the size the risk profile allows, labelled as
trailing the index fund. A holding is only sold to pay for an index-beating idea. When nothing is expected to make
money after fees, the top action is HOLD, with the reason.

The decision desk runs it after every cycle and writes state/actions.json. The inbox routine and the app ask it
questions:
    python3 ops/engine/actions.py ask "What should I do with 100000 HUF now?"
    python3 ops/engine/actions.py ask "Should I sell CHWY?"
Standard library only, so the routine can run it without the engine's other parts."""
import datetime
import json
import math
import os
import re
import sys

ROOT = os.environ.get("MC_ROOT", ".")
FEE_PCT, FEE_MIN = 0.0025, 1.12          # the broker's fee: 0.25% of the order, at least one euro, each way
TAX_RATE = 0.15                          # Hungarian personal income tax on share gains; losses this year offset gains
MIN_ORDER = 100.0                        # below this the minimum fee costs more than 1% each way
FOOT = "Output of your own system's rules and estimates. You decide and place every order."
STALE_FEEDS = ("desk", "screen", "quant", "books")
NOT_A_BUY = "Not a buy now: "
FRACTION = "A fraction of a share: Revolut takes limit orders for whole shares only, so place it as a market order while the US market is open."


def rj(rel, default=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def r2(x, n=2):
    return None if x is None else round(float(x), n)


def fee(usd, pct=None, low=None):
    # read the fee at call time: the desk's setting replaces the defaults after this module loads
    pct = FEE_PCT if pct is None else pct
    low = FEE_MIN if low is None else low
    return round(max(pct * usd, low), 2) if usd > 0 else 0.0


def usd_huf(fx):
    rates = (fx or {}).get("rates") or []
    return float(rates[-1]["usd_huf"]) if rates else None


def shares_for(usd, price):
    # whole shares when the money buys at least one; a fraction otherwise (Revolut may take fractions as market orders only)
    if not price or usd <= 0:
        return 0.0
    n = math.floor(usd / price)
    return float(n) if n >= 1 else math.floor(usd / price * 10000) / 10000.0


HWORDS = {"1m": "a month", "3m": "three months", "1y": "a year", "by": "the card's date"}


def fct_for(fct, t):
    f = (fct or {}).get(t) or {}
    if not f or f.get("none"):
        return None
    h, plan = f.get("h") or {}, f.get("plan") or {}
    # the take-profit / stop odds belong to the card's own horizon (the Forecaster's plan); the other odds to fixed horizons
    hk = plan.get("horizon") if plan.get("horizon") in h else next((k for k in ("by", "1y", "3m", "1m") if k in h), None)
    fh = (h.get(hk) or {}).get("f") or {}
    tp, sp = fh.get("tp_first") or {}, fh.get("stop_first") or {}
    beat = fh.get("beat") or ((h.get("1m") or {}).get("f") or {}).get("beat") or {}
    bh = hk if fh.get("beat") else "1m"
    return {"tp_first": tp.get("p"), "stop_first": sp.get("p"), "beat_index": beat.get("p"), "beat_over": HWORDS.get(bh, bh), "horizon": hk,
            "due": (h.get(hk) or {}).get("due") or plan.get("due"), "cases": tp.get("cases"), "few": bool(tp.get("few")),
            "range": [tp.get("lo"), tp.get("hi")] if tp else None}


def years_to(due, today):
    try:
        d = datetime.date.fromisoformat(str(due)[:10])
    except ValueError:
        return 1.0
    return max(1.0 / 12, (d - today).days / 365.25)


def evidence(card, track, fc):
    passed = [c.get("id") for c in card.get("checks") or [] if c.get("pass") is True]
    states = dict((k, (v or {}).get("state")) for k, v in ((track or {}).get("checks") or {}).items())
    proven = [i for i in passed if states.get(i) == "proven"]
    label = "proven" if passed and len(proven) == len(passed) else "unproven"
    n = (track or {}).get("count")
    txt = "%s: %d of its %d passed checks %s a proven record (%s ideas on paper so far)" % (
        label, len(proven), len(passed), "has" if len(proven) == 1 else "have", n if n is not None else "no")
    if fc and fc.get("cases"):
        txt += "; forecast from %s similar past cases%s" % ("{:,}".format(int(fc["cases"])), " (too few to rely on)" if fc.get("few") else "")
    return {"label": label, "passed": passed, "proven": proven, "ideas_on_paper": n, "text": txt}


def holding_map(snap):
    out = {}
    for p in (snap or {}).get("positions") or []:
        t = p.get("ticker")
        if not t:
            continue
        px = float(p.get("last_price") or 0)
        mv = float(p.get("market_value") or 0)
        q = p.get("qty")
        out[t] = {"qty": float(q) if q not in (None, "") else (mv / px if px else 0.0), "qty_known": q not in (None, ""), "price": px, "value": mv,
                  "cost": float(p.get("cost_basis") or 0), "price_as_of": p.get("price_as_of")}
    return out


def largest_after(hold, nav, add_t=None, add_usd=0.0, drop_t=None, extra_cash=0.0):
    vals = dict((t, h["value"]) for t, h in hold.items() if t != drop_t)
    if add_t:
        vals[add_t] = vals.get(add_t, 0.0) + add_usd
    tot = nav + extra_cash
    if not vals or tot <= 0:
        return None
    t = max(vals, key=lambda k: vals[k])
    return {"t": t, "share": r2(vals[t] / tot, 4)}


def candidates(ctx):
    # every open idea card as a candidate, with its numbers per dollar and the reasons it may be held back
    out = []
    hold, nav, lim = ctx["hold"], ctx["nav"], ctx["limits"]
    for c in ctx["cards"]:
        if c.get("kind") != "idea" or c.get("status") != "open" or not c.get("ticker") or c["ticker"] == "portfolio":
            continue
        t = c["ticker"]
        limit = float((c.get("cost") or {}).get("limit") or ((c.get("legs") or [{}])[0].get("limit")) or c.get("entry") or 0)
        if not limit:
            continue
        stop, tp = c.get("stop"), c.get("take_profit")
        fc = fct_for(ctx["fct"], t)
        up = (float(tp) / limit - 1) if tp else None
        dn = (1 - float(stop) / limit) if stop else None
        edge = None
        if fc and fc.get("tp_first") is not None and up is not None and dn is not None:
            edge = fc["tp_first"] * up - (fc.get("stop_first") or 0.0) * dn
        # the yardstick: the same money in the index fund until the same date, at the engine's index assumption
        years = years_to((fc or {}).get("due"), ctx.get("today") or datetime.date.today())
        index_edge = ctx.get("index_mu", 0.0861) * years
        # at most what the risk profile allows for one idea: the card's size, or the risk per trade over the stop distance
        cap = float(c.get("profile_size") or 0) or ((float(lim.get("risk_per_trade") or 0.015) * nav / dn) if dn else 0.0)
        room = float(lim.get("stock_cap") or 0.3) * nav - (hold.get(t) or {}).get("value", 0.0)
        cap = max(0.0, min(cap, room)) if cap else max(0.0, room)
        held_back, flags, disagree = [], [], []
        if c.get("greyed"):
            held_back.append(c.get("grey_reason") or "held back by the desk")
        pc = c.get("price_check") or {}
        if pc.get("ok") is False:
            held_back.append("price check failed: " + str(pc.get("why")))
        if c.get("stale"):
            held_back.append("its price is stale")
        if ctx["stale"]:
            held_back.append("data is stale: " + ", ".join(ctx["stale"]))
        if pc.get("ok") is None and pc:
            flags.append("price from one source only")
        if not fc:
            held_back.append("no forecast yet")
        ev = evidence(c, ctx["track"], fc)
        if ev["label"] == "unproven":
            flags.append("unproven")
        beat = (fc or {}).get("beat_index")
        if beat is not None and beat < 0.5:
            disagree.append("the card says buy, but the Forecaster gives it only %d%% to beat the index fund over %s" % (round(100 * beat), fc.get("beat_over")))
        pf = c.get("portfolio") or {}
        if pf.get("change") is not None and pf.get("index_change") is not None and pf["change"] > pf["index_change"]:
            disagree.append("the same money in the index fund would cut the bad year more (%+.1f against %+.1f points)" % (100 * pf["index_change"], 100 * pf["change"]))
        vs_index = None
        if edge is not None:
            vs_index = "expected %+.1f%% by %s if it follows its order plan (%d%% take-profit first, %d%% stop first), against %+.1f%% for the index fund over the same time" % (
                100 * edge, fc.get("due"), round(100 * fc["tp_first"]), round(100 * (fc.get("stop_first") or 0)), 100 * index_edge)
        fund = c.get("funding") or {}
        out.append({"t": t, "key": c.get("key"), "name": c.get("name"), "card": c.get("id"), "limit": round(limit, 2), "stop": stop, "take_profit": tp, "up": up, "dn": dn, "edge": edge,
                     "index_edge": index_edge, "years": round(years, 3), "vs_index": vs_index,
                     "sector": (ctx.get("sector") or {}).get(t), "new_sector": bool((ctx.get("sector") or {}).get(t)) and (ctx.get("sector") or {}).get(t) not in (ctx.get("held_sectors") or []),
                     "bad_change": pf.get("change"),
                     "cap": round(cap, 2), "fc": fc, "evidence": ev, "flags": flags, "disagree": disagree, "held_back": held_back,
                     "bad_per_usd": (pf["change"] / pf["size"]) if pf.get("change") is not None and pf.get("size") else None, "bad_before": pf.get("bad_before"),
                     "fund_sell": fund.get("sell") if fund.get("kind") == "paired_sale" else None, "fund_why": fund.get("why"),
                     "why": "; ".join(c.get("why") or [])[:300], "exit_rule": c.get("exit_rule"), "valid_until": c.get("expires")})
    return out


def beats_index(x):
    # expected to do better than the same money in the index fund, and the Forecaster does not rate it below an even chance
    beat = (x["fc"] or {}).get("beat_index")
    return x["edge"] is not None and x["edge"] > x["index_edge"] and not (beat is not None and beat < 0.5)


def qualifies(x):
    # Rule of 23 Oct 2026 (Ben): ideas that beat the index fund always come first; an idea expected to make money after
    # fees is a BUY too, labelled as trailing the index fund. Held-back ideas (stale data, no forecast, failed price
    # check) never qualify.
    return not x["held_back"] and x["edge"] is not None and x["edge"] > 0


def tier(x):
    return 1 if beats_index(x) else 2


def rank(x):
    # Rule of 23 Oct 2026 (Ben): index-beaters first; within each group, ideas from a sector not yet held come first,
    # then those that improve the bad year most, then the best expected result
    return (tier(x), 0 if x.get("new_sector") else 1, -(x.get("bad_change") or 0), -(x["edge"] or 0))


def mix_note(x, ctx):
    held = dict(((ctx.get("sector") or {}).get(t), t) for t in ctx["hold"]) if ctx.get("sector") else {}
    out = []
    if x.get("sector"):
        out.append(("adds a new sector (%s)" % x["sector"]) if x.get("new_sector") else ("same sector as your %s (%s)" % (held.get(x["sector"], "holdings"), x["sector"])))
    if x.get("bad_change") is not None and x.get("bad_before") is not None:
        out.append("bad year %.1f%% to %.1f%%" % (100 * x["bad_before"], 100 * (x["bad_before"] + x["bad_change"])))
    return (" Diversification: " + "; ".join(out) + ".") if out else ""


def mark_tier(a, x):
    # tier 1 beats the index fund; tier 2 makes money but trails it, and says so on the line
    a["tier"] = 1 if (tier(x) == 1 and (a.get("expected_usd") or 0) > (a.get("index_usd") or 0)) else 2
    if a["tier"] == 2:
        a["flags"].append("trails the index fund")
        a["line"] += " Makes money but trails the index fund: expected %s$%s against %s$%s for the same money in the index fund." % (
            "+" if (a.get("expected_usd") or 0) >= 0 else "-", money(abs(a.get("expected_usd") or 0)), "+" if (a.get("index_usd") or 0) >= 0 else "-", money(abs(a.get("index_usd") or 0)))
    return a


def reason(x):
    # the first reason an idea is not a BUY
    if x["held_back"]:
        r = x["held_back"][0]
    elif x["edge"] is not None and x["edge"] <= 0:
        r = x["vs_index"]
    elif x["edge"] is not None:
        r = "the fees take its expected gain at the size allowed (" + str(x["vs_index"]) + ")"
    else:
        r = (x["disagree"] or ["no forecast for it yet"])[0]
    r = str(r)
    if r.startswith(NOT_A_BUY):
        r = r[len(NOT_A_BUY):]
    return r.rstrip(". ")


def buy_line(x, usd, ctx, pays):
    sh = shares_for(usd, x["limit"])
    cost = round(sh * x["limit"], 2)
    if cost <= 0:
        return None
    f_in = fee(cost)
    f_out = fee(cost * (1 + (x["up"] or 0)))
    exp = cost * (x["edge"] or 0) - f_in - f_out
    idx = cost * x["index_edge"] - fee(cost) - fee(cost * (1 + x["index_edge"]))
    fx = ctx["fx"]
    bad = (x["bad_before"] + x["bad_per_usd"] * cost) if x["bad_per_usd"] is not None and x["bad_before"] is not None else None
    new_money = "new money" in pays
    a = {"type": "BUY", "ticker": x["t"], "shares": sh, "limit": x["limit"], "usd": cost, "huf": round(cost * fx) if fx else None, "fees": round(f_in, 2),
         "fees_both_ways": round(f_in + f_out, 2), "pays_with": pays, "stop": x["stop"], "take_profit": x["take_profit"],
         "if_take_profit": r2(cost * (x["up"] or 0) - f_in - f_out), "if_stop": r2(-cost * (x["dn"] or 0) - f_in - fee(cost * (1 - (x["dn"] or 0)))),
         "expected_usd": r2(exp), "index_usd": r2(idx), "forecast": x["fc"], "evidence": x["evidence"], "flags": list(x["flags"]), "disagree": list(x["disagree"]),
         "portfolio": {"largest": largest_after(ctx["hold"], ctx["nav"], x["t"], cost, extra_cash=cost if new_money else 0.0),
                       "bad_year": r2(bad, 4), "bad_year_now": x["bad_before"], "bad_note": "scaled from the card's own figure" if bad is not None else "not worked out for this idea"},
         "card": x["card"], "key": x.get("key"), "valid_until": x["valid_until"], "exit_rule": x["exit_rule"]}
    a["line"] = "BUY %s %s at limit $%.2f = $%s%s, fees $%.2f, paid from %s. Stop $%s, take-profit $%s." % (
        fmt_sh(sh), x["t"], x["limit"], money(cost), (" (%s HUF)" % "{:,}".format(a["huf"])) if a["huf"] else "", f_in, pays, money(x["stop"]), money(x["take_profit"]))
    if not float(sh).is_integer():
        a["flags"].append("fraction of a share")
        a["line"] += " " + FRACTION
    return a


def fmt_sh(s):
    return ("%d" % s) if float(s).is_integer() else ("%.4f" % s)


def money(v):
    return "-" if v is None else "{:,.2f}".format(float(v))


def sell_numbers(t, ctx, qty=None):
    h = ctx["hold"][t]
    q = h["qty"] if qty is None else min(qty, h["qty"])
    px = h["price"]
    gross = q * px
    f = fee(gross)
    cost_part = h["cost"] * (q / h["qty"]) if h["qty"] else 0.0
    gain = gross - f - cost_part
    tax = round(TAX_RATE * gain, 2) if gain > 0 else 0.0
    return {"shares": round(q, 6), "limit": round(px, 2), "gross": round(gross, 2), "fees": f, "proceeds": round(gross - f, 2), "gain": round(gain, 2),
            "tax": tax, "tax_note": ("about $%.2f tax (15%% of the $%.2f gain), unless losses this year offset it" % (tax, gain)) if gain > 0 else
            ("a loss of $%.2f: no tax; it offsets other gains this year" % -gain), "qty_known": h["qty_known"], "price_as_of": h["price_as_of"]}


def swap_line(x, ctx):
    s = x["fund_sell"]
    sfc = fct_for(ctx["fct"], s) or {}
    why = "%s is %s. %s" % (x["t"], x["vs_index"], x["fund_why"] or "")
    if sfc.get("beat_index") is not None:
        why += " The Forecaster gives %s %d%% to beat the index fund over %s." % (s, round(100 * sfc["beat_index"]), sfc.get("beat_over"))
    return swap_for(x, s, ctx, why)


# Ben, 29 Oct 2026: "add a sell this stock, buy this one instead option". A holding is swapped for an idea that is
# clearly better: the Forecaster's middle outcome in a year beats the holding's by SWAP_MARGIN after the switch costs.
# Never for a kept holding (UBER), never for a share bought in the last BOUGHT_DAYS (you just followed the list).
SWAP_MARGIN = 0.05
BOUGHT_DAYS = 30


def mid_1y(t, ctx):
    # the Forecaster's middle outcome in a year (half its simulated paths end above it) and its odds to beat the index fund
    f = (ctx["fct"] or {}).get(t) or {}
    h = (f.get("h") or {}).get("1y") or {}
    if f.get("none") or not f.get("price") or h.get("median") is None:
        return None
    return {"ret": float(h["median"]) / float(f["price"]) - 1, "beat": ((h.get("f") or {}).get("beat") or {}).get("p")}


def swap_choices(x, ctx, used=()):
    mx = mid_1y(x["t"], ctx)
    if not mx or not qualifies(x):
        return []
    out = []
    for s in sorted(ctx["hold"]):
        if s == x["t"] or s in ctx["keeps"] or s in (ctx.get("recent_buys") or ()) or s in used:
            continue
        ms = mid_1y(s, ctx)
        sn = sell_numbers(s, ctx)
        if not ms or sn["proceeds"] < 1:
            continue
        cost = (sn["fees"] + sn["tax"] + fee(min(sn["proceeds"], x["cap"]))) / sn["proceeds"]
        margin = mx["ret"] - ms["ret"] - cost
        if margin >= SWAP_MARGIN:
            out.append({"sell": s, "margin": margin, "cost": cost, "new": mx, "old": ms})
    return sorted(out, key=lambda o: -o["margin"])


def swap_better(x, o, ctx):
    s, mx, ms = o["sell"], o["new"], o["old"]
    why = "in a year the Forecaster's middle outcome is %+.1f%% for %s against %+.1f%% for %s; after the switch costs (%.1f%%) that is %.1f points better (estimates)." % (
        100 * mx["ret"], x["t"], 100 * ms["ret"], s, 100 * o["cost"], 100 * o["margin"])
    if mx.get("beat") is not None and ms.get("beat") is not None:
        why += " Odds to beat the index fund over a year: %d%% for %s, %d%% for %s." % (round(100 * mx["beat"]), x["t"], round(100 * ms["beat"]), s)
    a = swap_for(x, s, ctx, why)
    if a:
        a["margin"] = r2(o["margin"], 4)
        left = round(x["cap"] - a["usd"], 2)
        if left >= 10:
            a["line"] += " Another $%s of %s from new money would fill it up to its limit." % (money(left), x["t"])
    return a


def swap_for(x, s, ctx, why):
    if s not in ctx["hold"] or s in ctx["keeps"]:
        return None
    sn = sell_numbers(s, ctx)
    budget = min(sn["proceeds"], x["cap"])
    b = buy_line(x, budget, ctx, "the sale of %s" % s)
    if not b:
        return None
    net = round(sn["proceeds"] - b["usd"] - b["fees"], 2)
    a = dict(b)
    a.update({"type": "SWAP", "sell": dict(sn, ticker=s), "buy": {"ticker": x["t"], "shares": b["shares"], "limit": b["limit"], "usd": b["usd"]},
              "net_cash": net, "fees": round(sn["fees"] + b["fees"], 2), "why_better": why,
              "portfolio": dict(b["portfolio"], largest=largest_after(ctx["hold"], ctx["nav"], x["t"], b["usd"], drop_t=s))})
    a["line"] = "SWAP: sell %s %s at $%.2f (proceeds $%s after fees, %s), buy %s %s at limit $%.2f ($%s). Net cash %s$%s, fees $%.2f in all." % (
        fmt_sh(sn["shares"]), s, sn["limit"], money(sn["proceeds"]), sn["tax_note"], fmt_sh(b["shares"]), x["t"], x["limit"], money(b["usd"]),
        "+" if net >= 0 else "-", money(abs(net)), a["fees"])
    return a


def hold_keep(t, ctx):
    k = ctx["keeps"][t]
    h = ctx["hold"].get(t) or {}
    pfk = (ctx["pf"].get("keeps") or {}).get(t) or {}
    a = {"type": "HOLD", "ticker": t, "shares": r2(h.get("qty"), 6), "usd": r2(h.get("value")), "decision": True, "target": k.get("target"), "review_by": k.get("by"),
         "chance_touch": k.get("chance_touch"), "chance_above_on_date": k.get("chance_above_on_date"),
         "portfolio": {"share": pfk.get("share") or r2(h.get("value", 0) / ctx["nav"], 4) if ctx["nav"] else None, "cap": pfk.get("cap"),
                       "bad_year": pfk.get("bad_as_held"), "bad_year_at_cap": pfk.get("bad_at_cap")}}
    hp = (ctx["holds"].get(t) or {})
    floor = next((l.get("price") for l in hp.get("levels") or [] if "Maximum-loss" in str(l.get("name"))), None)
    a["line"] = "HOLD %s: your decision. Target $%s by %s; the model gives %s to touch it first." % (
        t, money(k.get("target")), k.get("by"), ("%d%%" % round(100 * k["chance_touch"])) if k.get("chance_touch") is not None else "no figure")
    eff = []
    if pfk.get("share") and pfk.get("cap"):
        eff.append("it is %d%% of the portfolio against your %d%% limit" % (round(100 * pfk["share"]), round(100 * pfk["cap"])))
    if pfk.get("bad_as_held") is not None and pfk.get("bad_at_cap") is not None:
        eff.append("bad year %.1f%% as held, %.1f%% if it were at the limit" % (100 * pfk["bad_as_held"], 100 * pfk["bad_at_cap"]))
    if floor:
        eff.append("your rules raise a sell card only below $%s (maximum-loss line)" % money(floor))
    a["effect"] = "Measured effect of keeping it: " + "; ".join(eff) + "." if eff else None
    return a


def hold_top(reason, ctx):
    return {"type": "HOLD", "ticker": None, "line": "HOLD: do nothing today. " + reason, "reason": reason}


def build_ctx(dec=None):
    dec = dec if dec is not None else rj("state/decisions.json", {}) or {}
    snap = rj("treasury/snapshot.json", {}) or {}
    fx = usd_huf(rj("state/fx.json", {}))
    contrib = rj("state/contribution.json", {}) or {}
    health = rj("state/health.json", {}) or {}
    fee_cfg = (dec.get("desk") or {}).get("fee") or {}
    global FEE_PCT, FEE_MIN
    # a fee of exactly 0 is a real setting, so only a missing value falls back to the default
    FEE_PCT = float(fee_cfg["pct"]) if fee_cfg.get("pct") is not None else FEE_PCT
    FEE_MIN = float(fee_cfg["min_usd"]) if fee_cfg.get("min_usd") is not None else FEE_MIN
    nav, cash = float(snap.get("nav") or 0), float(snap.get("cash") or 0)
    lim = ((dec.get("profile") or {}).get("limits")) or {}
    stale = [d.get("name") or d.get("id") for d in health.get("data") or [] if d.get("stale") and (d.get("id") in STALE_FEEDS)]
    huf = float(contrib.get("amount") or 0) if str(contrib.get("currency") or "HUF").upper() == "HUF" else None
    # sectors, for diversification: the wide screen's rows and the engine's assets
    sector = dict((r.get("t"), r.get("sector")) for r in (rj("state/screen.json", {}) or {}).get("rows") or [] if r.get("t") and r.get("sector"))
    for t, a in ((rj("state/quant.json", {}) or {}).get("assets") or {}).items():
        if a.get("sector") and t not in sector:
            sector[t] = a.get("sector")
    return {"dec": dec, "cards": dec.get("cards") or [], "fct": (rj("state/forecasts.json", {}) or {}).get("targets") or {}, "track": rj("state/track.json", {}) or {},
            "hold": holding_map(snap), "nav": nav, "cash": cash, "limits": lim, "keeps": dec.get("keeps") or {}, "holds": dec.get("holds") or {},
            "pf": dec.get("portfolio_first") or {}, "fx": fx, "stale": stale, "free_cash": max(0.0, cash - float(lim.get("min_cash") or 0.03) * nav),
            "monthly_huf": huf, "monthly_usd": (huf / fx) if huf and fx else None, "spy": dec.get("spy_price"),
            "today": datetime.datetime.now(datetime.timezone.utc).date(),
            "index_mu": float(((rj("state/quant.json", {}) or {}).get("opt") or {}).get("rf") or 0.04) + 0.05,
            "books_as_of": snap.get("as_of"), "desk_as_of": dec.get("as_of"), "sector": sector, "recent_buys": recent_buys(rj("treasury/ledger.json", {}) or {}),
            "held_sectors": sorted(set(sector.get(p.get("ticker")) for p in snap.get("positions") or [] if sector.get(p.get("ticker"))))}


def recent_buys(ledger):
    cut = (datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=BOUGHT_DAYS)).isoformat()
    return set(e["ticker"] for e in ledger.get("entries") or [] if e.get("action") == "buy" and e.get("status") == "applied"
               and e.get("ticker") and not e.get("undone_by") and str(e.get("at"))[:10] >= cut)


def number(acts):
    for i, a in enumerate(acts, 1):
        a["n"] = i
    return acts


def today(ctx):
    cands = candidates(ctx)
    good = sorted([x for x in cands if qualifies(x)], key=rank)
    acts, cash, used, sold = [], ctx["free_cash"], {}, set()
    for x in good:
        if x.get("sector") and x["sector"] in used:
            x["skip_reason"] = "for diversification: %s is already in this list for %s" % (used[x["sector"]], x["sector"])
            continue
        # a holding is only sold to pay for an idea that beats the index fund
        a = swap_line(x, ctx) if (x["fund_sell"] and tier(x) == 1) else None
        if not a:
            ch = swap_choices(x, ctx, sold)
            a = swap_better(x, ch[0], ctx) if ch else None
        if a:
            sold.add(a["sell"]["ticker"])
        if not a:
            usd = min(x["cap"], cash) if cash >= MIN_ORDER else x["cap"]
            pays = "free cash" if cash >= MIN_ORDER else ("new money: the next monthly %s HUF" % "{:,.0f}".format(ctx["monthly_huf"]) if ctx["monthly_huf"] else "new money")
            a = buy_line(x, usd, ctx, pays)
            if a and pays == "free cash":
                cash -= a["usd"] + a["fees"]
            if a and x["t"] in ctx["hold"]:
                a["line"] += " You already hold $%s of %s; this adds to it." % (money(ctx["hold"][x["t"]]["value"]), x["t"])
        if a and a["expected_usd"] is not None and a["expected_usd"] > 0:
            a["line"] += mix_note(x, ctx)
            acts.append(mark_tier(a, x))
            if x.get("sector"):
                used[x["sector"]] = x["t"]
    if not acts:
        acts.append(hold_top(why_nothing(cands, ctx), ctx))
    acts += [hold_keep(t, ctx) for t in sorted(ctx["keeps"]) if t in ctx["hold"]]
    return number(acts), cands


def swap_options(cands, acts, ctx, n=3):
    # every other clearly-better swap, best first, for "sell this, buy this instead"
    have = set((a["sell"]["ticker"], a["buy"]["ticker"]) for a in acts if a["type"] == "SWAP")
    out = []
    for x in cands:
        if x.get("skip_reason"):
            continue
        for o in swap_choices(x, ctx):
            if (o["sell"], x["t"]) not in have:
                a = swap_better(x, o, ctx)
                if a:
                    out.append(a)
    out = sorted(out, key=lambda a: -a["margin"])[:n]
    for i, a in enumerate(out):
        a["n"], a["option"] = "ABC"[i], True
    return out


def verdicts_from(ctx):
    # the decision desk's one judge: a card is a BUY only if it is in today's action list; otherwise it carries the reason
    acts, cands = today(ctx)
    by_key = dict((a.get("key"), a) for a in acts if a["type"] in ("BUY", "SWAP") and a.get("key"))
    out = {}
    for x in cands:
        a = by_key.get(x.get("key"))
        if a:
            out[x["key"]] = {"buy": True, "n": a["n"], "type": a["type"], "line": a["line"], "expected_usd": a.get("expected_usd"), "index_usd": a.get("index_usd")}
        elif x.get("key"):
            out[x["key"]] = {"buy": False, "why": x.get("skip_reason") or reason(x)}
    return out


def as_open(cards):
    # the desk calls this with fresh ideas, which have no status yet: judge them as open cards
    return [dict(c, status=c.get("status") or "open") for c in cards]


def verdicts(cards, keeps=None, limits=None, fee_pct=None, fee_min=None):
    return verdicts_from(build_ctx({"cards": as_open(cards), "keeps": keeps or {}, "profile": {"limits": limits or {}},
                                    "desk": {"fee": {"pct": fee_pct, "min_usd": fee_min}}}))


def why_nothing(cands, ctx):
    if ctx["stale"]:
        return "Data is stale (%s), so every buy waits until it updates." % ", ".join(ctx["stale"])
    if not cands:
        return "There is no open idea card, so nothing beats what you hold or the index fund after fees."
    parts = ["%s: %s" % (x["t"], reason(x)) for x in cands[:6]]
    return "No idea is expected to make money after fees. " + "; ".join(parts) + "."


def plan_amount(usd, ctx, label=None):
    # spread an amount of new money over the ideas that qualify, best expected result first, each at most what the risk
    # profile allows for one idea; whatever is left goes to the index fund, the yardstick everything is measured against
    cands = candidates(ctx)
    good = sorted([x for x in cands if qualifies(x)], key=rank)
    acts, left, used = [], usd, set()
    for x in good:
        if x.get("sector") and x["sector"] in used:
            continue
        put = min(x["cap"], left)
        if put < max(MIN_ORDER, x["limit"] if x["limit"] < 1000 else MIN_ORDER):
            continue
        a = buy_line(x, put, ctx, "the new money")
        if a and a["expected_usd"] is not None and a["expected_usd"] > 0:
            a["line"] += mix_note(x, ctx)
            acts.append(mark_tier(a, x))
            used.add(x.get("sector"))
            left -= a["usd"] + a["fees"]
    whole = not acts
    if left >= MIN_ORDER and ctx.get("spy"):
        sh = shares_for(left - fee(left), float(ctx["spy"]))
        cost = round(sh * float(ctx["spy"]), 2)
        if cost > 0:
            acts.append({"type": "BUY", "ticker": "SPY", "shares": sh, "limit": round(float(ctx["spy"]), 2), "usd": cost, "huf": round(cost * ctx["fx"]) if ctx["fx"] else None,
                         "fees": fee(cost), "pays_with": "the rest of the new money", "flags": ["index fund: no edge claimed"], "evidence": {"label": "benchmark", "text": "the S&P 500 index fund every idea is measured against"},
                         "expected_usd": r2(cost * ctx.get("index_mu", 0.0861) - 2 * fee(cost)), "expected_note": "over a year at the engine's index assumption (%.1f%% a year)" % (100 * ctx.get("index_mu", 0.0861)),
                         "portfolio": {"largest": largest_after(ctx["hold"], ctx["nav"], "SPY", cost, extra_cash=usd)},
                         "line": "BUY %s SPY (S&P 500 index fund) at limit $%.2f = $%s%s, fees $%.2f: %s.%s" % (fmt_sh(sh), float(ctx["spy"]), money(cost), (" (%s HUF)" % "{:,}".format(round(cost * ctx["fx"]))) if ctx["fx"] else "", fee(cost),
                                                                                                                  "the whole amount, because no idea beats the index fund" if whole else "the rest of the money, where no further idea beats the index fund",
                                                                                                                  "" if float(sh).is_integer() else " " + FRACTION)})
            if whole:
                best = sorted([x for x in cands if x["edge"] is not None and not x["held_back"]], key=lambda x: -(x["edge"] - x["index_edge"]))[:2]
                if best:
                    acts[-1]["disagree"] = []
                    acts[-1]["closest"] = ["%s: %s" % (x["t"], x["vs_index"]) for x in best]
            left -= cost + fee(cost)
    if not acts:
        acts.append(hold_top(why_nothing(cands, ctx) + " Keep the money as cash.", ctx))
    elif left > 0.5:
        acts.append({"type": "HOLD", "ticker": None, "usd": round(left, 2), "line": "HOLD the remaining $%s as cash (too small for an order whose fee stays under 1%%)." % money(left)})
    return number(acts)


def should_sell(t, ctx):
    t = t.upper()
    if t not in ctx["hold"]:
        return number([{"type": "HOLD", "ticker": t, "line": "You do not hold %s, so there is nothing to sell." % t}])
    if t in ctx["keeps"]:
        return number([hold_keep(t, ctx)])
    sn = sell_numbers(t, ctx)
    swaps = [swap_line(x, ctx) for x in candidates(ctx) if qualifies(x) and x["fund_sell"] == t]
    swaps = [s for s in swaps if s]
    if not swaps:
        for x in candidates(ctx):
            ch = [o for o in swap_choices(x, ctx) if o["sell"] == t]
            swaps += [s for s in [swap_better(x, ch[0], ctx) if ch else None] if s]
    if swaps:
        return number(sorted(swaps, key=lambda a: -(a["expected_usd"] or 0))[:1])
    hp = ctx["holds"].get(t) or {}
    floor = next((l.get("price") for l in hp.get("levels") or [] if "Maximum-loss" in str(l.get("name"))), None)
    sfc = fct_for(ctx["fct"], t) or {}
    if floor and sn["limit"] <= float(floor):
        a = {"type": "SELL", "ticker": t, "line": "SELL %s %s at limit $%.2f: proceeds $%s after $%.2f fees; %s. It is below your maximum-loss line ($%s)." % (
            fmt_sh(sn["shares"]), t, sn["limit"], money(sn["proceeds"]), sn["fees"], sn["tax_note"], money(floor))}
        a.update(sn)
        a["portfolio"] = {"largest": largest_after(ctx["hold"], ctx["nav"], drop_t=t)}
        return number([a])
    beat = sfc.get("beat_index")
    why = "no idea is expected to do clearly better than it after the costs of switching%s, and it is above your maximum-loss line%s. Selling would cost $%.2f in fees%s." % (
        (" (and you bought it in the last %d days)" % BOUGHT_DAYS) if t in (ctx.get("recent_buys") or ()) else "", (" ($%s)" % money(floor)) if floor else "", sn["fees"], (" and about $%.2f tax" % sn["tax"]) if sn["tax"] else "")
    if beat is not None:
        why += " The Forecaster gives it %d%% to beat the index fund over %s." % (round(100 * beat), sfc.get("beat_over"))
    return number([{"type": "HOLD", "ticker": t, "line": "HOLD %s: %s" % (t, why[0].upper() + why[1:]), "if_sold": sn,
                    "portfolio": {"largest": largest_after(ctx["hold"], ctx["nav"], drop_t=t), "bad_year_if_sold": ((ctx["pf"].get("sells") or {}).get(t))}}])


STOP = {"NOW", "IT", "ON", "ALL", "A", "I", "SO", "ARE", "BE", "DO", "OR", "AND", "FOR", "THE", "BUY", "SELL", "HOW", "MUCH", "WITH", "WHAT", "USD", "HUF", "FT", "RN"}


def ticker_in(s, ctx):
    # a share named in the question: one the desk or the books know, or any word written in capitals
    known = set(ctx["hold"]) | set(c.get("ticker") for c in ctx["cards"] if c.get("ticker")) | set(ctx["fct"] or {})
    for w in re.findall(r"[A-Za-z.]{1,6}", s):
        if w.upper() in STOP:
            continue
        if w.upper() in known or (w.isupper() and len(w) >= 2):
            return w.upper()
    return None


def parse(q, ctx):
    s = (q or "").strip()
    m = re.search(r"sell\s+([A-Za-z.]{1,6})\b", s, re.I)
    if m:
        return ("sell", m.group(1).upper())
    # "buy MRK at 152" names a price, not an amount
    price = None
    pm = re.search(r"(?:\bat\b|@)\s*\$?\s*(\d+(?:[.,]\d+)?)", s, re.I)
    if pm:
        price = float(pm.group(1).replace(",", "."))
        s = s[:pm.start()] + s[pm.end():]
    t = ticker_in(s, ctx)
    if t and re.search(r"\b(buy|how much|add|put)\b", s, re.I):
        amt = parse_amount(s, ctx)
        return ("buy", (t, amt[1] if amt[0] == "amount" else None, price))
    return parse_amount(s, ctx)


def parse_amount(s, ctx):
    m = re.search(r"([$])?\s*([0-9][0-9 ,.]*)\s*(k\b)?\s*(huf|ft|forint|usd|dollars?|\$)?", s, re.I)
    if m and re.search(r"\d", m.group(2)):
        raw = m.group(2).strip().replace(" ", "")
        raw = raw.replace(",", "") if re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", raw) else raw.replace(".", "").replace(",", ".") if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", raw) else raw.replace(",", ".")
        try:
            v = float(raw)
        except ValueError:
            return ("today", None)
        if m.group(3):
            v *= 1000
        cur = (m.group(4) or "").lower()
        if m.group(1) or cur in ("usd", "dollar", "dollars", "$"):
            return ("amount", v)
        if cur in ("huf", "ft", "forint") or v >= 20000:
            return ("amount", v / ctx["fx"] if ctx["fx"] else None)
        return ("amount", v)
    return ("today", None)


def buy_one(t, usd, ctx, price=None):
    # "How much T should I buy?" / "Should I buy T for $X?": that idea's numbers, at what the risk profile allows unless
    # an amount is given; an amount above the limit is shown as asked, with the warning in one line
    x = next((c for c in candidates(ctx) if c["t"] == t), None)
    if not x:
        why = "%s has no open idea card, so your system has no order plan (limit, stop, take-profit) for it." % t
        if t in ctx["hold"]:
            why += " You hold it; ask \"Should I sell %s?\" for its numbers." % t
        return number([hold_top(why, ctx)])
    named = (" You named $%.2f, %.1f%% %s the plan's limit of $%.2f." % (price, abs(100 * (price / x["limit"] - 1)), "above" if price > x["limit"] else "below", x["limit"])) if price else ""
    if not qualifies(x):
        a = dict(hold_top("Do not buy %s now: %s." % (t, reason(x)), ctx), ticker=t, evidence=x["evidence"], forecast=x["fc"], disagree=x["disagree"])
        a["line"] = "HOLD: do not buy %s now. %s.%s" % (t, reason(x)[0].upper() + reason(x)[1:], named)
        return number([a])
    if usd is None:
        usd = min(x["cap"], ctx["free_cash"]) if ctx["free_cash"] >= MIN_ORDER else x["cap"]
        pays = "free cash" if ctx["free_cash"] >= MIN_ORDER and usd <= ctx["free_cash"] else "new money"
    else:
        pays = "free cash" if usd <= ctx["free_cash"] else "new money"
    a = buy_line(x, usd, ctx, pays)
    if not a:
        return number([hold_top("The amount is too small for one share of %s at $%.2f." % (t, x["limit"]), ctx)])
    if (a.get("expected_usd") or 0) <= 0:
        h = hold_top("Do not buy %s now: the fees take its expected gain at this size (expected %s$%s after fees)." % (t, "+" if (a.get("expected_usd") or 0) >= 0 else "-", money(abs(a.get("expected_usd") or 0))), ctx)
        h["line"] = "HOLD: do not buy %s now. The fees take its expected gain at this size.%s" % (t, named)
        return number([dict(h, ticker=t, evidence=x["evidence"], forecast=x["fc"])])
    mark_tier(a, x)
    a["line"] += named
    if usd > x["cap"] + 0.01:
        a["flags"].append("above your limit")
        a["line"] += " Warning: your risk profile allows at most $%s in this idea; this is $%s." % (money(x["cap"]), money(a["usd"]))
    return number([a])


def answer(q, ctx):
    kind, val = parse(q, ctx)
    if kind == "buy":
        acts, head = buy_one(val[0], val[1], ctx, val[2] if len(val) > 2 else None), "Should I buy %s?" % val[0]
    elif kind == "sell":
        acts, head = should_sell(val, ctx), "Should I sell %s?" % val
    elif kind == "amount" and val:
        acts = plan_amount(val, ctx)
        head = "What to do with $%s%s now" % (money(val), (" (%s HUF)" % "{:,.0f}".format(val * ctx["fx"])) if ctx["fx"] else "")
    else:
        acts, head = today(ctx)[0], "What to do right now"
    return {"q": q, "kind": kind, "head": head, "actions": acts}


def text(ans):
    lines = [ans["head"] + ("" if ans["head"].endswith("?") else ":")]
    for a in ans["actions"]:
        lines.append("%d. %s" % (a["n"], a["line"]))
        extra = []
        fc = a.get("forecast") or {}
        if fc.get("tp_first") is not None:
            extra.append("Forecaster: %d%% take-profit first, %d%% stop first by %s" % (round(100 * fc["tp_first"]), round(100 * (fc.get("stop_first") or 0)), fc.get("due")))
        if a.get("expected_usd") is not None and a.get("if_take_profit") is not None:
            extra.append("expected after fees %s$%s, the same money in the index fund %s$%s (at take-profit %s, at stop %s)" % (
                "+" if a["expected_usd"] >= 0 else "-", money(abs(a["expected_usd"])), "+" if (a.get("index_usd") or 0) >= 0 else "-", money(abs(a.get("index_usd") or 0)),
                money(a.get("if_take_profit")), money(a.get("if_stop"))))
        elif a.get("expected_usd") is not None:
            extra.append("expected after fees %s$%s %s" % ("+" if a["expected_usd"] >= 0 else "-", money(abs(a["expected_usd"])), a.get("expected_note") or ""))
        p = a.get("portfolio") or {}
        if p.get("largest"):
            extra.append("largest holding after: %s %d%%" % (p["largest"]["t"], round(100 * p["largest"]["share"])))
        if p.get("bad_year") is not None and p.get("bad_year_now") is not None:
            extra.append("bad year %.1f%% (now %.1f%%)" % (100 * p["bad_year"], 100 * (p.get("bad_year_now") or 0)))
        if a.get("why_better"):
            extra.append("why: " + a["why_better"])
        if a.get("evidence"):
            extra.append(a["evidence"]["text"])
        if a.get("disagree"):
            extra.append("disagreement: " + "; ".join(a["disagree"]))
        if a.get("effect"):
            extra.append(a["effect"])
        if a.get("closest"):
            extra.append("Closest ideas: " + "; ".join(a["closest"]))
        if extra:
            extra = [x.strip().rstrip(".") for x in extra if x and x.strip()]
            lines.append("   " + ". ".join(x[0].upper() + x[1:] for x in extra) + ".")
    lines.append(FOOT)
    return "\n".join(lines)


def method_text(index_mu):
    return (__doc__.split("\n\n")[1].replace("\n", " ") + " The index fund is assumed to earn the safe rate plus 5%% a year (%.1f%% now), the engine's own"
            " assumption. Shares are whole where the money buys at least one. Tax is an estimate at 15%% of the gain." % (100 * index_mu))


def run(now=None, dec=None, spy_price=None):
    ctx = build_ctx(dec)
    if spy_price:
        ctx["spy"] = spy_price
    acts, cands = today(ctx)
    sells = dict((t, should_sell(t, ctx)) for t in sorted(ctx["hold"]))
    out = {"as_of": now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "books_as_of": ctx["books_as_of"], "desk_as_of": ctx["desk_as_of"],
           "actions": acts, "swap_options": swap_options(cands, acts, ctx), "sell_answers": sells, "stale": ctx["stale"],
           "monthly_answer": plan_amount(ctx["monthly_usd"], ctx) if ctx["monthly_usd"] else None,
           "inputs": {"cash": r2(ctx["cash"]), "free_cash": r2(ctx["free_cash"]), "nav": r2(ctx["nav"]), "usd_huf": r2(ctx["fx"], 4), "monthly_huf": ctx["monthly_huf"],
                      "monthly_usd": r2(ctx["monthly_usd"]), "fee_pct": FEE_PCT, "fee_min_usd": FEE_MIN, "min_order": MIN_ORDER, "tax_rate": TAX_RATE,
                      "stock_cap": ctx["limits"].get("stock_cap"), "min_cash": ctx["limits"].get("min_cash"), "spy": ctx["spy"], "keeps": sorted(ctx["keeps"]),
                      "index_mu": r2(ctx["index_mu"], 4)},
           "candidates": [dict((k, v) for k, v in x.items()) for x in cands],
           "method": method_text(ctx["index_mu"]),
           "foot": FOOT}
    with open(os.path.join(ROOT, "state", "actions.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "ask":
        c = build_ctx()
        c["spy"] = c["spy"] or (rj("state/actions.json", {}) or {}).get("inputs", {}).get("spy")
        print(text(answer(" ".join(sys.argv[2:]), c)))
    else:
        o = run()
        print(text({"head": "What to do right now", "actions": o["actions"]}))
