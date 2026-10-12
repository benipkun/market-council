"""Market Council forecaster. Plain code, no AI: every probability here is counted or simulated, never chosen.

For each holding and each idea it answers fixed yes-or-no questions with a date (higher than today? a fall of more
than 10% or 25%? better than the index fund? target before stop?) at one month, three months and one year, from three
sources that are each shown:
  sim   10,000 simulated futures drawn from the share's own daily price changes in unbroken 21-day stretches
  base  how often it happened after similar past setups across all shares in the history, with the number of cases
  opt   what option prices imply (a bell curve at the option market's volatility), where a free quote exists
The headline is their plain average; the range covers all of them, and is widened when they disagree. Every forecast is
written once to a log that is never edited (each entry carries a fingerprint of the one before it), marked right or
wrong by code when its date arrives, and scored against two simple rivals: always saying 50%, and the plain base rate.
A back-test makes the same forecasts at past dates, using only what was known then, and scores them the same way.
Run by history.py after each US trading day. It never places orders."""
import datetime
import hashlib
import json
import math
import os

import numpy as np

import engine as E

VERSION = 1
RUNS, SENS_RUNS, BT_RUNS, BLOCK, SEED = 10000, 2000, 1000, 21, 20261012
HZ = (("1m", 21), ("3m", 63), ("1y", 252))
HN = {"1m": "one month", "3m": "three months", "1y": "one year"}
KINDS = ("up", "fall10", "fall25", "beat")
MIN_CASES = 20          # fewer cases than this: "too few cases to rely on", and the source is shown but not averaged in
WIDE = 0.15             # sources further apart than this are reported as disagreeing, and the range is widened
CAP_LO, CAP_HI = 0.10, 0.90
SIM_DAYS = 2520         # at most ten years of the share's own history feed the simulation
MIN_DAYS = 400
ENOUGH = 30             # checked forecasts needed before the score is more than "too early to judge"
NL = chr(10)


def r4(x, n=4):
    return E.rd(x, n)


def words(p):
    if p is None:
        return "not known"
    if p < 0.05:
        return "very unlikely (less than 1 in 20)"
    if p > 0.95:
        return "very likely (more than 19 in 20)"
    best = min(((round(abs(p - a / float(b)), 4), b, a) for b in (2, 3, 4, 5, 10) for a in range(1, b)))
    return "about %d in %d" % (best[2], best[1])


def band_of(p):
    return min(0.9, max(0.1, round(p * 10) / 10.0))


# ---------------------------------------------------------------- setups and what happened after them
def cells_for(x):
    # for every day a number 0..11 built from three facts known that day: above the 200-day average or not, up or down
    # over 63 days, and how jumpy the last 20 days were (under 20%, 20 to 35%, over 35% a year); -1 where not known yet
    n = len(x)
    out = np.full(n, -1, dtype=int)
    if n < 260:
        return out
    c = np.concatenate([[0.0], np.cumsum(x)])
    avg = np.full(n, np.nan)
    avg[199:] = (c[200:] - c[:-200]) / 200.0
    r = np.zeros(n)
    r[1:] = x[1:] / x[:-1] - 1
    c1, c2 = np.concatenate([[0.0], np.cumsum(r)]), np.concatenate([[0.0], np.cumsum(r * r)])
    s1, s2 = c1[21:n + 1] - c1[1:n - 19], c2[21:n + 1] - c2[1:n - 19]
    vol = np.full(n, np.nan)
    vol[20:] = np.sqrt(np.maximum((s2 - s1 * s1 / 20.0) / 19.0, 0.0)) * math.sqrt(252)
    mom = np.full(n, np.nan)
    mom[63:] = x[63:] / x[:-63] - 1
    ok = ~np.isnan(avg) & ~np.isnan(vol) & ~np.isnan(mom)
    band = np.where(vol < 0.20, 0, np.where(vol < 0.35, 1, 2))
    with np.errstate(invalid="ignore"):
        code = (x > avg).astype(int) * 6 + (mom > 0).astype(int) * 3 + band
    out[ok] = code[ok]
    return out


def cell_text(c):
    return "price %s its 200-day average, %s over three months, %s" % (
        "above" if c >= 6 else "below", "up" if (c % 6) >= 3 else "down",
        ("calm (moving less than 20% a year)", "moving 20 to 35% a year", "jumpy (moving more than 35% a year)")[c % 3])


def flip_trend(c):
    return c - 6 if c >= 6 else c + 6


def outcomes(x, spy, I, d):
    # x and spy cover the same days; I are starting days with I + d inside the series. Paths are ratios of the start.
    P = x[I[:, None] + 1 + np.arange(d)[None, :]] / x[I][:, None]
    end, mn = P[:, -1], P.min(axis=1)
    return {"up": end > 1.0, "fall10": mn <= 0.90, "fall25": mn <= 0.75, "beat": end > spy[I + d] / spy[I]}, P


def touch_first(P, up, dn):
    # which level a path closes beyond first: (target first, stop first). The same day counts for the stop.
    big = P.shape[1] + 1
    a = P >= up
    ti = np.where(a.any(axis=1), a.argmax(axis=1), big)
    if dn:
        b = P <= dn
        si = np.where(b.any(axis=1), b.argmax(axis=1), big)
    else:
        si = np.full(len(ti), big)
    return ti < si, (si <= ti) & (si < big)


def pooled(shares, ctx):
    # one start a month for every share: the setup that day and what happened over each horizon
    spy = ctx["spy"]
    tab = {h: {"g": [], "c": [], "ev": {k: [] for k in KINDS}} for h, _ in HZ}
    per = {}
    for s in shares:
        x, n = s["x"], len(s["x"])
        if n < 300:
            continue
        cells = cells_for(x)
        per[s["t"]] = cells
        sa = spy[s["a"]:s["b"]]
        for h, d in HZ:
            I = np.arange(200, n - d, BLOCK)
            I = I[cells[I] >= 0] if len(I) else I
            if not len(I):
                continue
            ev, _ = outcomes(x, sa, I, d)
            tab[h]["g"].append(s["a"] + I)
            tab[h]["c"].append(cells[I])
            for k in KINDS:
                tab[h]["ev"][k].append(ev[k])
    for h, _ in HZ:
        T = tab[h]
        T["g"] = np.concatenate(T["g"]) if T["g"] else np.zeros(0, dtype=int)
        T["c"] = np.concatenate(T["c"]) if T["c"] else np.zeros(0, dtype=int)
        for k in KINDS:
            T["ev"][k] = np.concatenate(T["ev"][k]) if T["ev"][k] else np.zeros(0, dtype=bool)
    return tab, per


def base_rates(tab, h, d, cell=None, cutoff=None):
    # how often each thing happened after the same setup (cell None = after any setup), counting only cases that had
    # fully played out by the cutoff day
    T = tab[h]
    m = np.ones(len(T["g"]), dtype=bool) if cell is None else (T["c"] == cell)
    if cutoff is not None:
        m = m & ((T["g"] + d) <= cutoff)
    n = int(m.sum())
    if not n:
        return {k: None for k in KINDS}, 0, 0
    return {k: float(T["ev"][k][m].mean()) for k in KINDS}, n, int(len(np.unique(T["g"][m] // BLOCK)))


def touch_rate(shares, per, cell, d, up, dn):
    hit = rev = tot = 0
    months = set()
    for s in shares:
        cells, x = per.get(s["t"]), s["x"]
        if cells is None:
            continue
        I = np.arange(200, len(x) - d, BLOCK)
        I = I[cells[I] == cell] if len(I) else I
        if not len(I):
            continue
        P = x[I[:, None] + 1 + np.arange(d)[None, :]] / x[I][:, None]
        a, b = touch_first(P, up, dn)
        hit, rev, tot = hit + int(a.sum()), rev + int(b.sum()), tot + len(I)
        months.update(((s["a"] + I) // BLOCK).tolist())
    return (hit / float(tot), rev / float(tot), tot, len(months)) if tot else (None, None, 0, 0)


# ---------------------------------------------------------------- the three sources
def simulate(r, rs, mu, mus, d, runs, rng, vol_scale=1.0):
    # the share's own daily changes, shifted to the assumed yearly return, drawn in unbroken 21-day stretches; the
    # index fund's changes are drawn from the same days, so the two keep moving together the way they did
    rc = np.maximum((r - np.mean(r)) * vol_scale + mu / 252.0, -0.95)
    rsc = np.maximum(rs - np.mean(rs) + mus / 252.0, -0.95)
    k = -(-d // BLOCK)
    starts = rng.integers(0, len(rc) - BLOCK + 1, size=(runs, k))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(runs, k * BLOCK)[:, :d]
    return np.exp(np.cumsum(np.log1p(rc[idx]), axis=1)), np.exp(np.sum(np.log1p(rsc[idx]), axis=1))


def sim_probs(P, S=None):
    end, mn = P[:, -1], P.min(axis=1)
    out = {"up": float(np.mean(end > 1.0)), "fall10": float(np.mean(mn <= 0.90)), "fall25": float(np.mean(mn <= 0.75))}
    out["beat"] = float(np.mean(end > S)) if S is not None else None
    return out


def bell_paths(iv, rf, d, runs, rng):
    sd = iv / math.sqrt(252.0)
    return np.exp(np.cumsum((rf / 252.0 - sd * sd / 2) + sd * rng.standard_normal((runs, d)), axis=1))


def implied_vol(opt, d):
    # the volatility option prices imply for about this horizon: the at-the-money call expiring closest to it
    rows = [q for q in (opt or {}).get("rows") or [] if q.get("type") == "C" and q.get("iv") and (q.get("days") or 0) > 0]
    want = d * 365.0 / 252.0
    if rows:
        q = min(rows, key=lambda z: abs(z["days"] - want))
        if abs(q["days"] - want) <= max(45, 0.6 * want):
            return float(q["iv"]), "options expiring %s" % q.get("exp")
    if d <= 30 and (opt or {}).get("iv30"):
        return float(opt["iv30"]), "the 30-day option volatility"
    return None, None


def combine(sim, base, cases, months, opt, adj=0.0):
    # the plain average of the sources that can be relied on; the range covers every source and the uncertainty of the
    # base rate, and is widened when the sources disagree. Nothing is averaged away silently: all three stay visible.
    solid = base is not None and cases >= MIN_CASES
    vals = [v for v in (sim, base if solid else None, opt) if v is not None]
    p = sum(vals) / len(vals)
    lo, hi = min(vals), max(vals)
    if solid:
        se = math.sqrt(max(base * (1 - base), 1e-6) / max(months, 1))
        lo, hi = min(lo, base - 1.96 * se), max(hi, base + 1.96 * se)
    else:
        lo, hi = lo - 0.10, hi + 0.10
    disagree = (max(vals) - min(vals)) > WIDE
    if disagree:
        lo, hi = lo - 0.05, hi + 0.05
    capped = False
    if not solid and (p < CAP_LO or p > CAP_HI):
        p, capped = min(CAP_HI, max(CAP_LO, p)), True
    raw = p
    p = min(0.99, max(0.01, p + (adj or 0.0)))
    lo, hi = max(0.01, min(lo, p - 0.03)), min(0.99, max(hi, p + 0.03))
    return {"p": r4(p, 3), "raw": r4(raw, 3), "lo": r4(lo, 3), "hi": r4(hi, 3), "disagree": bool(disagree), "capped": capped,
            "few": not solid, "adj": r4(adj or 0.0, 3)}


def beta_mu(r, rs, rf):
    a, b = r[-252:], rs[-252:]
    v = float(np.var(b))
    beta = float(np.cov(a, b)[0, 1] / v) if v > 0 and len(a) > 60 else 1.0
    return float(min(0.15, max(0.03, rf + beta * 0.05)))


# ---------------------------------------------------------------- the log: written once, never edited
def entry_hash(prev, e):
    body = json.dumps({k: e[k] for k in sorted(e) if k not in ("hash", "prev")}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((str(prev or "") + body).encode("utf-8")).hexdigest()[:24]


def chain_ok(entries):
    prev = None
    for e in entries:
        if e.get("prev") != prev or e.get("hash") != entry_hash(prev, e):
            return False
        prev = e["hash"]
    return True


def append_log(entries, new, made, cal_idx):
    # one entry a week for each question, or sooner when the price has moved more than a typical month from the last one
    last = {}
    for e in entries:
        last[(e["t"], e["kind"], e["h"])] = e
    added = 0
    for f in new:
        o = last.get((f["t"], f["kind"], f["h"]))
        if o is not None:
            gap = cal_idx.get(made, 0) - cal_idx.get(o["made"], -99)
            moved = abs(f["ref"] / o["ref"] - 1) > f.get("move", 9) if (o.get("ref") and f.get("ref")) else False
            same_levels = (o.get("up"), o.get("dn")) == (f.get("up"), f.get("dn"))
            if gap < 5 and not moved and same_levels:
                continue
        e = {k: f[k] for k in ("t", "kind", "h", "d", "due", "q", "p", "lo", "hi", "plain", "ref", "up", "dn", "sim", "base", "opt", "cases", "w") if f.get(k) is not None}
        e["made"], e["id"] = made, "%s|%s|%s|%s" % (made, f["t"], f["kind"], f["h"])
        e["prev"] = entries[-1]["hash"] if entries else None
        e["hash"] = entry_hash(e["prev"], e)
        entries.append(e)
        added += 1
    return added


def score_entry(e, by, ctx):
    # 1 = it happened, 0 = it did not, None = not decided yet (or the prices needed are no longer in the history)
    m = ctx["idx"].get(e["made"])
    if m is None:
        return None
    d, kind = int(e["d"]), e["kind"]
    if e["t"] == "PORT":
        w, val, full = e.get("w") or {}, 1.0 - sum((e.get("w") or {}).values()), True
        for t, wt in w.items():
            s = by.get(t)
            if s is None or not (s["a"] <= m and m + d < s["b"]):
                full = False
                break
            val += wt * float(s["x"][m + d - s["a"]] / s["x"][m - s["a"]])
        if not full:
            return None
        return int(val < (1.0 - float(e.get("dn") or 0.0)) if kind == "port_max" else val < 1.0)
    s = by.get(e["t"])
    if s is None or not (s["a"] <= m < s["b"]):
        return None
    x, i = s["x"], m - s["a"]
    path = x[i + 1:i + 1 + d] / x[i]
    full = len(path) >= d
    if kind == "up":
        return int(path[-1] > 1.0) if full else None
    if kind in ("fall10", "fall25"):
        lvl = 0.90 if kind == "fall10" else 0.75
        if len(path) and float(path.min()) <= lvl:
            return 1
        return 0 if full else None
    if kind == "beat":
        return int(path[-1] > ctx["spy"][m + d] / ctx["spy"][m]) if full else None
    if kind in ("tp_first", "stop_first") and len(path):
        a, b = touch_first(path[None, :], float(e["up"]), float(e["dn"]))
        if a[0] or b[0]:
            return int(bool(a[0]) == (kind == "tp_first"))
        return 0 if full else None
    return None


def summarise(P, O, PL, labels=None):
    # P stated probabilities, O what happened (1/0), PL the plain base rate said at the time
    P, O, PL = np.asarray(P, dtype=float), np.asarray(O, dtype=float), np.asarray(PL, dtype=float)
    n = int(len(P))
    out = {"checked": n, "enough": n >= ENOUGH, "bands": [], "adjust": {}}
    if not n:
        out["verdict"] = "Too early to judge: no forecast has reached its date yet."
        return out
    bf, b5, bp = float(np.mean((P - O) ** 2)), float(np.mean((0.5 - O) ** 2)), float(np.mean((PL - O) ** 2))
    out.update({"brier": r4(bf), "brier_fifty": r4(b5), "brier_plain": r4(bp), "beats_fifty": bool(bf < b5), "beats_plain": bool(bf < bp)})
    bands = np.array([band_of(p) for p in P])
    for b in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        m = np.abs(bands - b) < 1e-9
        k = int(m.sum())
        row = {"band": b, "n": k, "said": r4(float(P[m].mean()), 3) if k else None, "happened": r4(float(O[m].mean()), 3) if k else None, "few": k < MIN_CASES}
        out["bands"].append(row)
        if k >= MIN_CASES:
            out["adjust"]["%.1f" % b] = r4(float(O[m].mean() - P[m].mean()), 3)
    if labels is not None:
        kinds = {}
        for lab in sorted(set(labels)):
            m = np.array([x == lab for x in labels])
            kinds[lab] = {"n": int(m.sum()), "said": r4(float(P[m].mean()), 3), "happened": r4(float(O[m].mean()), 3),
                          "brier": r4(float(np.mean((P[m] - O[m]) ** 2))), "brier_plain": r4(float(np.mean((PL[m] - O[m]) ** 2))),
                          "brier_fifty": r4(float(np.mean((0.5 - O[m]) ** 2)))}
        out["kinds"] = kinds
    if n < ENOUGH:
        out["verdict"] = "Too early to judge: %d forecast%s checked, %d needed." % (n, "" if n == 1 else "s", ENOUGH)
    else:
        out["verdict"] = ("Its error score is %.3f (lower is better; 0 is perfect). Always saying 50%% scores %.3f and the plain base rate %.3f. " % (bf, b5, bp)) + (
            "It beats both." if (bf < b5 and bf < bp) else "It beats always saying 50% but NOT the plain base rate, so the extra work adds nothing yet." if bf < b5
            else "It beats the plain base rate but not always saying 50%." if bf < bp else "It beats NEITHER rival: its probabilities are no better than a guess.")
    return out


# ---------------------------------------------------------------- the back-test of the method itself
def backtest(shares, ctx, tab, per, targets, rf, load, save):
    key = "%s|v%d|%d" % (ctx["cal"][-1][:7], VERSION, len(shares))
    old = load("fc_backtest.json")
    if old and old.get("key") == key:
        return old["out"]
    rng, spy, cal = np.random.default_rng(SEED + 7), ctx["spy"], ctx["cal"]
    pick = [s for s in shares if s["t"] in targets] + [s for k, s in enumerate(shares) if k % 6 == 0 and s["t"] not in targets]
    P_, O_, PL_, K_ = [], [], [], []
    first, last, used = None, None, 0
    for s in pick:
        x, n, cells = s["x"], len(s["x"]), per.get(s["t"])
        if cells is None or n < 756 + 320:
            continue
        sa = spy[s["a"]:s["b"]]
        r, rs = x[1:] / x[:-1] - 1, sa[1:] / sa[:-1] - 1
        used += 1
        for i in range(max(756, n - 3024 - 253), n - 253, 63):
            c = int(cells[i])
            if c < 0:
                continue
            ri, rsi = r[max(0, i - SIM_DAYS):i], rs[max(0, i - SIM_DAYS):i]
            mu, mus, g = beta_mu(ri, rsi, rf), rf + 0.05, s["a"] + i
            first, last = min(first or cal[g], cal[g]), max(last or cal[g], cal[g])
            for h, d in HZ:
                Pm, Sm = simulate(ri, rsi, mu, mus, d, BT_RUNS, rng)
                sp = sim_probs(Pm, Sm)
                ev, Pr = outcomes(x, sa, np.array([i]), d)
                br, nb, mo = base_rates(tab, h, d, c, g)
                pl, npl, _ = base_rates(tab, h, d, None, g)
                for k in KINDS:
                    f = combine(sp[k], br[k], nb, mo, None)
                    P_.append(f["p"]); O_.append(int(ev[k][0])); PL_.append(pl[k] if pl[k] is not None else 0.5); K_.append(k + " " + h)
                if h == "3m":
                    a, b = touch_first(Pm, 1.10, 0.90)
                    ra, rb = touch_first(Pr, 1.10, 0.90)
                    f = combine(float(np.mean(a)), None, 0, 0, None)
                    P_.append(f["p"]); O_.append(int(ra[0])); PL_.append(0.5); K_.append("up 10% before down 10% 3m")
    out = summarise(P_, O_, PL_, K_)
    out.update({"shares": used, "from": first, "to": last, "runs": BT_RUNS,
                "method": "The same code made forecasts at one date every three months over the last twelve years for %d shares, using only prices up to that date and only past cases that had fully played out by then. Each forecast was then compared with what happened." % used,
                "limits": ["The shares are today's large companies: firms that failed or were taken over are missing, which flatters \"higher than today\" and understates big falls.",
                           "The option-price source could not be back-tested: no free history of option prices exists. The back-test covers the simulation and the base rate only.",
                           "Forecasts made a quarter apart for the same share overlap for the one-year questions, so there are fewer independent cases than the counts suggest.",
                           "Today's interest rate is used at every past date."]})
    save("fc_backtest.json", {"key": key, "out": out})
    return out


# ---------------------------------------------------------------- today's forecasts
def due_date(last, d):
    return str(np.busday_offset(np.datetime64(last), d, roll="forward"))


def movers(base_p, alts):
    rows = [{"if": txt, "to": r4(p, 3), "by": r4(p - base_p, 3)} for txt, p in alts if p is not None]
    rows.sort(key=lambda z: -abs(z["by"]))
    return rows[:3]


def share_forecast(s, ctx, tab, per, shares, opt, plan, rf, adjust, rng):
    x, n, cal = s["x"], len(s["x"]), ctx["cal"]
    t, px, last = s["t"], float(s["x"][-1]), cal[s["b"] - 1]
    if n < MIN_DAYS:
        return {"none": "Not enough history to forecast this: %d trading days of prices, and %d are needed." % (n, MIN_DAYS)}, []
    sa = ctx["spy"][s["a"]:s["b"]]
    r, rs = (x[1:] / x[:-1] - 1)[-SIM_DAYS:], (sa[1:] / sa[:-1] - 1)[-SIM_DAYS:]
    mu, mus = beta_mu(r, rs, rf), rf + 0.05
    vol = float(np.std(r[-252:], ddof=1) * math.sqrt(252))
    cell = int(per[t][-1]) if per.get(t) is not None else -1
    month_move = vol / math.sqrt(12.0)
    out = {"price": r4(px, 2), "as_of": last, "setup": cell_text(cell) if cell >= 0 else None, "assume": {"mu": r4(mu), "vol": r4(vol), "years": r4(len(r) / 252.0, 1)},
           "h": {}, "check": "Each question is checked by code on its own date. All forecasts are recalculated after every US trading day; a fresh one is logged once a week, or sooner if the price moves more than %s from $%.2f (a typical month for this share) or a target or stop changes." % (E.pc(month_move, 0), px)}
    logs = []
    up = dn = None
    if plan and plan.get("target") and plan["target"] > px:
        up = float(plan["target"]) / px
        dn = float(plan["stop"]) / px if plan.get("stop") and plan["stop"] < px else None
    horizons = list(HZ) + ([("by", int(plan["days"]))] if plan and plan.get("days") and abs(plan["days"] - 252) > 30 and up else [])
    for h, d in horizons:
        due = due_date(last, d)
        P0, S0 = simulate(r, rs, mu, mus, d, RUNS, rng)
        sp = sim_probs(P0, S0)
        alt = {}
        for name, a_mu, a_vs in (("lo", mu - 0.05, 1.0), ("hi", mu + 0.05, 1.0), ("wild", mu, 1.25), ("calm", mu, 0.8)):
            Pa, Sa = simulate(r, rs, a_mu, mus, d, SENS_RUNS, rng, a_vs)
            alt[name] = (sim_probs(Pa, Sa), Pa)
        alt_txt = (("lo", "its yearly return turns out 5 points lower than the %s assumed" % E.pc(mu, 0)), ("hi", "its yearly return turns out 5 points higher than the %s assumed" % E.pc(mu, 0)),
                   ("wild", "it moves a quarter more than it has in the past"), ("calm", "it moves a fifth less than it has in the past"))
        iv, iv_note = implied_vol(opt, d)
        Pb = bell_paths(iv, rf, d, 5000, rng) if iv else None
        ob = sim_probs(Pb) if Pb is not None else {}
        if h in tab and cell >= 0:
            br, nb, mo = base_rates(tab, h, d, cell)
            bf, _, _ = base_rates(tab, h, d, flip_trend(cell))
            pl, _, _ = base_rates(tab, h, d, None)
        else:
            br, nb, mo, bf, pl = {k: None for k in KINDS}, 0, 0, {k: None for k in KINDS}, {k: None for k in KINDS}
        own_I = np.arange(0, n - d, d)
        own = {k: float(v.mean()) for k, v in outcomes(x, ctx["spy"][s["a"]:s["b"]], own_I, d)[0].items()} if len(own_I) else {}
        q = np.percentile(P0[:, -1], [5, 25, 50, 75, 95])
        H = {"due": due, "days": d, "label": HN.get(h, "by your review date"), "range50": [r4(px * q[1], 2), r4(px * q[3], 2)], "range90": [r4(px * q[0], 2), r4(px * q[4], 2)],
             "median": r4(px * q[2], 2), "f": {}, "implied_from": iv_note, "implied_vol": r4(iv) if iv else None}
        texts = {"up": "Will %s close above $%.2f (today's price) on %s?" % (t, px, due),
                 "fall10": "Will %s close at or below $%.2f (10%% under today's price) on any day up to %s?" % (t, px * 0.90, due),
                 "fall25": "Will %s close at or below $%.2f (25%% under today's price) on any day up to %s?" % (t, px * 0.75, due),
                 "beat": "Will %s do better than the S&P 500 index fund from today to %s?" % (t, due)}

        def rec(kind, sim, base, cases, months, optp, own_rate, plain, alts, text, lv_up=None, lv_dn=None):
            raw = combine(sim, base, cases, months, optp)
            adj = float(adjust.get("%.1f" % band_of(raw["raw"]), 0.0) or 0.0)
            f = combine(sim, base, cases, months, optp, adj)
            f.update({"q": text, "words": words(f["p"]), "sim": r4(sim, 3), "base": r4(base, 3) if base is not None else None, "cases": cases, "months": months,
                      "opt": r4(optp, 3) if optp is not None else None, "own": r4(own_rate, 3) if own_rate is not None else None, "own_cases": int(len(own_I)),
                      "plain": r4(plain, 3) if plain is not None else None, "movers": movers(sim, alts)})
            f["note"] = ("The three sources disagree by more than %d points, so the range is wide; no single figure should be trusted here. " % round(100 * WIDE) if f["disagree"] else "") + (
                "Too few similar past cases to rely on (%d), so the base rate is shown but not counted, and the figure is kept between 10%% and 90%%. " % cases if f["few"] else "") + (
                "Adjusted by %+d points for its own past bias in this band. " % round(100 * adj) if adj else "") + "An estimate, not a promise."
            H["f"][kind] = f
            if h != "by" or kind in ("tp_first", "stop_first"):
                logs.append({"t": t, "kind": kind, "h": h, "d": d, "due": due, "q": text, "p": f["p"], "lo": f["lo"], "hi": f["hi"], "plain": f["plain"], "ref": r4(px, 4),
                             "up": r4(lv_up, 4) if lv_up else None, "dn": r4(lv_dn, 4) if lv_dn else None, "sim": f["sim"], "base": f["base"], "opt": f["opt"], "cases": cases, "move": month_move})
        for k in (KINDS if h != "by" else ()):
            alts = [(txt, alt[nm][0][k]) for nm, txt in alt_txt] + [("the trend flips (%s its 200-day average): similar past cases then gave" % ("below" if cell >= 6 else "above"), bf[k])]
            rec(k, sp[k], br[k], nb, mo, ob.get(k), own.get(k), pl[k], alts, texts[k])
        if up:
            a, b = touch_first(P0, up, dn)
            tr = touch_rate(shares, per, cell, d, up, dn) if cell >= 0 else (None, None, 0, 0)
            oa = ob2 = None
            if Pb is not None:
                oa, ob2 = [float(np.mean(z)) for z in touch_first(Pb, up, dn)]
            al_t, al_s = [], []
            for nm, txt in alt_txt:
                za, zb = touch_first(alt[nm][1], up, dn)
                al_t.append((txt, float(np.mean(za))))
                al_s.append((txt, float(np.mean(zb))))
            tq = "Will %s close at or above $%.2f%s on or before %s?" % (t, px * up, (" before it closes at or below $%.2f," % (px * dn)) if dn else "", due)
            rec("tp_first", float(np.mean(a)), tr[0], tr[2], tr[3], oa, None, 0.5, al_t, tq, up, dn)
            if dn:
                sq = "Will %s close at or below $%.2f before it closes at or above $%.2f, on or before %s?" % (t, px * dn, px * up, due)
                rec("stop_first", float(np.mean(b)), tr[1], tr[2], tr[3], ob2, None, 0.5, al_s, sq, up, dn)
        out["h"][h] = H
    # the one line for the card
    hk = "by" if "by" in out["h"] else "1y"
    f = out["h"][hk]["f"].get("tp_first") if up else None
    if f:
        out["line"] = "%d%% to reach $%.2f %s (range %d to %d%%, %s)" % (round(100 * f["p"]), px * up, ("before $%.2f" % (px * dn)) if dn else ("by " + out["h"][hk]["due"]),
                                                                       round(100 * f["lo"]), round(100 * f["hi"]),
                                                                       ("from %d similar cases" % f["cases"]) if not f["few"] else "too few similar cases to rely on")
        out["plan"] = {"target": r4(px * up, 2), "stop": r4(px * dn, 2) if dn else None, "kind": plan.get("kind"), "horizon": hk, "due": out["h"][hk]["due"]}
    else:
        f = out["h"]["3m"]["f"]["up"]
        out["line"] = "%d%% to be higher in three months (range %d to %d%%, %s)" % (round(100 * f["p"]), round(100 * f["lo"]), round(100 * f["hi"]),
                                                                                    ("from %d similar cases" % f["cases"]) if not f["few"] else "too few similar cases to rely on")
    return out, logs


def portfolio_forecast(by, ctx, snap, max_loss, rf, adjust, rng):
    cal = ctx["cal"]
    pos = [(p.get("ticker"), float(p.get("pct_nav") or 0) / (100.0 if float(p.get("pct_nav") or 0) > 1.5 else 1.0)) for p in snap.get("positions") or []]
    have = [(t, w) for t, w in pos if t in by and w > 0 and by[t]["b"] == ctx["n"]]
    if not have:
        return {"none": "No holding has a long enough price history to forecast the portfolio."}, []
    a, b = max(by[t]["a"] for t, w in have), min(by[t]["b"] for t, w in have)
    if b - a < MIN_DAYS:
        return {"none": "Not enough shared history to forecast the portfolio: the youngest holding has %d trading days of prices, and %d are needed." % (b - a, MIN_DAYS)}, []
    rp = np.zeros(b - a - 1)
    mu = 0.0
    sa = ctx["spy"][a:b]
    rs = sa[1:] / sa[:-1] - 1
    for t, w in have:
        x = by[t]["x"][a - by[t]["a"]:b - by[t]["a"]]
        rt = x[1:] / x[:-1] - 1
        rp += w * rt
        mu += w * beta_mu(rt, rs, rf)
    rp, rs = rp[-SIM_DAYS:], rs[-SIM_DAYS:]
    val = np.concatenate([[1.0], np.cumprod(1 + rp)])
    out = {"as_of": cal[b - 1], "covers": r4(sum(w for t, w in have), 3), "assume": {"mu": r4(mu), "vol": r4(float(np.std(rp[-252:], ddof=1) * math.sqrt(252))), "years": r4(len(rp) / 252.0, 1)},
           "max_loss": max_loss, "h": {}, "note": "Today's weights are held fixed; cash is counted as earning nothing. History starts when the youngest holding listed (%s), so the base rate rests on few cases." % cal[a][:7]}
    logs, w = [], dict((t, r4(wt, 4)) for t, wt in have)
    for h, d in HZ:
        due = due_date(cal[b - 1], d)
        P0, _ = simulate(rp, rs, mu, rf + 0.05, d, RUNS, rng)
        end = P0[:, -1]
        I = np.arange(0, len(val) - d, d)
        own_end = val[I + d] / val[I] if len(I) else np.zeros(0)
        q = np.percentile(end, [5, 25, 50, 75, 95]) - 1
        H = {"due": due, "days": d, "label": HN[h], "range50": [r4(q[1], 3), r4(q[3], 3)], "range90": [r4(q[0], 3), r4(q[4], 3)], "median": r4(q[2], 3), "f": {}}
        kinds = [("port_loss", "Will the portfolio at today's weights be worth less on %s than today?" % due, 0.0)]
        if h == "1y" and max_loss:
            kinds.append(("port_max", "Will the portfolio at today's weights be down more than %s (your maximum loss) on %s?" % (E.pc(max_loss, 0), due), max_loss))
        for kind, text, lvl in kinds:
            sim = float(np.mean(end < 1.0 - lvl))
            base = float(np.mean(own_end < 1.0 - lvl)) if len(own_end) else None
            raw = combine(sim, base, len(own_end), len(own_end), None)
            adj = float(adjust.get("%.1f" % band_of(raw["raw"]), 0.0) or 0.0)
            f = combine(sim, base, len(own_end), len(own_end), None, adj)
            f.update({"q": text, "words": words(f["p"]), "sim": r4(sim, 3), "base": r4(base, 3) if base is not None else None, "cases": int(len(own_end)), "months": int(len(own_end)), "opt": None,
                      "plain": 0.5, "movers": [], "note": ("Too few past cases to rely on (%d %s periods in the portfolio's own history), so the figure rests on the simulation. " % (len(own_end), HN[h].replace("one ", ""))
                                                             if f["few"] else "") + "An estimate, not a promise."})
            H["f"][kind] = f
            logs.append({"t": "PORT", "kind": kind, "h": h, "d": d, "due": due, "q": text, "p": f["p"], "lo": f["lo"], "hi": f["hi"], "plain": 0.5, "ref": 1.0, "dn": r4(lvl, 4) if lvl else None,
                         "sim": f["sim"], "base": f["base"], "cases": f["cases"], "w": w, "move": 9})
        out["h"][h] = H
    return out, logs


def plans_from(dec, by):
    # the target and stop each forecast is asked about: your own target and maximum-loss line for a holding you keep,
    # the card's take-profit and stop for an idea
    out, holds = {}, dec.get("holds") or {}
    for t, k in (dec.get("keeps") or {}).items():
        if t in by and k.get("target"):
            stop = [lv.get("price") for lv in (holds.get(t) or {}).get("levels") or [] if str(lv.get("name") or "").startswith("Maximum-loss")]
            days = None
            if k.get("by"):
                try:
                    days = int(np.busday_count(np.datetime64(str(by[t]["last"])), np.datetime64(str(k["by"])[:10])))
                except Exception:
                    days = None
            out[t] = {"kind": "your target and review date", "target": float(k["target"]), "stop": float(stop[0]) if stop and stop[0] else None,
                      "days": max(21, min(days, 504)) if days and days > 5 else None}
    for c in dec.get("cards") or []:
        t = c.get("ticker")
        if c.get("status") == "open" and t in by and t not in out and c.get("take_profit") and c.get("stop"):
            out[t] = {"kind": "the card's take-profit and stop", "target": float(c["take_profit"]), "stop": float(c["stop"]), "days": None}
    return out


def read_json(rel, default):
    try:
        with open(os.path.join(E.ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(rel, obj):
    path = os.path.join(E.ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.write(NL)


def run(shares, ctx, meta, targets, limits, load, save):
    quant, dec, snap = E.rj("state/quant.json", {}) or {}, E.rj("state/decisions.json", {}) or {}, E.rj("treasury/snapshot.json", {}) or {}
    opts = (E.rj("state/options.json", {}) or {}).get("shares") or {}
    rf = float(ctx.get("rf") or 0.04)
    cal, made = ctx["cal"], ctx["cal"][-1]
    by = {s["t"]: s for s in shares}
    for s in shares:
        s["last"] = cal[s["b"] - 1]
    rng = np.random.default_rng(SEED)
    tab, per = pooled(shares, ctx)
    # 1. score what has come due, before anything new is said
    log = read_json("state/forecasts/log.json", {"entries": []})
    entries = log.get("entries") or []
    intact = chain_ok(entries)
    scores = read_json("state/forecasts/scores.json", {})
    for e in entries:
        if e["id"] not in scores:
            o = score_entry(e, by, ctx)
            if o is not None:
                scores[e["id"]] = {"o": o, "on": made}
    done = [(e, scores[e["id"]]["o"]) for e in entries if e["id"] in scores]
    live = summarise([e["p"] for e, o in done], [o for e, o in done], [e.get("plain") if e.get("plain") is not None else 0.5 for e, o in done], [e["kind"] for e, o in done])
    adjust = live.get("adjust") or {}
    # 2. today's forecasts
    plans = plans_from(dec, by)
    held = [p.get("ticker") for p in snap.get("positions") or [] if p.get("ticker")]
    desk = [c.get("ticker") for c in dec.get("cards") or [] if c.get("status") == "open" and c.get("ticker")]
    out_t, new = {}, []
    for t in list(dict.fromkeys(held + desk)):
        s = by.get(t)
        if s is None:
            out_t[t] = {"none": "Not enough history to forecast this: no long price history for %s in the free source." % t}
            continue
        if s["b"] != ctx["n"]:
            out_t[t] = {"none": "No forecast: the price history for %s stops at %s." % (t, s["last"])}
            continue
        try:
            rec, logs = share_forecast(s, ctx, tab, per, shares, opts.get(t), plans.get(t), rf, adjust, rng)
            rec["name"], rec["held"] = (meta.get(t) or {}).get("name") or t, t in held
            out_t[t] = rec
            new += logs
        except Exception as e:
            out_t[t] = {"none": "The forecast for %s could not be worked out this run (%s)." % (t, type(e).__name__)}
            limits.append("Forecaster: %s failed (%s: %s)." % (t, type(e).__name__, str(e)[:100]))
    max_loss = float(((quant.get("profile") or {}).get("max_loss_pct") or 0)) / 100.0
    try:
        port, plogs = portfolio_forecast(by, ctx, snap, max_loss, rf, adjust, rng)
        new += plogs
    except Exception as e:
        port = {"none": "The portfolio forecast could not be worked out this run (%s)." % type(e).__name__}
        limits.append("Forecaster: portfolio failed (%s: %s)." % (type(e).__name__, str(e)[:100]))
    # 3. the log
    added = append_log(entries, new, made, ctx["idx"]) if intact else 0
    if not intact:
        limits.append("Forecaster: the forecast log failed its fingerprint check, so nothing was added to it. It must be looked at by hand.")
    write_json("state/forecasts/log.json", {"entries": entries, "note": "Written once, never edited. Each entry's hash covers the entry and the hash before it."})
    write_json("state/forecasts/scores.json", scores)
    # 4. the back-test of the method
    try:
        bt = backtest(shares, ctx, tab, per, set(targets) | set(held), rf, load, save)
    except Exception as e:
        bt = {"checked": 0, "verdict": "The back-test did not run (%s)." % type(e).__name__}
        limits.append("Forecaster: back-test failed (%s: %s)." % (type(e).__name__, str(e)[:100]))
    recent = [{"id": e["id"], "made": e["made"], "t": e["t"], "q": e["q"], "p": e["p"], "lo": e["lo"], "hi": e["hi"], "due": e["due"],
               "o": (scores.get(e["id"]) or {}).get("o")} for e in entries[-400:]]
    E.wj("state/forecasts.json", {
        "as_of": E.now_iso(), "made": made, "version": VERSION, "targets": out_t, "portfolio": port,
        "log": {"count": len(entries), "added": added, "intact": intact, "first": entries[0]["made"] if entries else None, "open": len(entries) - len(done), "recent": recent},
        "score": live, "backtest": bt,
        "agent": {"name": "Forecaster", "level": "A1", "job": "Predictions and their probabilities only. It does not pick shares and does not argue for an idea.",
                  "rule": "The Councillor may not raise a card without a forecast from it."},
        "method": "Three sources, each shown: 10,000 simulated futures drawn from the share's own daily price changes in unbroken 21-day stretches (shifted to an assumed yearly return of the risk-free rate plus the share's beta times 5%); how often the same thing happened after similar past setups across every share in the history; and what option prices imply. The headline is their plain average. The range covers all sources and the uncertainty of the base rate, and is widened when the sources are more than 15 points apart. Targets, stops and falls are judged on daily closing prices.",
        "honesty": "Every figure is an estimate, not a promise. Similar past cases come from today's large companies, which leaves out firms that failed and so flatters the good outcomes. Fewer than 20 cases: too few to rely on."})
    return {"targets": len([1 for v in out_t.values() if not v.get("none")]), "logged": added, "checked": len(done)}
