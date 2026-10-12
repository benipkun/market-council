# Market Council quant tools, run by the nightly back-check job on the same price history.
#   1. Outcome ranges: what the portfolio, a card or a holding could be worth, from 10,000 simulated futures.
#   2. Options: fair price three ways, the Greeks, implied volatility from real quotes, the cost of protection.
#   3. Pairs: shares that move together in a statistically stable way, tested on years the fit never saw.
#   4. A learned signal: a simple model of next month's return, validated walk-forward only.
# Everything here is on paper. It reads public data, shows its method, and places no orders.
import datetime
import math
import os
import re
import time

import numpy as np

import engine as E

RUNS, BLOCK = 10000, 21
RH = (("1m", 21), ("1y", 252), ("5y", 1260))
COST = 0.005                       # buy and sell at 0.25% each way
SEED = 20261011                    # fixed, so the same data gives the same figures
PATH_YEARS = 15                    # years of daily returns published for the "change the assumptions" control
PAIR_DAYS, PAIR_FIT = 2520, 1512   # ten years: fit on the first six, report on the last four
PAIR_IN, PAIR_OUT, PAIR_STOP = 2.0, 0.0, 4.0
EG_5PCT = -3.37                    # Engle-Granger critical value, two series with a constant, 5%
TENORS = (30, 91, 182, 365)


def r4(x, n=4):
    return E.rd(x, n)


def pcts(v):
    return {"med": r4(np.median(v)), "lo": r4(np.percentile(v, 10)), "hi": r4(np.percentile(v, 90)), "loss": r4(np.mean(v < 0)), "avg": r4(np.mean(v))}


# ---------------------------------------------------------------- 1. outcome ranges
def sim_ranges(r, mu, rng):
    # Daily returns from history, moved so their average matches the assumed yearly return. Their shape (fat tails) and
    # their bad stretches are kept by drawing whole 21-day blocks. The bell curve uses the same average and volatility.
    rc = r - np.mean(r) + mu / 252.0
    cs = np.concatenate([[0.0], np.cumsum(np.log1p(rc))])
    blocks = cs[BLOCK:] - cs[:-BLOCK]
    sd = float(np.std(rc, ddof=1))
    out = {"boot": {}, "bell": {}}
    for h, n in RH:
        pick = rng.integers(0, len(blocks), size=(RUNS, n // BLOCK))
        out["boot"][h] = pcts(np.expm1(blocks[pick].sum(axis=1)))
        out["bell"][h] = pcts(np.expm1(n * (mu / 252.0 - sd * sd / 2) + sd * math.sqrt(n) * rng.standard_normal(RUNS)))
    return out, sd * math.sqrt(252)


def first_touch(paths, target, stop):
    big = paths.shape[1] + 1
    up = paths >= target
    ti = np.where(up.any(axis=1), up.argmax(axis=1), big)
    if stop:
        dn = paths <= stop
        si = np.where(dn.any(axis=1), dn.argmax(axis=1), big)
    else:
        si = np.full(len(ti), big)
    return {"target_first": r4(np.mean(ti < si)), "stop_first": r4(np.mean((si <= ti) & (si < big))), "neither": r4(np.mean((ti == big) & (si == big))),
            "touch_target": r4(np.mean(ti < big)), "above_on_date": r4(np.mean(paths[:, -1] >= target))}


def sim_plan(r, mu, price, target, stop, days, rng):
    rc = r - np.mean(r) + mu / 252.0
    days = int(max(5, min(days, 504)))
    k = -(-days // BLOCK)
    starts = rng.integers(0, len(rc) - BLOCK + 1, size=(RUNS, k))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(RUNS, k * BLOCK)[:, :days]
    boot = first_touch(price * np.exp(np.cumsum(np.log1p(rc[idx]), axis=1)), target, stop)
    sd = float(np.std(rc, ddof=1))
    bell = first_touch(price * np.exp(np.cumsum((mu / 252.0 - sd * sd / 2) + sd * rng.standard_normal((RUNS, days)), axis=1)), target, stop)
    return {"days": days, "boot": boot, "bell": bell}


def differ(a, b):
    return bool(abs((a["1y"]["lo"] or 0) - (b["1y"]["lo"] or 0)) > 0.05 or abs((a["1y"]["loss"] or 0) - (b["1y"]["loss"] or 0)) > 0.05
                or abs((a["5y"]["med"] or 0) - (b["5y"]["med"] or 0)) > 0.15)


def write_path(key, dates, r, limits):
    rel = "state/paths/" + re.sub("[^A-Za-z0-9_]", "_", key) + ".json"
    old = E.rj(rel, None)
    if old and old.get("to") and (datetime.date.fromisoformat(dates[-1]) - datetime.date.fromisoformat(old["to"])).days < 7:
        return   # rewritten once a week at most, so the repository does not grow by a megabyte a day
    E.wj(rel, {"key": key, "from": dates[0], "to": dates[-1], "unit": "hundredths of a percent a day", "r": [int(round(float(x) * 10000)) for x in r]})


def ranges(by, ctx, quant, dec, snap, limits):
    cal, rng = ctx["cal"], np.random.default_rng(SEED)
    rf = (quant.get("opt") or {}).get("rf") or 0.04
    items, holds = {}, dec.get("holds") or {}

    def daily(s, cap=None):
        x = s["x"] if cap is None else s["x"][-cap:]
        return x[1:] / x[:-1] - 1

    def mu_for(t):
        a = (quant.get("assets") or {}).get(t) or {}
        if a.get("mu_est") is not None:
            return float(a["mu_est"]), "the engine's estimate: the risk-free rate plus the share's beta times 5%"
        if (holds.get(t) or {}).get("mu") is not None:
            return float(holds[t]["mu"]), "the engine's estimate"
        s = by.get(t)
        if s is not None and len(s["x"]) > 260:
            ra, rb = daily(s, 253), ctx["spy"][s["b"] - 253:s["b"]]
            rb = rb[1:] / rb[:-1] - 1
            beta = float(np.cov(ra, rb)[0, 1] / np.var(rb)) if np.var(rb) > 0 else 1.0
            return float(min(0.15, max(0.03, rf + beta * 0.05))), "the risk-free rate plus the share's one-year beta times 5%"
        return 0.08, "a plain 8% a year, because the share has too little history for its own estimate"

    def one(key, label, kind, r, dates, mu, mu_note, price):
        sims, vol = sim_ranges(r, mu, rng)
        items[key] = {"label": label, "kind": kind, "price": r4(price, 2), "as_of": dates[-1],
                      "assume": {"mu": r4(mu), "mu_note": mu_note, "vol": r4(vol), "years": r4(len(r) / 252.0, 1), "from": dates[0], "to": dates[-1],
                                 "hist_mu": r4(float(np.mean(r)) * 252)},
                      "boot": sims["boot"], "bell": sims["bell"], "differ": differ(sims["boot"], sims["bell"])}
        write_path(key, dates[-min(len(r), PATH_YEARS * 252):], r[-PATH_YEARS * 252:], limits)
        return items[key]
    # the portfolio at today's weights, over the years all holdings share; cash earns nothing here
    pos = [(p.get("ticker"), float(p.get("pct_nav") or 0) / (100.0 if float(p.get("pct_nav") or 0) > 1.5 else 1.0)) for p in snap.get("positions") or []]
    have = [(t, w) for t, w in pos if t in by and w > 0]
    if have:
        a, b = max(by[t]["a"] for t, w in have), min(by[t]["b"] for t, w in have)
        if b - a > 300:
            rp = np.zeros(b - a - 1)
            for t, w in have:
                x = by[t]["x"][a - by[t]["a"]:b - by[t]["a"]]
                rp += w * (x[1:] / x[:-1] - 1)
            mu = (dec.get("portfolio_range") or {}).get("mu")
            mu = float(mu) if mu is not None else sum(w * mu_for(t)[0] for t, w in have)
            it = one("PORT", "Your portfolio at today's weights", "portfolio", rp, cal[a + 1:b], mu, "the engine's estimate for the holdings at today's weights; cash is counted as earning nothing", 1.0)
            it["covers"] = r4(sum(w for t, w in have), 3)
            it["note"] = "History starts when the youngest holding listed (%s), so it is short." % cal[a][:7]
            if len(have) < len(pos):
                limits.append("Outcome ranges: the portfolio range leaves out %s (no long price history)." % ", ".join(t for t, w in pos if t not in by))
    cards = [c for c in dec.get("cards") or [] if c.get("status") == "open" and c.get("ticker")]
    for t in [t for t, w in pos] + [c["ticker"] for c in cards]:
        s = by.get(t)
        if t in items or s is None or len(s["x"]) < 400:
            continue
        mu, note = mu_for(t)
        one(t, t, "share", daily(s), cal[s["a"] + 1:s["b"]], mu, note, float(s["x"][-1]))
    # targets and stops
    last = datetime.date.fromisoformat(cal[-1])
    for t, k in (dec.get("keeps") or {}).items():
        if t not in items or not k.get("target") or not k.get("by"):
            continue
        s = by[t]
        days = int(np.busday_count(last, datetime.date.fromisoformat(str(k["by"])[:10])))
        if days < 5:
            continue
        stop = [lv.get("price") for lv in (holds.get(t) or {}).get("levels") or [] if str(lv.get("name") or "").startswith("Maximum-loss")]
        stop = float(stop[0]) if stop and stop[0] and stop[0] < s["x"][-1] else None
        pl = sim_plan(daily(s), items[t]["assume"]["mu"], float(s["x"][-1]), float(k["target"]), stop, days, rng)
        pl.update({"kind": "keep", "target": r4(float(k["target"]), 2), "stop": r4(stop, 2), "by": str(k["by"])[:10], "stop_name": "your maximum-loss line" if stop else None})
        items[t]["plan"] = pl
    for c in cards:
        t = c["ticker"]
        if t in items and c.get("take_profit") and c.get("stop") and c.get("entry") and "plan" not in items[t]:
            pl = sim_plan(daily(by[t]), items[t]["assume"]["mu"], float(c["entry"]), float(c["take_profit"]), float(c["stop"]), 252, rng)
            pl.update({"kind": "card", "target": c["take_profit"], "stop": c["stop"], "entry": c["entry"], "card": c.get("id")})
            items[t]["card_plan"] = pl
    return {"as_of": E.now_iso(), "runs": RUNS, "block_days": BLOCK, "horizons": [h for h, _ in RH], "items": items,
            "method": "10,000 simulated futures for each. Daily price changes are drawn from the share's own history in unbroken 21-day stretches, so large moves and bad runs appear as often as they really did; the history is shifted so that its average equals the assumed yearly return. The bell-curve version uses the same average and volatility but assumes changes are normally distributed.",
            "median_note": "The headline is the median: half of the simulated futures end below it. The average is higher because a few very large gains pull it up, and you live through one future, not the average of ten thousand.",
            "honesty": "Simulated outcomes are evidence about the size of the risk, not a forecast. The assumed average return matters most over five years and nobody knows it; change it below and watch the range move."}


# ---------------------------------------------------------------- 2. options
def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def npdf(x):
    return math.exp(-x * x / 2.0) / math.sqrt(2.0 * math.pi)


def bs(S, K, T, r, v, call=True):
    if T <= 0 or v <= 0:
        return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2) if call else K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)


def greeks(S, K, T, r, v, call=True):
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T))
    d2 = d1 - v * math.sqrt(T)
    theta = -S * npdf(d1) * v / (2 * math.sqrt(T)) - (r * K * math.exp(-r * T) * ncdf(d2) if call else -r * K * math.exp(-r * T) * ncdf(-d2))
    return {"delta": r4(ncdf(d1) if call else ncdf(d1) - 1), "gamma": r4(npdf(d1) / (S * v * math.sqrt(T)), 5), "vega": r4(S * npdf(d1) * math.sqrt(T) / 100.0),
            "theta": r4(theta / 365.0), "rho": r4((K * T * math.exp(-r * T) * ncdf(d2) if call else -K * T * math.exp(-r * T) * ncdf(-d2)) / 100.0)}


def binom(S, K, T, r, v, call=True, steps=200, american=True):
    dt = T / steps
    u = math.exp(v * math.sqrt(dt))
    d, disc = 1.0 / u, math.exp(-r * dt)
    p = (math.exp(r * dt) - d) / (u - d)
    j = np.arange(steps + 1)
    px = S * u ** (steps - j) * d ** j
    val = np.maximum(px - K, 0.0) if call else np.maximum(K - px, 0.0)
    for i in range(steps - 1, -1, -1):
        val = disc * (p * val[:-1] + (1 - p) * val[1:])
        if american:
            px = S * u ** (i - np.arange(i + 1)) * d ** np.arange(i + 1)
            val = np.maximum(val, (px - K) if call else (K - px))
    return float(val[0])


def mc_opt(S, K, T, r, v, call, rng, n=20000):
    z = rng.standard_normal(n)
    z = np.concatenate([z, -z])
    st = S * np.exp((r - v * v / 2) * T + v * math.sqrt(T) * z)
    pay = math.exp(-r * T) * (np.maximum(st - K, 0.0) if call else np.maximum(K - st, 0.0))
    return float(np.mean(pay)), float(np.std(pay, ddof=1) / math.sqrt(len(pay)))


def implied(price, S, K, T, r, call):
    if price is None or price <= max(0.0, (S - K * math.exp(-r * T)) if call else (K * math.exp(-r * T) - S)) + 1e-6 or T <= 0:
        return None
    lo, hi = 0.01, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if bs(S, K, T, r, mid, call) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2 if hi < 4.99 else None


def fetch_chain(t, load, save):
    name = "opt_" + re.sub("[^A-Za-z0-9]", "_", t) + ".json"
    if E.OFFLINE:
        return load(name)
    try:
        d = (E.http_json("https://cdn.cboe.com/api/global/delayed_quotes/options/" + t + ".json") or {})
        stamp, d = d.get("timestamp"), d.get("data") or {}
        spot = float(d.get("current_price") or 0)
        today = datetime.datetime.now(datetime.timezone.utc).date()
        exps = {}
        for o in d.get("options") or []:
            m = re.match(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$", str(o.get("option") or ""))
            if not m or not spot:
                continue
            exp = datetime.date(2000 + int(m.group(2)[:2]), int(m.group(2)[2:4]), int(m.group(2)[4:6]))
            k = int(m.group(4)) / 1000.0
            if (exp - today).days >= 7 and 0.7 * spot <= k <= 1.3 * spot:
                exps.setdefault(exp.isoformat(), []).append([m.group(3), k, o.get("bid"), o.get("ask"), o.get("iv"), o.get("open_interest"), o.get("volume")])
        keep = set()
        for want in TENORS:
            near = sorted(exps, key=lambda e: abs((datetime.date.fromisoformat(e) - today).days - want))
            if near:
                keep.add(near[0])
        out = {"t": t, "spot": spot, "bid": d.get("bid"), "ask": d.get("ask"), "iv30": d.get("iv30"), "at": stamp, "exps": {e: exps[e] for e in sorted(keep)}}
        save(name, out)
        return out
    except Exception:
        return load(name)


def options(tickers, held, by, ctx, quant, load, save, limits):
    rng = np.random.default_rng(SEED + 1)
    rf = float((quant.get("opt") or {}).get("rf") or 0.04)
    today = datetime.date.fromisoformat(ctx["cal"][-1])
    out, none = {}, []
    for t in tickers:
        ch = fetch_chain(t, load, save)
        if not ch or not ch.get("exps") or not ch.get("spot"):
            none.append(t)
            continue
        if not E.OFFLINE:
            time.sleep(0.3)
        S, s = float(ch["spot"]), by.get(t)
        x = s["x"] if s is not None else np.array([])
        rv = lambda n: float(np.std(x[-n:][1:] / x[-n:][:-1] - 1, ddof=1) * math.sqrt(252)) if len(x) > n else None
        rows = []
        for e, lst in ch["exps"].items():
            days = (datetime.date.fromisoformat(e) - today).days
            T = max(days, 1) / 365.0
            for want, typ, tag in ((S, "C", "call at today's price"), (S, "P", "put at today's price"), (0.9 * S, "P", "put 10% below today's price")):
                c = [q for q in lst if q[0] == typ and q[2] is not None and q[3] is not None and float(q[3]) > 0]
                if not c:
                    continue
                q = min(c, key=lambda z: abs(z[1] - want))
                mid = (float(q[2]) + float(q[3])) / 2
                iv = implied(mid, S, q[1], T, rf, typ == "C")
                rows.append({"exp": e, "days": days, "type": typ, "tag": tag, "strike": q[1], "bid": q[2], "ask": q[3], "mid": r4(mid, 2), "iv": r4(iv), "iv_source": r4(q[4]),
                             "oi": q[5], "pct_of_price": r4(float(q[3]) / S)})
        if not rows:
            none.append(t)
            continue
        ex = min([r for r in rows if r["type"] == "C"] or rows, key=lambda r: abs(r["days"] - 91))
        T, call = max(ex["days"], 1) / 365.0, ex["type"] == "C"
        v = ex["iv"] or rv(253) or 0.3
        mcp, mce = mc_opt(S, ex["strike"], T, rf, v, call, rng)
        hist = rv(253)
        example = {"exp": ex["exp"], "days": ex["days"], "type": ex["type"], "strike": ex["strike"], "spot": r4(S, 2), "rate": r4(rf), "vol": r4(v), "vol_is": "implied by the market price" if ex["iv"] else "the share's past volatility",
                   "market_mid": ex["mid"], "black_scholes": r4(bs(S, ex["strike"], T, rf, v, call), 3), "binomial": r4(binom(S, ex["strike"], T, rf, v, call), 3),
                   "monte_carlo": r4(mcp, 3), "monte_carlo_error": r4(mce, 3), "greeks": greeks(S, ex["strike"], T, rf, v, call),
                   "at_past_vol": r4(bs(S, ex["strike"], T, rf, hist, call), 3) if hist else None}
        iv30 = float(ch["iv30"]) / 100.0 if ch.get("iv30") else None
        prot = []
        if t in held:
            for want in (91, 182):
                for tag in ("put at today's price", "put 10% below today's price"):
                    c = [r for r in rows if r["tag"] == tag]
                    if c:
                        r0 = min(c, key=lambda r: abs(r["days"] - want))
                        if abs(r0["days"] - want) <= 60:
                            prot.append({"months": 3 if want == 91 else 6, "tag": tag, "exp": r0["exp"], "days": r0["days"], "strike": r0["strike"], "price": r0["ask"], "pct": r0["pct_of_price"]})
        out[t] = {"spot": r4(S, 2), "quote_at": ch.get("at"), "iv30": r4(iv30), "vol_1y": r4(hist), "vol_30d": r4(rv(31)),
                  "reading": (None if not (iv30 and hist) else "Options are pricing in %s movement than the past year showed (%s a year implied, against %s actual)." % (
                      "more" if iv30 > hist * 1.1 else "less" if iv30 < hist * 0.9 else "about the same", E.pc(iv30, 0), E.pc(hist, 0))),
                  "rows": rows, "example": example, "protect": prot}
    if none:
        limits.append("Options: no usable option quotes for %s." % ", ".join(none))
    return {"as_of": E.now_iso(), "rate": r4(rf), "shares": out, "none": none,
            "source": "Cboe delayed quotes (about 15 minutes late in trading hours; the last quotes of the day otherwise).",
            "method": "Black-Scholes is the closed formula for an option that can only be used at the end. The binomial tree steps through 200 possible price moves and allows early use, as US share options do. Monte Carlo averages the payoff over 40,000 simulated prices. All three take the same five inputs: share price, strike, time, interest rate and volatility. Dividends are left out, which overstates calls and understates puts a little for shares that pay them.",
            "note": "Information only. Your broker does not offer options, so no option ever becomes a card."}


# ---------------------------------------------------------------- 3. pairs
def adf_t(e):
    de = e[1:] - e[:-1]
    X = np.column_stack([e[1:-1], de[:-1]])
    y = de[1:]
    beta, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    s2 = float(u @ u) / (len(y) - 2)
    cov = s2 * np.linalg.inv(X.T @ X)
    return float(beta[0] / math.sqrt(cov[0, 0])), float(beta[0])


def trade_pair(z, e, hedge):
    # one position at a time: enter at two standard deviations, leave at the average or at four (the stop), costs on every leg
    trades, pos, e0 = [], 0, 0.0
    for i in range(len(z)):
        if pos == 0:
            if z[i] >= PAIR_IN and z[i] < PAIR_STOP:
                pos, e0 = -1, e[i]
            elif z[i] <= -PAIR_IN and z[i] > -PAIR_STOP:
                pos, e0 = 1, e[i]
        elif (pos == 1 and (z[i] >= PAIR_OUT or z[i] <= -PAIR_STOP)) or (pos == -1 and (z[i] <= PAIR_OUT or z[i] >= PAIR_STOP)):
            trades.append(pos * (e[i] - e0) / (1.0 + abs(hedge)) - COST)
            pos = 0
    t = np.array(trades)
    if len(t) == 0:
        return {"n": 0, "avg": None, "win": None, "total": 0.0, "worst": None, "open": pos != 0}
    return {"n": int(len(t)), "avg": r4(np.mean(t)), "win": r4(np.mean(t > 0)), "total": r4(np.sum(t)), "worst": r4(np.min(t)), "open": pos != 0}


def pairs(shares, ctx, watch, limits):
    n = ctx["n"]
    ok = [s for s in shares if s["b"] == n and s["b"] - s["a"] >= PAIR_DAYS and s.get("sector")]
    groups = {}
    for s in ok:
        groups.setdefault(s["sector"], []).append(s)
    tested, found = 0, []
    for sec, lst in groups.items():
        L = [np.log(s["x"][-PAIR_DAYS:]) for s in lst]
        R = [l[1:PAIR_FIT] - l[:PAIR_FIT - 1] for l in L]
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                if np.corrcoef(R[i], R[j])[0, 1] < 0.5:
                    continue
                tested += 1
                best = None
                for a, b in ((i, j), (j, i)):
                    ya, xb = L[a][:PAIR_FIT], L[b][:PAIR_FIT]
                    hedge, c0 = np.polyfit(xb, ya, 1)
                    e = ya - (c0 + hedge * xb)
                    t, rho = adf_t(e)
                    if best is None or t < best[0]:
                        best = (t, rho, a, b, float(hedge), float(c0), float(np.std(e)))
                t, rho, a, b, hedge, c0, sd = best
                if t >= EG_5PCT or not (-0.2 < rho < 0) or hedge <= 0 or sd <= 0:
                    continue
                half = -math.log(2) / math.log(1 + rho)
                if not (5 <= half <= 120):
                    continue
                e_all = L[a] - (c0 + hedge * L[b])
                z = e_all / sd
                ins, oos = trade_pair(z[:PAIR_FIT], e_all[:PAIR_FIT], hedge), trade_pair(z[PAIR_FIT:], e_all[PAIR_FIT:], hedge)
                t_oos = adf_t(e_all[PAIR_FIT:])[0]
                found.append({"a": lst[a]["t"], "b": lst[b]["t"], "sector": sec, "hedge": r4(hedge, 3), "adf": r4(t, 2), "half_life_days": r4(half, 0), "z_now": r4(z[-1], 2),
                              "z_percentile": r4(float(np.mean(np.abs(z) <= abs(z[-1])))), "in_sample": ins, "unseen": oos, "adf_unseen": r4(t_oos, 2),
                              "fails": bool(oos["n"] == 0 or (oos["total"] or 0) <= 0), "few": bool(oos["n"] < 20), "mine": bool(lst[a]["t"] in watch or lst[b]["t"] in watch),
                              "signal": ("the spread is beyond the stop: the old relationship no longer holds" if abs(z[-1]) >= PAIR_STOP else "the spread is stretched: on paper, buy %s and sell %s short" % ((lst[a]["t"], lst[b]["t"]) if z[-1] <= -PAIR_IN else (lst[b]["t"], lst[a]["t"])) if abs(z[-1]) >= PAIR_IN else "no entry today")})
    good = sorted([p for p in found if (p["in_sample"]["total"] or 0) > 0 and p["in_sample"]["n"] >= 3], key=lambda p: p["adf"])
    held_up = [p for p in good if not p["fails"]]
    un = [p["unseen"] for p in good if p["unseen"]["n"]]
    tot_n = sum(u["n"] for u in un)
    cal = ctx["cal"]
    return {"as_of": E.now_iso(), "tested": tested, "passed_fit": len(good), "held_up": len(held_up), "unseen_trades": tot_n,
            "unseen_avg": r4(sum(u["avg"] * u["n"] for u in un) / tot_n) if tot_n else None,
            "unseen_win": r4(sum(u["win"] * u["n"] for u in un) / tot_n) if tot_n else None,
            "window": {"from": cal[n - PAIR_DAYS], "split": cal[n - PAIR_DAYS + PAIR_FIT], "to": cal[-1], "fit_years": 6, "unseen_years": 4},
            "best": good[:3], "more": good[3:15], "mine": [p for p in good if p["mine"]][:6],
            "rule": "Enter when the spread is two standard deviations from its average: buy the cheap share and sell the dear one short, in the fitted proportion. Leave when the spread is back at its average, or at four standard deviations (the stop). Costs: 0.25% on every leg in and out, so half a percent of the money at work per trade; the fee for borrowing shares to sell short is not included.",
            "method": "Shares in the same sector whose daily moves correlate above 0.5 are tested with the Engle-Granger cointegration test on the first six years: one share's log price is regressed on the other's, and the leftover (the spread) is tested for pulling back to its average (5% level, half-life between 5 and 120 days). Everything is fitted on those six years only. The last four years are then traded with the fitted numbers frozen. The best three are ranked by the strength of the first-part test alone, never by what followed.",
            "note": "Paper only: a pair needs one share sold short, which your account cannot do. With thousands of pairs tested, some pass by luck; the unseen years are the test that matters."}


# ---------------------------------------------------------------- 4. the learned signal
FEATS = [("d200", "Price against its 200-day average"), ("momx", "12-month move against the S&P 500, latest month left out"), ("r21", "Change over one month"),
         ("r63", "Change over three months"), ("dd", "Distance below its 12-month high"), ("vol", "20-day volatility"), ("surp", "Last earnings surprise"),
         ("react", "Price move in the five days after the last results"), ("insnet", "Insiders: net buying or net selling in 90 days")]


def learned(shares, ctx, targets, limits, lam=10.0, first_train=60, top=0.2):
    me, cal = ctx["me"], ctx["cal"]
    M, N, K = len(me), len(shares), len(FEATS)
    X = np.full((M, N, K), np.nan)
    Y = np.full((M, N), np.nan)
    SC = np.full((M, N), np.nan)
    spy = ctx["spy_f"]["1m"] + COST
    for j, s in enumerate(shares):
        idx = [(i, k - s["a"]) for i, k in enumerate(me) if s["a"] + 260 <= k < s["b"]]
        if not idx:
            continue
        ii, jj = np.array([a for a, b in idx]), np.array([b for a, b in idx])
        f = s["f"]
        cols = [f["d200"], s["raw"]["momx"], f["r21"], f["r63"], f["dd"], f["vol"], s["raw"]["surp"], s["raw"]["react"], s["raw"]["insnet"]]
        for k, c in enumerate(cols):
            X[ii, j, k] = c[jj]
        fw = np.full(len(jj), np.nan)
        okf = jj + 21 < len(s["x"])
        fw[okf] = s["x"][jj[okf] + 21] / s["x"][jj[okf]] - 1
        Y[ii, j] = fw
        st = np.stack([s["st"][c][jj] for c in ("trend", "momentum", "drift", "insiders")]).astype(float)
        st[st < 0] = np.nan
        SC[ii, j] = np.where(np.isnan(st).sum(axis=0) <= 1, np.nansum(st, axis=0), np.nan)
    # each month, every feature becomes a rank between -0.5 and +0.5 across the shares; a missing value sits in the middle
    Z = np.zeros_like(X)
    for i in range(M):
        for k in range(K):
            v = X[i, :, k]
            okv = ~np.isnan(v)
            if okv.sum() > 20:
                rk = np.argsort(np.argsort(v[okv])).astype(float)
                Z[i, okv, k] = rk / (okv.sum() - 1) - 0.5
    have = ~np.isnan(Y) & ~np.isnan(X[:, :, 0])
    Yx = np.where(have, Y - np.nanmean(np.where(have, Y, np.nan), axis=1, keepdims=True), np.nan)   # return against the average share that month
    months = [i for i in range(M) if have[i].sum() >= int(os.environ.get("MC_LEARN_MIN", "40"))]
    if len(months) < first_train + 24:
        return {"status": "too little history", "as_of": E.now_iso()}
    start = months[first_train]
    folds, coefs, rows, prev_top, prev_sc = [], [], [], set(), set()
    ic_in, ic_out = [], []

    def fit(upto):
        sel = [i for i in months if i < upto]
        A = np.concatenate([Z[i][have[i]] for i in sel])
        y = np.clip(np.concatenate([Yx[i][have[i]] for i in sel]), -0.5, 0.5)
        w = np.linalg.solve(A.T @ A + lam * np.eye(K), A.T @ y)
        ics = [float(np.corrcoef(np.argsort(np.argsort(Z[i][have[i]] @ w)), np.argsort(np.argsort(Yx[i][have[i]])))[0, 1]) for i in sel[-60:]]
        return w, float(np.mean(ics))
    w, year_of = None, None
    for i in [m for m in months if m >= start]:
        y = cal[me[i]][:4]
        if y != year_of:
            w, ic_tr = fit(i)   # refitted once a year on everything before that month
            year_of = y
            coefs.append(w)
            ic_in.append(ic_tr)
        okm = have[i]
        pred = Z[i][okm] @ w
        ret = Y[i][okm]
        names = np.array([s["t"] for s in shares])[okm]
        ic_out.append(float(np.corrcoef(np.argsort(np.argsort(pred)), np.argsort(np.argsort(ret)))[0, 1]))
        k = max(5, int(round(top * len(pred))))
        pick = np.argsort(-pred)[:k]
        cur = set(names[pick])
        model = float(np.mean(ret[pick])) - COST * (len(cur - prev_top) / float(len(cur)))
        prev_top = cur
        sc = SC[i][okm]
        g = np.where(sc >= 3)[0]
        cur_sc = set(names[g])
        score = (float(np.mean(ret[g])) - COST * (len(cur_sc - prev_sc) / float(max(1, len(cur_sc))))) if len(g) >= 5 else np.nan
        prev_sc = cur_sc
        rows.append((y, model, score, float(np.mean(ret)), float(spy[me[i]]) if not np.isnan(spy[me[i]]) else np.nan))
    R = np.array([[a, b, c, d] for _, a, b, c, d in rows], dtype=float)
    yrs = [y for y, *_ in rows]

    def ann(v):
        v = v[~np.isnan(v)]
        return r4(float(np.prod(1 + v)) ** (12.0 / len(v)) - 1) if len(v) else None
    table = []
    for y in sorted(set(yrs)):
        m = np.array([yy == y for yy in yrs])
        table.append({"year": y, "months": int(m.sum()), "model": r4(float(np.prod(1 + R[m, 0]) - 1)), "score": r4(float(np.nanprod(1 + R[m, 1]) - 1)) if not np.isnan(R[m, 1]).all() else None,
                      "all": r4(float(np.prod(1 + R[m, 2]) - 1)), "spy": r4(float(np.nanprod(1 + R[m, 3]) - 1))})
    both = ~np.isnan(R[:, 1])
    wm = np.mean(np.array(coefs), axis=0)
    imp = sorted([{"id": FEATS[k][0], "name": FEATS[k][1], "weight": r4(float(wm[k]), 4), "direction": "higher is better" if wm[k] > 0 else "lower is better"} for k in range(K)], key=lambda d: -abs(d["weight"]))
    icin, icout = float(np.mean(ic_in)), float(np.mean(ic_out))
    beats_score = bool(ann(R[both, 0]) is not None and ann(R[both, 1]) is not None and ann(R[both, 0]) > ann(R[both, 1]))
    beats_all = bool(ann(R[:, 0]) > ann(R[:, 2]))
    # today's reading, from a fit on everything
    w_now, _ = fit(M + 1)
    Xt = np.full((N, K), np.nan)
    for j, s in enumerate(shares):
        if s["b"] == ctx["n"] and len(s["x"]) > 260:
            f = s["f"]
            Xt[j] = [c[-1] for c in (f["d200"], s["raw"]["momx"], f["r21"], f["r63"], f["dd"], f["vol"], s["raw"]["surp"], s["raw"]["react"], s["raw"]["insnet"])]
    okl = ~np.isnan(Xt[:, 0])
    Zt = np.zeros((N, K))
    for k in range(K):
        okv = ~np.isnan(Xt[:, k])
        if okv.sum() > 20:
            Zt[okv, k] = np.argsort(np.argsort(Xt[okv, k])) / float(okv.sum() - 1) - 0.5
    pred = Zt @ w_now
    order = np.argsort(np.argsort(-pred[okl]))
    rank = dict(zip([s["t"] for j, s in enumerate(shares) if okl[j]], order / float(max(1, okl.sum() - 1))))
    today = {t: {"percentile": r4(float(rank[t]), 3), "top": bool(rank[t] <= top)} for t in targets if t in rank}
    return {"status": "ok", "as_of": E.now_iso(), "features": [{"id": a, "name": b} for a, b in FEATS], "importance": imp,
            "unseen": {"from": cal[me[start]][:7], "to": cal[me[months[-1]]][:7], "months": int(len(rows)), "model": ann(R[:, 0]), "score": ann(R[both, 1]), "model_same_months": ann(R[both, 0]),
                       "all": ann(R[:, 2]), "spy": ann(R[:, 3]), "beat_all_months": r4(float(np.mean(R[:, 0] > R[:, 2]))), "rank_link": r4(icout, 3)},
            "training": {"rank_link": r4(icin, 3)},
            "overfit": bool(icout <= 0 or icin > 2 * icout),
            "overfit_note": "On the data it was trained on, the model's ranking matched what happened with a strength of %.3f; on months it had never seen, %.3f. %s" % (
                icin, icout, "That gap is the mark of a model that learned noise." if (icout <= 0 or icin > 2 * icout) else "The two are close, so it is not simply memorising the past."),
            "beats_score": beats_score, "beats_all": beats_all, "table": table, "today": today, "top_share": top,
            "verdict": ("On unseen months it beat the plain score." if beats_score else "On unseen months it did not beat the plain score.") + (" It beat the average share in the list." if beats_all else " It did not beat the average share in the list.") + " It stays on paper either way; promoting it to the scorecard is your decision.",
            "method": "A ridge regression (a straight-line model that is discouraged from leaning hard on any one input) predicts each share's next-month return, measured against the average share, from nine inputs. Each input is turned into a rank among the shares that month. The model is refitted once a year using only earlier months, then used for the following twelve: no month is ever predicted by a model that saw it. Each month the top fifth by prediction is held, equally weighted; half a percent is charged on every name that enters. The plain score is the same test for shares passing at least three of the four checks that can be rebuilt (the full seven cannot).",
            "caveat": "The shares are today's largest companies, so all four columns are flattered and the average share beats the index by construction. The fair comparison is model against average share, and model against plain score."}


def run(shares, ctx, meta, targets, limits, load, save):
    quant, dec, snap = E.rj("state/quant.json", {}) or {}, E.rj("state/decisions.json", {}) or {}, E.rj("treasury/snapshot.json", {}) or {}
    by = {s["t"]: s for s in shares}
    held = [p.get("ticker") for p in snap.get("positions") or [] if p.get("ticker")]
    cards = [c.get("ticker") for c in dec.get("cards") or [] if c.get("status") == "open" and c.get("ticker")]
    done = []
    for name, rel, fn in (
            ("Outcome ranges", "state/ranges.json", lambda: ranges(by, ctx, quant, dec, snap, limits)),
            ("Options", "state/options.json", lambda: options(list(dict.fromkeys(held + cards))[:12], held, by, ctx, quant, load, save, limits)),
            ("Pairs", "state/pairs.json", lambda: pairs(shares, ctx, set(targets), limits)),
            ("Learned signal", "state/learned.json", lambda: learned([s for s in shares if s.get("listed")] or shares, ctx, targets, limits))):
        try:
            E.wj(rel, fn())
            done.append(name)
        except Exception as e:
            limits.append("%s: not computed this run (%s: %s)." % (name, type(e).__name__, str(e)[:120]))
    return done
