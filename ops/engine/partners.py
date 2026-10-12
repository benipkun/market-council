"""Market Council partner meetings: the one-page statement the partners read. Plain code, no AI.

The partners (an AI run, ops/PARTNERS.md in the records) judge; they never calculate and never invent a figure. Everything
they may quote is worked out here from the records: real money after fees, the same money in the index fund over the same
days, the paper record of every idea, the Forecaster's score, the running costs that have been entered, concentration and
the bad year, and the state of the machine itself. It also says when an emergency meeting is due.
Written by the decision desk on every run to state/partners/statement.json."""
import datetime
import os

import engine as E

FEE_PCT = 0.0025                 # one purchase fee charged to the index-fund alternative
DRAWDOWN = 0.15                  # an emergency meeting is due when the portfolio is this far under its high
STUCK_HOURS = 24                 # ... or when a job problem has stood this long


def money_flows(ledger):
    # money put in (+) and taken out (-), by day
    out = []
    for e in (ledger or {}).get("entries") or []:
        if e.get("action") in ("deposit", "withdraw") and e.get("usd") and e.get("status") == "applied":
            out.append((str(e.get("at"))[:10], float(e["usd"]) * (1.0 if e["action"] == "deposit" else -1.0)))
    return sorted(out)


def close_on(rows, day):
    # the last close on or before a day; rows are (day, close), oldest first
    v = None
    for d, c in rows:
        if d > day:
            break
        v = c
    return v


def index_alternative(days, flows, spy_rows, now_nav):
    # the same money in the index fund: the starting value buys the fund on the first day (one purchase fee), every
    # later payment in buys more and every withdrawal sells, each at that day's close
    if not days or not spy_rows:
        return None
    d0, nav0 = days[0]["date"], float(days[0]["nav"])
    p0, p1 = close_on(spy_rows, d0), spy_rows[-1][1]
    if not p0 or not p1:
        return None
    units, net = nav0 * (1 - FEE_PCT) / p0, 0.0
    for d, amt in flows:
        if d <= d0:
            continue
        p = close_on(spy_rows, d)
        if not p:
            continue
        units += (amt * (1 - FEE_PCT) if amt > 0 else amt) / p
        net += amt
    value = units * p1
    real = float(now_nav) - nav0 - net
    return {"from": d0, "to": spy_rows[-1][0], "start": E.rd(nav0, 2), "net_paid_in": E.rd(net, 2), "now": E.rd(float(now_nav), 2), "result": E.rd(real, 2),
            "result_pct": E.rd(real / nav0, 4) if nav0 else None, "index_now": E.rd(value, 2), "index_result": E.rd(value - nav0 - net, 2),
            "index_result_pct": E.rd((value - nav0 - net) / nav0, 4) if nav0 else None, "ahead_of_index": E.rd(float(now_nav) - value, 2)}


def drawdown(days, flows):
    # how far the portfolio is under its own high, with payments in and out taken out of the picture
    if len(days) < 2:
        return None
    idx, top, prev = 1.0, 1.0, days[0]
    for d in days[1:]:
        f = sum(a for x, a in flows if prev["date"] < x <= d["date"])
        if prev["nav"]:
            idx *= (float(d["nav"]) - f) / float(prev["nav"])
        top, prev = max(top, idx), d
    return E.rd(idx / top - 1, 4)


def run(now=None):
    now = now or E.now_iso()
    snap, ledger = E.rj("treasury/snapshot.json", {}) or {}, E.rj("treasury/ledger.json", {}) or {}
    days = (E.rj("state/nav_history.json", {}) or {}).get("days") or []
    dec, track, fc = E.rj("state/decisions.json", {}) or {}, E.rj("state/track.json", {}) or {}, E.rj("state/forecasts.json", {}) or {}
    health, costs = E.rj("state/health.json", {}) or {}, E.rj("state/partners/costs.json", {}) or {}
    flows, spy = money_flows(ledger), E.read_cache("SPY")
    nav = float(snap.get("nav") or 0)
    pos = snap.get("positions") or []
    unreal = sum(float(p.get("market_value") or 0) - float(p.get("cost_basis") or 0) for p in pos)
    rp = snap.get("realized_pl")
    realised = float((rp or {}).get("ytd") or 0) if isinstance(rp, dict) else float(rp or 0)
    trades = [e for e in ledger.get("entries") or [] if e.get("action") in ("buy", "sell") and e.get("status") == "applied"]
    fees = sum(float(e.get("fee") or 0) for e in trades)
    alt = index_alternative(days, flows, spy, nav) if nav else None
    dd = drawdown(days + ([{"date": str(snap.get("as_of"))[:10], "nav": nav}] if nav and days and str(snap.get("as_of"))[:10] > days[-1]["date"] else []), flows)
    pf = dec.get("portfolio_first") or {}
    three = ((track.get("all") or {}).get("3m")) or {}
    score, bt = fc.get("score") or {}, fc.get("backtest") or {}
    entries = costs.get("entries") or []
    month = sum(float(c.get("usd_per_month") or 0) for c in entries)
    problems = [p.get("text") for p in health.get("problems") or []]
    stuck = [p.get("text") for p in health.get("problems") or [] if str(p.get("key", "")).startswith("job:") and p.get("since")
             and (E_ts(now) - E_ts(p["since"])).total_seconds() > STUCK_HOURS * 3600]
    emergency = []
    if dd is not None and dd <= -DRAWDOWN:
        emergency.append("The portfolio is %s under its high (the level for an emergency meeting is %s)." % (E.pc(-dd, 1), E.pc(DRAWDOWN, 0)))
    emergency += ["A job problem has stood for more than %d hours: %s" % (STUCK_HOURS, t) for t in stuck]
    if alt:
        gap = alt["ahead_of_index"]
        line = "Since %s the portfolio has %s $%.2f; the same money in the index fund would have %s $%.2f. That is $%.2f %s the index fund, before running costs%s." % (
            alt["from"], "made" if alt["result"] >= 0 else "lost", abs(alt["result"]), "made" if alt["index_result"] >= 0 else "lost", abs(alt["index_result"]),
            abs(gap), "ahead of" if gap >= 0 else "behind",
            (" of $%.2f a month" % month) if entries else ", which have not been entered")
    else:
        line = "The comparison with the index fund could not be worked out this run (no value history or no index prices)."
    out = {
        "as_of": now,
        "period": {"from": alt["from"] if alt else None, "to": alt["to"] if alt else None, "days_of_record": len(days),
                   "note": "The record of the portfolio's value starts on %s. %d days is far too short to judge skill; it only shows where things stand." % (days[0]["date"], len(days)) if days else "No value history yet."},
        "real_money": {"value_now": E.rd(nav, 2), "cash": E.rd(float(snap.get("cash") or 0), 2), "unrealised": E.rd(unreal, 2), "realised_this_year": E.rd(realised, 2),
                       "fees_recorded": E.rd(fees, 2), "trades_recorded": len(trades),
                       "fee_note": ("No broker fee is recorded on %d trade%s. The broker's stated minimum is about $1.12 a trade, so the true result is probably a little worse than shown." % (
                           len(trades), "" if len(trades) == 1 else "s")) if (trades and fees == 0) else None,
                       "positions": [{"t": p.get("ticker"), "cost": E.rd(float(p.get("cost_basis") or 0), 2), "value": E.rd(float(p.get("market_value") or 0), 2),
                                      "gain": E.rd(float(p.get("market_value") or 0) - float(p.get("cost_basis") or 0), 2), "share": E.rd(float(p.get("pct_nav") or 0) / 100.0, 4)} for p in pos]},
        "against_index": alt,
        "paper_record": {"ideas_logged": track.get("count"), "first": track.get("first"), "verdict": track.get("verdict"), "three_months": three or None, "to_date": (track.get("all") or {}).get("now"),
                         "offered_to_date": (track.get("offered") or {}).get("now"), "dropped_checks": sorted((track.get("dropped") or {}).keys()), "proven_checks": track.get("proven") or [],
                         "log_unedited": track.get("intact")},
        "forecasts": {"logged": (fc.get("log") or {}).get("count"), "checked": score.get("checked"), "verdict": score.get("verdict"), "error": score.get("brier"),
                      "error_always_50": score.get("brier_fifty"), "error_plain_base_rate": score.get("brier_plain"), "log_unedited": (fc.get("log") or {}).get("intact"),
                      "backtest": {"cases": bt.get("checked"), "error": bt.get("brier"), "error_always_50": bt.get("brier_fifty"), "error_plain_base_rate": bt.get("brier_plain"), "verdict": bt.get("verdict")}},
        "running_costs": {"entries": entries, "usd_per_month": E.rd(month, 2) if entries else None, "known": bool(entries),
                          "note": None if entries else "No running cost has been entered (Claude subscription, data subscriptions, anything else paid). Until they are, nobody can say whether the operation pays for itself."},
        "bottom_line": line,
        "risk": {"largest": (pf.get("largest") or {}).get("t"), "largest_share": (pf.get("largest") or {}).get("share"), "bad_year": pf.get("bad_year"), "bad_year_days": pf.get("days"),
                 "kept": pf.get("keeps") or {}, "under_high": dd, "emergency_level": -DRAWDOWN},
        "machine": {"health_checked": health.get("as_of"), "all_running": health.get("ok"), "problems": problems,
                    "jobs": [{"name": j.get("name"), "last_good_run": j.get("last_ok"), "late": j.get("late"), "last_result": j.get("last_result")} for j in health.get("jobs") or []],
                    "results": [{"name": d.get("name"), "as_of": d.get("as_of"), "stale": d.get("stale")} for d in health.get("data") or []],
                    "price_check": {k: (dec.get("price_check") or {}).get(k) for k in ("checked", "agree", "held", "one_source")}},
        "desk": {"open_cards": len([c for c in dec.get("cards") or [] if c.get("status") == "open" and not c.get("greyed")]),
                 "greyed_cards": len([c for c in dec.get("cards") or [] if c.get("status") == "open" and c.get("greyed")])},
        "emergency": emergency,
        "method": "Every figure here is computed from the records by plain code. The index-fund figure puts the starting value into the S&P 500 fund on the first day of the record with one purchase fee, and repeats every later payment in or out on its own day. Unrealised gain is market value less cost for each holding. The bad year is the one-in-ten worst simulated year at today's weights."}
    os.makedirs(os.path.join(E.ROOT, "state", "partners"), exist_ok=True)
    E.wj("state/partners/statement.json", out)
    return out


def E_ts(s):
    return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
