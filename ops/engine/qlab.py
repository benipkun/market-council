"""QUANT LAB (Ben, 16 Nov 2026): every number tool in one place, run on request with Ben's own inputs.

The app saves a request as answers/qlab-<time>.json (kind "qlab": tool + inputs). The engine job on GitHub Actions runs
this file after the decision desk: plain code, no AI, no Claude credits. Each run is saved as state/qlab/runs/<id>.json
and listed in state/qlab/index.json, so past runs can be opened again. Every result carries its method, the number of
cases it rests on ("too few cases to rely on" under 20), how old its data is, and a label:
  LIVE    an estimate on today's real data (ranges, history check, earnings reaction)
  PAPER   a trading rule or signal that has not earned real money (back-tests, signals, pairs, learned signal)
  SAMPLE  for learning only (options: Ben's broker has no options)
A run Ben sends to the decision engine (answers/qlab-send-*.json) becomes a note on the action list for the same ticker.
It never places, sizes or changes an order.
"""
import datetime
import glob
import json
import math
import os
import re

import numpy as np

import engine as E
import lab
import quant

FEE, FEE_MIN = 0.0025, 1.0          # Revolut: 0.25% of the order, at least $1 (estimate, as in the rest of the engine)
RF, ERP = 0.0365, 0.05              # risk-free rate and the engine's equity premium: return = RF + beta x ERP
FEW = 20
MAX_PER_RUN = 6
LABEL_OF = {"backtest": "PAPER", "signals": "PAPER", "history": "LIVE", "montecarlo": "LIVE", "doomsday": "PAPER",
            "options": "SAMPLE", "pairs": "PAPER", "earnings": "LIVE", "learned": "PAPER", "events": "LIVE"}
TITLE = {"backtest": "Backtester", "signals": "Signals lab", "history": "History check", "montecarlo": "Monte Carlo",
         "doomsday": "Doomsday back-test", "options": "Options calculator", "pairs": "Pairs", "earnings": "Earnings reaction",
         "learned": "Learned signal", "events": "Event study"}
TICK = re.compile(r"^[A-Z0-9.^=@-]{1,12}$")


def r4(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


def tick(v, default=None):
    t = str(v or default or "").strip().upper()
    if not TICK.match(t):
        raise ValueError("not a ticker: %r" % v)
    return t


def fnum(v, default, lo, hi):
    try:
        x = float(v)
    except Exception:
        x = float(default)
    return max(lo, min(hi, x))


def prices(sym, long=True):
    """Daily closes: the long history (CNBC, from 2000) when asked, else the engine's five-year price file."""
    rows = []
    if long:
        try:
            import history
            rows = history.long_prices(sym)
        except Exception:
            rows = []
    if len(rows) < 300:
        rows = E.read_cache(sym) or rows
    if len(rows) < 300 and not E.OFFLINE:
        try:
            rows = E.load_prices(sym, True, {})
        except Exception:
            pass
    if len(rows) < 60:
        raise ValueError("no price history for %s" % sym)
    return [(str(d)[:10], float(v)) for d, v in rows if v and v > 0]


def age(rows):
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(rows[-1][0])).days
    except Exception:
        return None


def pcts(v):
    v = np.asarray(v)
    return {"typical": r4(np.median(v)), "bad_1_in_10": r4(np.percentile(v, 10)), "good_1_in_10": r4(np.percentile(v, 90)),
            "chance_of_loss": r4(np.mean(v < 0), 3)}


def fee_rate(amount):
    return max(FEE, FEE_MIN / max(1.0, amount))


# ---------------------------------------------------------------- 1. backtester
def t_backtest(inp):
    t = tick(inp.get("ticker"), "SPY")
    rule = str(inp.get("rule") or "trend200")
    if rule not in [r[0] for r in lab.RULES]:
        raise ValueError("unknown rule")
    years = fnum(inp.get("years"), 10, 2, 25)
    amount = fnum(inp.get("amount"), 1000, 100, 1e7)
    a, b = lab.align(prices(t), prices("SPY"))
    keep = int(years * 252) + lab.WARM
    a, b = a[-keep:], b[-keep:]
    if len(a) < lab.WARM + 260:
        raise ValueError("not enough shared history with the S&P 500 fund")
    dates, px = lab.arr(a)
    spx = lab.arr(b)[1]
    c = fee_rate(amount)
    old, lab.COST = lab.COST, c
    try:
        eq, trades, tin = lab.run(px, lab.signal(rule, px), lab.WARM)
        seq, _, _ = lab.run(spx, np.ones(len(spx)), lab.WARM)
    finally:
        lab.COST = old
    st, ss, half = lab.stats(eq), lab.stats(seq), len(eq) // 2
    h1 = (eq[half - 1] - 1) - (seq[half - 1] - 1)
    h2 = (eq[-1] / eq[half - 1] - 1) - (seq[-1] / seq[half - 1] - 1)
    beats = bool(st["total"] > ss["total"] and h1 > 0 and h2 > 0)
    name = dict((r[0], r[1]) for r in lab.RULES)[rule]
    idx, curve = lab.sample(eq)
    return {"ticker": t, "cases": trades, "case_word": "trades", "data_through": dates[-1], "data_age_days": age(a),
            "headline": "%s on %s: %s total against %s for the S&P 500 fund after fees (%s); %s." % (
                name, t, E.pc(st["total"], 0), E.pc(ss["total"], 0), "%d trades" % trades,
                "ahead in both halves" if beats else "not ahead in both halves, so no edge shown"),
            "table": [["", "Rule", "S&P 500 fund"], ["Total", E.pc(st["total"]), E.pc(ss["total"])], ["A year", E.pc(st["cagr"]), E.pc(ss["cagr"])],
                      ["Worst fall", E.pc(st["mdd"]), E.pc(ss["mdd"])], ["Worst 12 months", E.pc(st["worst_12m"]), E.pc(ss["worst_12m"])],
                      ["First half vs fund", E.pc(h1), ""], ["Second half vs fund", E.pc(h2), ""], ["Time in the market", E.pc(tin, 0), "100%"]],
            "curve": {"dates": [dates[lab.WARM + int(i)] for i in idx], "rule": curve, "spy": lab.sample(seq)[1]}, "beats": beats,
            "method": "Rule: %s. It decides at the close and holds over the next day; out of the market the money earns nothing. "
                      "Each change of position costs %.2f%% (Revolut 0.25%%, at least $1 on a $%.0f order). The S&P 500 fund is bought once "
                      "and held over the same %s days. Split-adjusted closes without dividends. The test is cut in two halves; a rule shows "
                      "an edge only if it is ahead in both." % (dict((r[0], r[2]) for r in lab.RULES)[rule], 100 * c, amount, len(eq))}


# ---------------------------------------------------------------- 2. signals lab
def t_signals(inp):
    t = tick(inp.get("ticker"), "SPY")
    want = str(inp.get("series") or "US 10-year yield")
    ser = next((s for s in lab.SERIES if s[0] == want or s[1] == want.upper()), None)
    if not ser:
        ser = (want, tick(want), bool(inp.get("is_rate")))
    ws, wk, wspy = lab.weekly(lab.outside(ser[1])), lab.weekly(prices(t, long=False)), lab.weekly(prices("SPY", long=False))
    keys = sorted(k for k in wk if k in ws and k in wspy)
    if len(keys) < 60:
        raise ValueError("fewer than 60 shared weeks for %s and %s" % (ser[0], t))
    xs, st, sp = (np.array([d[k] for k in keys]) for d in (ws, wk, wspy))
    dx = (xs[1:] - xs[:-1]) if ser[2] else (xs[1:] / xs[:-1] - 1)
    ex = (st[1:] / st[:-1] - 1) - (sp[1:] / sp[:-1] - 1)
    rows, best = [["Lead", "Weeks", "Correlation", "t first half", "t second half", "Holds?"]], None
    for lag in (1, 2, 3, 4):
        x, y = dx[:-lag], ex[lag:]
        h = len(x) // 2
        ra, ta = lab.tstat(x, y)
        _, t1 = lab.tstat(x[:h], y[:h])
        _, t2 = lab.tstat(x[h:], y[h:])
        holds = abs(t1) >= 2 and abs(t2) >= 2 and (t1 > 0) == (t2 > 0)
        rows.append(["%d week%s" % (lag, "" if lag == 1 else "s"), len(x), "%.2f" % ra, "%.1f" % t1, "%.1f" % t2, "yes" if holds else "no"])
        if holds and not best:
            best = lag
    return {"ticker": t, "cases": len(dx), "case_word": "weeks", "data_through": "%d-W%02d" % keys[-1], "data_age_days": age(prices(t, long=False)),
            "headline": ("%s leads %s by %d week%s in both halves of the history (a pattern, not a cause)." % (ser[0], t, best, "" if best == 1 else "s"))
            if best else "%s does not lead %s in a way that holds in both halves of the history." % (ser[0], t), "table": rows,
            "method": "Weekly changes of %s (%s) against %s's return minus the S&P 500 fund's, one to four weeks later. History cut in two: a "
                      "lead counts only if its t-statistic is 2 or more in both halves with the same sign. Four leads are tested, so one in "
                      "about 100 such runs passes by luck." % (ser[0], "in points" if ser[2] else "in percent", t)}


# ---------------------------------------------------------------- 3. history check
def feats(px):
    n = len(px)
    f = np.full((n, 4), np.nan)
    r = np.zeros(n)
    r[1:] = px[1:] / px[:-1] - 1
    for i in range(252, n):
        f[i, 0] = px[i] / px[i - 252] - 1
        f[i, 1] = px[i] / px[i - 21] - 1
        f[i, 2] = np.std(r[i - 19:i + 1], ddof=1) * math.sqrt(252)
        f[i, 3] = px[i] / np.mean(px[i - 199:i + 1]) - 1
    return f


def t_history(inp):
    t = tick(inp.get("ticker"), "SPY")
    k = int(fnum(inp.get("matches"), 30, 10, 60))
    rows = prices(t)
    srow = dict(prices("SPY"))
    dates = [d for d, v in rows]
    px = np.array([v for d, v in rows])
    f = feats(px)
    ok = ~np.isnan(f).any(axis=1)
    sd = np.nanstd(f[ok], axis=0)
    sd[sd == 0] = 1
    now = f[-1]
    dist = np.sqrt(np.nansum(((f - now) / sd) ** 2, axis=1))
    last = len(px) - 1 - 252                            # a match needs a full year after it
    order = [i for i in np.argsort(dist) if ok[i] and i <= last]
    pick = []
    for i in order:
        if all(abs(i - j) >= 63 for j in pick):
            pick.append(int(i))
        if len(pick) >= k:
            break
    out, tab = {}, [["After", "Typical", "Bad (1 in 10)", "Good (1 in 10)", "Rose", "S&P 500 fund typical"]]
    for name, h in (("1 month", 21), ("3 months", 63), ("12 months", 252)):
        v = np.array([px[i + h] / px[i] - 1 for i in pick])
        s = [srow[dates[i + h]] / srow[dates[i]] - 1 for i in pick if dates[i] in srow and dates[i + h] in srow]
        out[name] = pcts(v)
        tab.append([name, E.pc(out[name]["typical"]), E.pc(out[name]["bad_1_in_10"]), E.pc(out[name]["good_1_in_10"]),
                    E.pc(float(np.mean(v > 0)), 0), E.pc(float(np.median(s))) if s else "-"])
    today = {"12-month change": E.pc(now[0]), "1-month change": E.pc(now[1]), "20-day volatility (a year)": E.pc(now[2]), "Against the 200-day average": E.pc(now[3])}
    y = out["12 months"]
    return {"ticker": t, "cases": len(pick), "case_word": "past periods", "data_through": dates[-1], "data_age_days": age(rows),
            "headline": "%d past periods looked like %s today; 12 months later the typical result was %s (bad 1 in 10: %s, good: %s)." % (
                len(pick), t, E.pc(y["typical"]), E.pc(y["bad_1_in_10"]), E.pc(y["good_1_in_10"])),
            "today": today, "matches": [dates[i] for i in sorted(pick)], "table": tab, "outcomes": out, "from": dates[0],
            "method": "Today's setup of %s in four numbers: the 12-month and 1-month change, the 20-day volatility and the distance from "
                      "the 200-day average. Each is scaled by its own spread over the history (%s to %s); the %d closest past days at "
                      "least three months apart, each with a full year after it, are the matches. The table counts what followed them. "
                      "Past periods are not a forecast; an estimate." % (t, dates[0], dates[-1], len(pick))}


# ---------------------------------------------------------------- 4. Monte Carlo
def mc_position(inp, rng):
    t = tick(inp.get("ticker"), "SPY")
    years = fnum(inp.get("years"), 1, 0.1, 10)
    amount = fnum(inp.get("amount"), 1000, 1, 1e7)
    a, b = lab.align(prices(t, long=False), prices("SPY", long=False))
    px, sp = lab.arr(a)[1], lab.arr(b)[1]
    r, rs = px[1:] / px[:-1] - 1, sp[1:] / sp[:-1] - 1
    if len(r) < 300:
        raise ValueError("too little history for %s" % t)
    w = min(756, len(r))
    beta = float(np.cov(r[-w:], rs[-w:])[0, 1] / np.var(rs[-w:], ddof=1))
    mu = RF + max(0.0, beta) * ERP
    rc = r - np.mean(r) + mu / 252.0
    cs = np.concatenate([[0.0], np.cumsum(np.log1p(rc))])
    blocks = cs[quant.BLOCK:] - cs[:-quant.BLOCK]
    n = max(1, int(round(years * 252 / quant.BLOCK)))
    v = np.expm1(blocks[rng.integers(0, len(blocks), size=(10000, n))].sum(axis=1)) - 2 * fee_rate(amount)
    o = pcts(v)
    return {"ticker": t, "cases": len(r), "case_word": "trading days of history", "data_through": a[-1][0], "data_age_days": age(a),
            "headline": "$%.0f of %s over %s year%s: typical %s, bad (1 in 10) %s, good %s; chance of a loss %s." % (
                amount, t, ("%g" % years), "" if years == 1 else "s", E.pc(o["typical"]), E.pc(o["bad_1_in_10"]), E.pc(o["good_1_in_10"]), E.pc(o["chance_of_loss"], 0)),
            "table": [["", "Return", "Money"]] + [[k, E.pc(o[x]), "$%.0f" % (amount * (1 + o[x]))] for k, x in
                                                    (("Typical", "typical"), ("Bad (1 in 10)", "bad_1_in_10"), ("Good (1 in 10)", "good_1_in_10"))] +
                     [["Chance of a loss", E.pc(o["chance_of_loss"], 0), ""]], "outcomes": o,
            "method": "10,000 simulated futures from %s's own daily changes (%d days), drawn in unbroken 21-day blocks so bad stretches and "
                      "fat tails are kept, shifted to an assumed %.1f%% a year (risk-free %.2f%% + beta %.2f x %.0f%%, the engine's rule). "
                      "Buy and sell fees taken off. An estimate, not a promise." % (t, len(r), 100 * mu, 100 * RF, beta, 100 * ERP)}


def mc_portfolio(inp, rng):
    al = E.rj("state/allocation.json", {}) or {}
    A = al.get("assumptions") or {}
    if not A.get("mu"):
        raise ValueError("the part assumptions are not ready yet (state/allocation.json)")
    parts = ("stocks", "bonds", "etfs")
    split = dict((k, fnum(inp.get(k), (al.get("actual") or {}).get("pct", {}).get(k, 0), 0, 100)) for k in parts)
    tot = sum(split.values()) or 1
    split = dict((k, 100.0 * v / tot) for k, v in split.items())
    years = int(fnum(inp.get("years"), 5, 1, 30))
    amount = fnum(inp.get("amount"), (al.get("actual") or {}).get("invested") or 1000, 1, 1e8)
    mu = np.array([A["mu"][k] for k in parts])
    cov = np.array(A["cov"])
    w = np.array([split[k] / 100.0 for k in parts])
    # each year: a draw of the three parts' yearly returns (lognormal, with their correlations), rebalanced to the split
    L = np.linalg.cholesky(cov + 1e-10 * np.eye(3))
    z = rng.standard_normal((10000, years, 3)) @ L.T
    yr = np.exp(mu - np.diag(cov) / 2 + z) - 1
    v = np.prod(1 + yr @ w, axis=1) - 1
    one = pcts(yr[:, 0, :] @ w)
    o = pcts(v)
    lbl = "%.0f/%.0f/%.0f" % (split["stocks"], split["bonds"], split["etfs"])
    return {"ticker": None, "split": split, "cases": A.get("days"), "case_word": "trading days behind the assumptions", "data_through": A.get("to"),
            "data_age_days": age([(A.get("to"), 0)]) if A.get("to") else None,
            "headline": "Portfolio at %s over %d year%s: typical %s, bad (1 in 10) %s, good %s; chance of a loss %s. Bad single year (1 in 10): %s." % (
                lbl, years, "" if years == 1 else "s", E.pc(o["typical"]), E.pc(o["bad_1_in_10"]), E.pc(o["good_1_in_10"]), E.pc(o["chance_of_loss"], 0), E.pc(one["bad_1_in_10"])),
            "table": [["", "Return", "Money"]] + [[k, E.pc(o[x]), "$%.0f" % (amount * (1 + o[x]))] for k, x in
                                                    (("Typical", "typical"), ("Bad (1 in 10)", "bad_1_in_10"), ("Good (1 in 10)", "good_1_in_10"))] +
                     [["Chance of a loss", E.pc(o["chance_of_loss"], 0), ""], ["Bad single year (1 in 10)", E.pc(one["bad_1_in_10"]), ""]], "outcomes": o,
            "method": "10,000 simulated %d-year futures for the split STOCKS/BONDS/ETFs %s, rebalanced each year. Each year's returns are drawn "
                      "together (lognormal, with the parts' correlations) from the engine's part assumptions: %s Starting money $%.0f. "
                      "An estimate, not a promise." % (years, lbl, A.get("method", ""), amount)}


def t_montecarlo(inp):
    rng = np.random.default_rng(int(fnum(inp.get("seed"), 7, 0, 1e9)))
    return mc_portfolio(inp, rng) if str(inp.get("what") or "position") == "portfolio" else mc_position(inp, rng)


# ---------------------------------------------------------------- 5. doomsday back-test
def t_doomsday(inp):
    start = str(int(fnum(inp.get("from_year"), 2000, 1993, datetime.date.today().year - 3)))
    spy = [r for r in prices("SPY") if r[0] >= start]
    safe = [] if str(inp.get("safe") or "SHY") == "cash" else [r for r in prices("SHY") if r[0] >= start]
    d = lab.doomsday(spy, safe)
    if d.get("status") != "ok":
        raise ValueError("not enough history: %s" % d.get("status"))
    eps = d["episodes"]
    tab = [["Fall", "Holding the fund", "With the protocol", "Back to the peak"]] + [
        ["%s to %s" % (e["peak"], e["low"]), E.pc(e["hold_fall"]), E.pc(e["protocol_fall"]), e["back"] or "not yet"] for e in eps]
    h, p = d["hold"], d["protocol"]
    tab += [["Whole period, a year", E.pc(h["cagr"]), E.pc(p["cagr"]), ""], ["Worst fall overall", E.pc(h["mdd"]), E.pc(p["mdd"]), ""]]
    return {"ticker": "SPY", "cases": len(eps), "case_word": "falls of 10% or more", "data_through": d["to"], "data_age_days": age(spy),
            "headline": d["verdict"], "table": tab, "level_now": d["level_now"], "method": d["method"] + " Safe asset: %s." % d["safe_asset"]}


# ---------------------------------------------------------------- 6. options calculator (learning only)
def t_options(inp):
    t = str(inp.get("ticker") or "").strip().upper()
    S = fnum(inp.get("price"), 0, 0, 1e7)
    rows = []
    vol = None
    if t and TICK.match(t):
        try:
            rows = prices(t, long=False)
            S = S or rows[-1][1]
            px = np.array([v for d, v in rows[-253:]])
            vol = float(np.std(px[1:] / px[:-1] - 1, ddof=1) * math.sqrt(252))
        except Exception:
            rows = []
    if S <= 0:
        raise ValueError("give a ticker or a share price")
    K = fnum(inp.get("strike"), S, 0.01, 1e7)
    days = fnum(inp.get("days"), 30, 1, 1500)
    v = fnum(inp.get("vol"), 100 * (vol or 0.3), 1, 300) / 100.0
    r = fnum(inp.get("rate"), 100 * RF, 0, 20) / 100.0
    call = str(inp.get("type") or "call") != "put"
    T = days / 365.0
    rng = np.random.default_rng(7)
    bsv = quant.bs(S, K, T, r, v, call)
    am = quant.binom(S, K, T, r, v, call)
    mcv, mse = quant.mc_opt(S, K, T, r, v, call, rng)
    g = quant.greeks(S, K, T, r, v, call)
    kind = "call" if call else "put"
    return {"ticker": t or None, "cases": None, "case_word": None, "data_through": rows[-1][0] if rows else None, "data_age_days": age(rows) if rows else None,
            "headline": "A %d-day %s at $%.2f on a $%.2f share: fair price $%.2f (Black-Scholes); delta %.2f, theta $%.3f a day. For learning only." % (
                days, kind, K, S, bsv, g["delta"], g["theta"]),
            "table": [["", "Value"], ["Black-Scholes (European)", "$%.2f" % bsv], ["Binomial tree, early exercise (American)", "$%.2f" % am],
                      ["Monte Carlo, 40,000 paths", "$%.2f (+-%.2f)" % (mcv, 1.96 * mse)], ["Delta (per $1 move)", "%.3f" % g["delta"]],
                      ["Gamma", "%.4f" % g["gamma"]], ["Vega (per 1 point of volatility)", "$%.3f" % g["vega"]], ["Theta (per day)", "$%.3f" % g["theta"]],
                      ["Rho (per 1 point of rate)", "$%.3f" % g["rho"]], ["Volatility used", E.pc(v)]],
            "method": "Three standard ways to price the same option: the Black-Scholes formula, a 200-step binomial tree that allows early "
                      "exercise, and 40,000 simulated prices at expiry. Inputs: share $%.2f, strike $%.2f, %d days, volatility %.0f%% (%s), "
                      "rate %.2f%%, no dividends. Your broker has no options: this is a calculator for learning, not a trade." % (
                          S, K, days, 100 * v, "the share's last 12 months" if vol and not inp.get("vol") else "your input", 100 * r)}


# ---------------------------------------------------------------- 7. pairs finder and pair backtester
def pair_test(a, b, fit_share=0.6):
    x, y = lab.align(prices(a, long=False), prices(b, long=False))
    if len(x) < 500:
        return None
    pa, pb = np.log(lab.arr(x)[1]), np.log(lab.arr(y)[1])
    k = int(len(pa) * fit_share)
    hedge, c = np.polyfit(pb[:k], pa[:k], 1)
    e = pa - (hedge * pb + c)
    tstat, _ = quant.adf_t(e[:k])
    mu, sd = float(np.mean(e[:k])), float(np.std(e[:k], ddof=1))
    z = (e - mu) / sd
    test = quant.trade_pair(z[k:], e[k:], hedge)
    return {"a": a, "b": b, "hedge": r4(hedge, 3), "adf_t": r4(tstat, 2), "stable": bool(tstat < -3.34), "test": test,
            "corr": r4(float(np.corrcoef(np.diff(pa), np.diff(pb))[0, 1]), 2), "z_now": r4(z[-1], 2), "days": len(pa), "fit_days": k, "through": x[-1][0]}


def t_pairs(inp):
    tick_list = [tick(s) for s in re.split(r"[ ,;]+", str(inp.get("tickers") or "")) if s.strip()][:10]
    if len(tick_list) < 2:
        held = [p.get("ticker") for p in (E.rj("treasury/snapshot.json", {}) or {}).get("positions", []) if p.get("ticker")]
        tick_list = (held + ["SPY", "IEF"])[:10]
    res = []
    for i in range(len(tick_list)):
        for j in range(i + 1, len(tick_list)):
            try:
                p = pair_test(tick_list[i], tick_list[j])
            except Exception:
                p = None
            if p:
                res.append(p)
    if not res:
        raise ValueError("no pair had two years of shared history")
    res.sort(key=lambda p: p["adf_t"])
    n = sum(p["test"]["n"] for p in res[:1])
    tab = [["Pair", "Stable?", "ADF t", "Trades after the fit", "Average trade", "Wins", "Now (z)"]] + [
        ["%s / %s" % (p["a"], p["b"]), "yes" if p["stable"] else "no", "%.2f" % p["adf_t"], p["test"]["n"],
         E.pc(p["test"]["avg"]) if p["test"]["avg"] is not None else "-", E.pc(p["test"]["win"], 0) if p["test"]["win"] is not None else "-", "%.1f" % p["z_now"]] for p in res[:12]]
    b = res[0]
    return {"ticker": None, "cases": n, "case_word": "trades of the best pair after the fit", "data_through": b["through"], "data_age_days": None,
            "headline": "Best pair %s / %s: %s (ADF t %.2f); %d test trades after the fit, average %s. Paper only: a pair needs a short sale, which is off in your profile." % (
                b["a"], b["b"], "a stable spread" if b["stable"] else "no stable spread", b["adf_t"], b["test"]["n"], E.pc(b["test"]["avg"]) if b["test"]["avg"] is not None else "-"),
            "table": tab, "pairs": res[:12],
            "method": "Every pair of %s. Log prices; the hedge ratio is fitted on the first 60%% of the shared history and the spread tested "
                      "for stability there (Engle-Granger, ADF t below -3.34 = stable at 5%%). The rule then trades only the last 40%%, which "
                      "the fit never saw: enter at 2 standard deviations, leave at the average or at 4 (stop), 0.5%% cost a round trip." % ", ".join(tick_list)}


# ---------------------------------------------------------------- 8. earnings reaction model
def t_earnings(inp):
    import earnings
    t = tick(inp.get("ticker"), "UBER")
    hist = E.rj("state/earnings/history/%s.json" % t, {}) or {}
    rows = hist.get("rows") or []
    closes = prices(t)
    cs = earnings.cases(t, rows, closes)
    if not cs:
        raise ValueError("no past results with prices for %s" % t)
    r1 = np.array([c["r1"] for c in cs])
    tab = [["Result", "Cases", "Next-day move, typical", "Rose", "20 days after, typical"]]
    for name, f in (("Beat", lambda c: c["surprise"] > 0.02), ("In line", lambda c: -0.02 <= c["surprise"] <= 0.02), ("Missed", lambda c: c["surprise"] < -0.02), ("All", lambda c: True)):
        g = [c for c in cs if f(c)]
        if g:
            d20 = [c["d20"] for c in g if "d20" in c]
            tab.append([name, len(g), E.pc(float(np.median([c["r1"] for c in g]))), E.pc(float(np.mean([c["r1"] > 0 for c in g])), 0),
                        E.pc(float(np.median(d20))) if d20 else "-"])
    move = float(np.median(np.abs(r1)))
    beat = float(np.mean([c["surprise"] > 0 for c in cs]))
    return {"ticker": t, "cases": len(cs), "case_word": "past results", "data_through": closes[-1][0], "data_age_days": age(closes),
            "headline": "%s usually moves about %s the day after results (either way; 8 in 10 moves within %s). It beat the estimate %s of the time." % (
                t, E.pc(move), E.pc(float(np.percentile(np.abs(r1), 80))), E.pc(beat, 0)),
            "table": tab, "expected_move": r4(move),
            "method": "Each past result of %s (dates, reported and estimated earnings per share from the saved history) matched to the "
                      "closes around it: the next-day move from the last close before the news, and the drift over the next 20 trading "
                      "days. 'Beat' means more than 2%% above the estimate. Counting past cases only; an estimate." % t}


# ---------------------------------------------------------------- 9. learned signal, walk-forward
def t_learned(inp):
    t = tick(inp.get("ticker"), "SPY")
    rows = prices(t)
    amount = fnum(inp.get("amount"), 1000, 100, 1e7)
    c = fee_rate(amount)
    m = {}
    for d, v in rows:
        m[d[:7]] = v                                           # last close of each month
    ks = sorted(m)
    px = np.array([m[k] for k in ks])
    if len(px) < 120:
        raise ValueError("needs ten years of monthly closes")
    ret = px[1:] / px[:-1] - 1
    X, Y, mom = [], [], []
    for i in range(12, len(px) - 1):
        X.append([px[i] / px[i - 1] - 1, px[i] / px[i - 3] - 1, px[i] / px[i - 12] - 1, np.std(ret[i - 12:i], ddof=1), px[i] / np.mean(px[i - 9:i + 1]) - 1])
        Y.append(px[i + 1] / px[i] - 1)
        mom.append(1.0 if px[i] > px[i - 12] else 0.0)
    X, Y, mom = np.array(X), np.array(Y), np.array(mom)
    first = 60
    pred = []
    for i in range(first, len(Y)):
        Xa, ya = X[:i], Y[:i]                                    # only months before the forecast
        mu, sd = Xa.mean(axis=0), Xa.std(axis=0) + 1e-9
        Z = np.column_stack([np.ones(i), (Xa - mu) / sd])
        lam = 10.0 * np.eye(Z.shape[1])
        lam[0, 0] = 0
        beta = np.linalg.solve(Z.T @ Z + lam, Z.T @ ya)
        pred.append(float(np.concatenate([[1.0], (X[i] - mu) / sd]) @ beta))
    pred = np.array(pred)
    y = Y[first:]

    def net(pos):
        turn = np.abs(np.diff(np.insert(pos, 0, 0.0)))
        return np.prod(1 + pos * y - turn * c) - 1, int(np.sum(turn > 0))
    model = (pred > 0).astype(float)
    tm, nm = net(model)
    tmo, nmo = net(mom[first:])
    th, _ = net(np.ones(len(y)))
    hit = float(np.mean((pred > 0) == (y > 0)))
    beats = tm > tmo and tm > th and len(y) >= 36
    return {"ticker": t, "cases": len(y), "case_word": "out-of-sample months", "data_through": rows[-1][0], "data_age_days": age(rows),
            "headline": "Learned signal on %s, %d months it never trained on: %s against %s for 12-month momentum and %s for holding, after fees. %s" % (
                t, len(y), E.pc(tm, 0), E.pc(tmo, 0), E.pc(th, 0),
                "It beat both simple rules out of sample; it still stays on paper until it does so in live months." if beats else "It did not beat the simple rules out of sample, so it stays on paper."),
            "table": [["Out of sample", "Total", "Trades"], ["Learned signal", E.pc(tm), nm], ["12-month momentum", E.pc(tmo), nmo], ["Buy and hold", E.pc(th), 1],
                      ["Learned signal: right direction", E.pc(hit, 0), ""], ["Signal now", "in the market" if pred[-1] > 0 else "out of the market", ""]],
            "beats": bool(beats),
            "method": "A ridge regression (penalty 10) of next month's return on five numbers known at each month end: the 1-, 3- and "
                      "12-month change, the 12-month volatility and the distance from the 10-month average. Walk-forward: each month's "
                      "forecast is fitted only on the months before it, starting after %d months. In the market when the forecast is above "
                      "zero; each switch costs %.2f%% (Revolut). Compared with 12-month momentum and buy-and-hold on the same months." % (first, 100 * c)}


def t_events(inp):
    """10. Event study (21 Nov 2026): the usual move after each kind of company event, from ops/engine/events.py."""
    st = E.rj("state/news/event_study.json", {}) or {}
    types = st.get("types") or {}
    if not types:
        raise ValueError("the event study has not run yet (it runs nightly after the back-checks)")
    h = str(inp.get("days") or "5").strip()
    h = h if h in ("1", "5", "20") else "5"
    want = str(inp.get("event") or "all").strip()
    keys = sorted(types, key=lambda k: -((types[k].get(h + "d") or {}).get("n") or 0)) if want == "all" else [k for k in types if k == want]
    if not keys:
        raise ValueError("no event type called %s" % want)
    tab = [["Event", "Cases", "Typical move", "Range (10th to 90th)", "Rose"]]
    for k in keys:
        x = types[k].get(h + "d") or {}
        if x.get("n"):
            tab.append([types[k].get("name", k), x["n"], E.pc(x["median"]), "%s to %s" % (E.pc(x["p10"]), E.pc(x["p90"])), E.pc(x["up"], 0)])
    top = types[keys[0]].get(h + "d") or {}
    return {"cases": top.get("n"), "case_word": "past events", "data_through": str(st.get("as_of"))[:10], "data_age_days": 0,
            "headline": "%s: over %s trading days the typical move against the S&P 500 fund was %s, range %s to %s, %s cases since %s." % (
                types[keys[0]].get("name", keys[0]), h, E.pc(top.get("median") or 0), E.pc(top.get("p10") or 0), E.pc(top.get("p90") or 0), "{:,}".format(top.get("n") or 0), st.get("since")),
            "table": tab, "not_measurable": st.get("not_measurable"), "method": st.get("method")}


TOOLS = {"backtest": t_backtest, "signals": t_signals, "history": t_history, "montecarlo": t_montecarlo, "doomsday": t_doomsday,
         "options": t_options, "pairs": t_pairs, "earnings": t_earnings, "learned": t_learned, "events": t_events}


def run_one(req):
    tool = req.get("tool")
    inp = req.get("inputs") or {}
    out = {"id": req["id"], "tool": tool, "title": TITLE.get(tool, tool), "inputs": inp, "asked_at": req.get("at"), "ran_at": E.now_iso(),
           "label": LABEL_OF.get(tool, "PAPER"), "runner": "GitHub Actions, plain code (ops/engine/qlab.py), no AI"}
    try:
        if tool not in TOOLS:
            raise ValueError("unknown tool")
        out.update(TOOLS[tool](inp))
        out["status"] = "ok"
        n = out.get("cases")
        out["cases_note"] = None if n is None else ("too few cases to rely on" if n < FEW else "%d %s" % (n, out.get("case_word") or "cases"))
    except Exception as e:
        out.update({"status": "failed", "headline": "Could not run: %s" % str(e)[:160]})
    return out


def main():
    os.makedirs(os.path.join(E.ROOT, "state", "qlab", "runs"), exist_ok=True)
    idx = E.rj("state/qlab/index.json", {}) or {}
    runs = idx.get("runs") or []
    done = set(r["id"] for r in runs)
    reqs, sends = [], []
    for p in sorted(glob.glob(os.path.join(E.ROOT, "answers", "qlab-*.json"))):
        try:
            a = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if a.get("kind") == "qlab" and a.get("id") and a["id"] not in done and re.fullmatch(r"qlab-[0-9TZ]+", a["id"]):
            reqs.append(a)
        elif a.get("kind") == "qlab_send" and a.get("run"):
            sends.append(a)
    for req in reqs[:MAX_PER_RUN]:
        res = run_one(req)
        E.wj("state/qlab/runs/%s.json" % req["id"], res)
        runs.append({"id": res["id"], "tool": res["tool"], "title": res["title"], "label": res["label"], "status": res["status"],
                     "ran_at": res["ran_at"], "headline": res.get("headline"), "cases_note": res.get("cases_note"), "ticker": res.get("ticker")})
        print("qlab:", res["id"], res["tool"], res["status"])
    # runs Ben sent to the decision engine: a note on the action list for the same ticker, never an order
    inputs = []
    by = dict((r["id"], r) for r in runs)
    for s in sends:
        r = by.get(s["run"])
        if r and r.get("status") == "ok" and r.get("ticker"):
            inputs.append({"run": r["id"], "tool": r["title"], "ticker": r["ticker"], "label": r["label"], "headline": r["headline"], "sent_at": s.get("at")})
    E.wj("state/qlab/inputs.json", {"as_of": E.now_iso(), "inputs": inputs[-20:],
                                    "rule": "A sent run is shown as a note on the action list for the same ticker. It never places, sizes or changes an order."})
    E.wj("state/qlab/index.json", {"as_of": E.now_iso(), "runs": runs[-200:], "waiting": max(0, len(reqs) - MAX_PER_RUN)})
    print("qlab: %d new run(s), %d waiting, %d sent to the engine" % (min(len(reqs), MAX_PER_RUN), max(0, len(reqs) - MAX_PER_RUN), len(inputs)))


if __name__ == "__main__":
    main()
