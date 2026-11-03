"""Earnings predictions: before each call, what the company will report and how the share will react; after it, the
next days' drift; every prediction logged on the day it is made and scored afterwards. Plain code, standard library.

Ben, 3 Nov 2026. Sources, all free:
  - dates, before-open or after-close, EPS consensus and analyst count: Nasdaq's earnings calendar (no key)
  - second source for the date: the hourly pipeline's Twelve Data earnings date (digests/latest.json)
  - beat/miss history: state/earnings/history/<T>.json, seeded from Alpha Vantage and kept current from Nasdaq's
    earnings-surprise feed (the last four quarters, no key)
  - revenue consensus: only where a seed file has it (state/earnings/consensus/<T>.json); no free source in code
  - the options market's expected move: Cboe's free delayed option chain (at-the-money straddle)
  - past price reactions: the engine's own daily closes
  - what management said: the Earnings Reader routine (an agent) writes state/earnings/reads/<T>-<date>.json
Every probability and range comes from counting past cases. Fewer than 20 cases is labelled too few to rely on.
These are estimates, never promises. Nothing here places an order.
"""
import datetime
import json
import math
import os
import re
import sys
import urllib.request

ROOT = os.environ.get("MC_ROOT", ".")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
BAND = 0.02          # a surprise within 2% of consensus counts as in line
SHRINK = 8           # the pooled history of other shares counts as 8 of this share's own calls
FEW = 20             # fewer cases than this: "too few cases to rely on"
JUDGE = 30           # scored calls needed before the record is judged
WINDOW_DAYS = 30
TAX = 0.15
FEE = 0.02
SCEN = ("beat", "inline", "miss")
WORDS = {"beat": "beats EPS consensus by more than 2%", "inline": "within 2% of EPS consensus", "miss": "misses EPS consensus by more than 2%"}
HONEST = "Estimates from counting past cases, never promises. You decide and place every order."


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
        json.dump(obj, f, indent=1)
        f.write("\n")


def http_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def num(v):
    try:
        if v in (None, "", "None", "N/A", "--"):
            return None
        return float(str(v).replace("$", "").replace(",", "").replace("(", "-").replace(")", ""))
    except Exception:
        return None


def day(s):
    return datetime.date.fromisoformat(str(s)[:10])


def r4(x, n=4):
    return None if x is None else round(float(x), n)


# ---------------------------------------------------------------- history: what was reported against consensus
def surprise(eps, est):
    if eps is None or est is None or est == 0:
        return None
    return (eps - est) / abs(est)


def scenario(s):
    if s is None:
        return None
    return "beat" if s > BAND else ("miss" if s < -BAND else "inline")


def merge_rows(old, new):
    # one row per report date; a newer source for the same date replaces the older one (Nasdaq over the seed)
    by = dict((r["date"], r) for r in old or [])
    for r in new or []:
        if r.get("date"):
            keep = by.get(r["date"]) or {}
            by[r["date"]] = dict(keep, **dict((k, v) for k, v in r.items() if v is not None))
    return sorted(by.values(), key=lambda r: r["date"])


def nasdaq_surprises(t):
    try:
        rows = ((http_json("https://api.nasdaq.com/api/company/%s/earnings-surprise" % t).get("data") or {}).get("earningsSurpriseTable") or {}).get("rows") or []
    except Exception:
        return []
    out = []
    for r in rows:
        try:
            m, d, y = [int(x) for x in str(r.get("dateReported")).split("/")]
        except Exception:
            continue
        out.append({"date": "%04d-%02d-%02d" % (y, m, d), "eps": num(r.get("eps")), "est": num(r.get("consensusForecast")), "source": "Nasdaq"})
    return out


def nasdaq_day(d):
    try:
        return (http_json("https://api.nasdaq.com/api/calendar/earnings?date=%s" % d).get("data") or {}).get("rows") or []
    except Exception:
        return None


def calendar(tickers, today, days=WINDOW_DAYS, fetch=nasdaq_day):
    # the next call of each share within the window, from Nasdaq's calendar
    out, failed = {}, 0
    for i in range(days + 1):
        d = today + datetime.timedelta(days=i)
        if d.weekday() >= 5:
            continue
        rows = fetch(str(d))
        if rows is None:
            failed += 1
            continue
        for r in rows:
            t = r.get("symbol")
            if t in tickers and t not in out:
                tm = str(r.get("time") or "")
                out[t] = {"date": str(d), "time": "bmo" if "pre" in tm else ("amc" if "after" in tm else "unknown"),
                          "eps_consensus": num(r.get("epsForecast")), "estimates": int(num(r.get("noOfEsts")) or 0) or None,
                          "fiscal": r.get("fiscalQuarterEnding"), "last_year_eps": num(r.get("lastYearEPS"))}
    return out, failed


# ---------------------------------------------------------------- price reactions
def reaction(closes, date, time):
    # next-day and five-day moves from the last close before the news, and the drift after the reaction day
    ds = [str(d)[:10] for d, c in closes]
    cs = [float(c) for d, c in closes]
    if not ds:
        return None
    date = str(date)[:10]
    if time == "amc":
        base = max([i for i, d in enumerate(ds) if d <= date], default=None)
        r = base + 1 if base is not None else None
    else:
        r = next((i for i, d in enumerate(ds) if d >= date), None)
        base = r - 1 if r is not None else None
    if base is None or r is None or base < 0 or r >= len(cs) or cs[base] <= 0:
        return None
    out = {"base_date": ds[base], "day": ds[r], "r1": cs[r] / cs[base] - 1}
    if r + 4 < len(cs):
        out["r5"] = cs[r + 4] / cs[base] - 1
    if r + 5 < len(cs):
        out["d5"] = cs[r + 5] / cs[r] - 1
    if r + 20 < len(cs):
        out["d20"] = cs[r + 20] / cs[r] - 1
    return out


def cases(t, rows, closes):
    out = []
    for row in rows:
        s = surprise(row.get("eps"), row.get("est"))
        rx = reaction(closes, row["date"], row.get("time") or "bmo") if closes else None
        if s is None or not rx:
            continue
        out.append(dict(rx, t=t, date=row["date"], surprise=s, scen=scenario(s)))
    return out


# ---------------------------------------------------------------- counting, with the pooled history as a prior
def wquant(pairs, qs):
    # weighted quantiles of (value, weight) pairs
    pts = sorted((v, w) for v, w in pairs if v is not None and w > 0)
    tot = sum(w for v, w in pts)
    if not pts or tot <= 0:
        return [None] * len(qs)
    out = []
    for q in qs:
        acc, val = 0.0, pts[-1][0]
        for v, w in pts:
            acc += w
            if acc >= q * tot:
                val = v
                break
        out.append(val)
    return out


def blend(own, pool, key, scale=1.0):
    # own cases weigh 1 each; the pool weighs SHRINK in total, its moves scaled to this share's size of move
    pairs = [(c.get(key), 1.0) for c in own if c.get(key) is not None]
    pv = [c.get(key) for c in pool if c.get(key) is not None]
    if pv:
        w = SHRINK / len(pv)
        pairs += [(v * scale, w) for v in pv]
    return pairs


def predict(t, call, own, pool, implied=None, consensus=None):
    own = sorted(own, key=lambda c: c["date"])[-20:]
    n = len(own)
    own_abs = [abs(c["r1"]) for c in own]
    pool_abs = [abs(c["r1"]) for c in pool]
    scale = (sum(own_abs) / n) / (sum(pool_abs) / len(pool_abs)) if n >= 4 and pool_abs and sum(pool_abs) > 0 else 1.0
    # how often each outcome happened: this share's own calls, shrunk towards the pool
    pool_freq = dict((s, (sum(1 for c in pool if c["scen"] == s) / len(pool)) if pool else 1.0 / 3) for s in SCEN)
    p = dict((s, (sum(1 for c in own if c["scen"] == s) + SHRINK * pool_freq[s]) / (n + SHRINK)) for s in SCEN)
    table, mix1, mix5 = [], [], []
    for s in SCEN:
        o, q = [c for c in own if c["scen"] == s], [c for c in pool if c["scen"] == s]
        pr1, pr5 = blend(o, q, "r1", scale), blend(o, q, "r5", scale)
        up_pool = (sum(1 for c in q if c["r1"] > 0) / len(q)) if q else 0.5
        p_up = (sum(1 for c in o if c["r1"] > 0) + SHRINK * up_pool) / (len(o) + SHRINK)
        q1, q5 = wquant(pr1, (0.1, 0.25, 0.5, 0.75, 0.9)), wquant(pr5, (0.1, 0.5, 0.9))
        table.append({"scenario": s, "words": WORDS[s], "chance": r4(p[s], 3), "p_up_next_day": r4(p_up, 3),
                      "next_day": {"p10": r4(q1[0]), "p25": r4(q1[1]), "median": r4(q1[2]), "p75": r4(q1[3]), "p90": r4(q1[4])},
                      "five_days": {"p10": r4(q5[0]), "median": r4(q5[1]), "p90": r4(q5[2])},
                      "own_cases": len(o), "pool_cases": len(q), "few": len(o) < FEW})
        tw1, tw5 = sum(w for v, w in pr1) or 1.0, sum(w for v, w in pr5) or 1.0
        mix1 += [(v, p[s] * w / tw1) for v, w in pr1]
        mix5 += [(v, p[s] * w / tw5) for v, w in pr5]
    q1 = wquant(mix1, (0.1, 0.25, 0.5, 0.75, 0.9))
    q5 = wquant(mix5, (0.1, 0.5, 0.9))
    tw = sum(w for v, w in mix1) or 1.0
    p_up = sum(x["chance"] * x["p_up_next_day"] for x in table)
    exp_abs = sum(abs(v) * w for v, w in mix1) / tw
    own_avg = (sum(own_abs) / n) if n else None
    big = (sum(w for v, w in mix1 if abs(v) > implied) / tw) if implied else None
    # our EPS estimate: consensus moved by this share's typical surprise over its last eight calls
    last8 = [c["surprise"] for c in own[-8:]]
    med = sorted(last8)[len(last8) // 2] if last8 else None
    cons = (consensus or {}).get("eps") if consensus else None
    cons = cons if cons is not None else call.get("eps_consensus")
    ours = cons + abs(cons) * med if (cons is not None and med is not None) else None
    rev = (consensus or {}).get("revenue")
    rv = [r for r in (consensus or {}).get("_rows") or [] if r.get("rev") and r.get("rev_est")]
    rb = sum(1 for r in rv if r["rev"] > r["rev_est"] * (1 + 0.005))
    p_rev = (rb + 4 * 0.5) / (len(rv) + 4) if rv else None
    return {"_mix1": mix1, "ticker": t, "call": call, "own_cases": n, "pool_cases": len(pool), "few": n < FEW,
            "eps": {"consensus": cons, "consensus_source": (consensus or {}).get("eps_source") or "Nasdaq calendar", "analysts": call.get("estimates"),
                    "ours": r4(ours, 3), "ours_method": "consensus moved by the company's median surprise over its last %d calls (%s)" % (
                        len(last8), "%+.1f%%" % (100 * med) if med is not None else "none"),
                    "p_beat": r4(p["beat"], 3), "p_inline": r4(p["inline"], 3), "p_miss": r4(p["miss"], 3)},
            "revenue": {"consensus": rev, "source": (consensus or {}).get("revenue_source"), "note": None if rev else "no free source for revenue consensus in the code yet",
                        "p_beat": r4(p_rev, 3), "cases": len(rv), "few": len(rv) < FEW,
                        "method": "past revenue beats (more than 0.5%% over consensus) in %d calls, shrunk towards an even chance (counted as 4 calls)" % len(rv) if rv else None},
            "guidance": guidance(t),
            "drivers": drivers(t),
            "past_reactions": {"cases": n, "mean_next_day": r4(sum(c["r1"] for c in own) / n) if n else None,
                               "mean_abs_next_day": r4(own_avg), "range_next_day": [r4(min(c["r1"] for c in own)), r4(max(c["r1"] for c in own))] if n else None,
                               "mean_five_day": r4(sum(c["r5"] for c in own if "r5" in c) / max(1, sum(1 for c in own if "r5" in c))) if n else None,
                               "list": [{"date": c["date"], "surprise": r4(c["surprise"], 3), "next_day": r4(c["r1"]), "five_days": r4(c.get("r5"))} for c in own[-12:]]},
            "implied_move": r4(implied),
            "scenarios": table,
            "overall": {"p_up_next_day": r4(p_up, 3), "next_day": {"p10": r4(q1[0]), "p25": r4(q1[1]), "median": r4(q1[2]), "p75": r4(q1[3]), "p90": r4(q1[4])},
                        "five_days": {"p10": r4(q5[0]), "median": r4(q5[1]), "p90": r4(q5[2])},
                        "expected_abs_move": r4(exp_abs), "p_bigger_than_implied": r4(big, 3)},
            "method": ("Chances count this share's last %d calls, shrunk towards %d calls of the other shares (they count as %d calls); "
                       "the pooled moves are scaled to this share's typical size of move (x%.2f). Ranges are the 10th to 90th percentile."
                       % (n, len(pool), SHRINK, scale)),
            "honesty": ("too few cases to rely on (%d own calls)" % n) if n < FEW else HONEST}


def guidance(t):
    # raised / kept / cut, counted from the calls the reader has read; until then it is not measured
    reads = [r for r in read_files(t) if r.get("guidance") in ("raised", "kept", "cut")]
    n = len(reads)
    if not n:
        return {"cases": 0, "note": "not measured yet: guidance is read from each call's transcript from now on (too few cases to rely on)"}
    cnt = dict((g, sum(1 for r in reads if r["guidance"] == g)) for g in ("raised", "kept", "cut"))
    return {"cases": n, "p_raised": r4((cnt["raised"] + 1) / (n + 3), 3), "p_kept": r4((cnt["kept"] + 1) / (n + 3), 3), "p_cut": r4((cnt["cut"] + 1) / (n + 3), 3),
            "few": n < FEW, "reasons": [r.get("guidance_quote") for r in reads[-2:] if r.get("guidance_quote")]}


def read_files(t):
    import glob
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "state", "earnings", "reads", "%s-*.json" % t))):
        try:
            out.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    return out


def drivers(t):
    reads = [r for r in read_files(t) if r.get("drivers_next")]
    if not reads:
        return {"items": [], "note": "not read yet: the Earnings Reader names them from the previous call's transcript"}
    r = reads[-1]
    return {"items": r["drivers_next"][:3], "from": r.get("call_date"), "source": r.get("source")}


# ---------------------------------------------------------------- the options market's expected move
def implied_move(t, call_day, fetch=None):
    # at-the-money straddle of the first expiry on or after the reaction day, as a share of the price
    try:
        d = (fetch or http_json)("https://cdn.cboe.com/api/global/delayed_quotes/options/%s.json" % t)["data"]
    except Exception:
        return None, None
    px = num(d.get("current_price"))
    if not px:
        return None, None
    best = {}
    for o in d.get("options") or []:
        m = re.match(r"^%s(\d{6})([CP])(\d{8})$" % re.escape(t), str(o.get("option")))
        if not m:
            continue
        exp = "20%s-%s-%s" % (m.group(1)[:2], m.group(1)[2:4], m.group(1)[4:])
        if exp < str(call_day):
            continue
        k = int(m.group(3)) / 1000.0
        bid, ask = num(o.get("bid")), num(o.get("ask"))
        if not bid or not ask or ask <= 0:
            continue
        best.setdefault(exp, {}).setdefault(k, {})[m.group(2)] = (bid + ask) / 2
    for exp in sorted(best):
        ks = [k for k, v in best[exp].items() if "C" in v and "P" in v]
        if ks:
            k = min(ks, key=lambda k: abs(k - px))
            return (best[exp][k]["C"] + best[exp][k]["P"]) / px, exp
    return None, None


# ---------------------------------------------------------------- your position through the call
def position(t, pred, snap, plans, keeps):
    p = next((x for x in snap.get("positions") or [] if x.get("ticker") == t), None)
    if not p:
        return None
    mv, qty, cost = num(p.get("market_value")) or 0.0, num(p.get("qty")) or 0.0, num(p.get("cost_basis")) or 0.0
    px = (mv / qty) if qty else num(p.get("last_price"))
    plan = next((x for x in plans if x.get("ticker") == t), {}) or {}
    stop = num(plan.get("stop"))
    o = pred["overall"]["next_day"]
    out = {"value": r4(mv, 2), "shares": r4(qty, 6), "price": r4(px, 2), "kept": t in (keeps or {})}
    if stop and px:
        gap = stop / px - 1
        # chance of a next-day close under the stop: the weighted share of past reactions (own and pooled) that fell that far
        mix = pred.get("_mix1") or []
        tw = sum(w for v, w in mix) or 1.0
        pb = sum(w for v, w in mix if v is not None and v <= gap) / tw
        worst = o["p10"]
        out.update({"stop": stop, "stop_gap": r4(gap), "p_below_stop": r4(pb, 3), "p_below_stop_words": ("under 1%" if pb < 0.01 else None),
                    "stop_jump": ("In the worst 10%% of cases the share opens at about $%.2f (%+.1f%%), $%.2f under the stop: a stop order would fill there, about $%.2f more loss than at the stop."
                                  % (px * (1 + worst), 100 * worst, stop - px * (1 + worst), qty * (stop - px * (1 + worst)))) if worst is not None and px * (1 + worst) < stop else
                                 "Even the worst 10% of past reactions stays above the stop."})
    gain = mv - cost
    tax_close = round(TAX * gain, 2) if gain > 0 else 0.0
    med, lo, hi = o["median"], o["p10"], o["p90"]
    out["choices"] = [
        {"choice": "hold", "expected_next_day": r4(mv * med, 2) if med is not None else None, "worst_10": r4(mv * lo, 2) if lo is not None else None, "best_10": r4(mv * hi, 2) if hi is not None else None, "cost": 0.0},
        {"choice": "reduce by half", "expected_next_day": r4(mv * med / 2, 2) if med is not None else None, "worst_10": r4(mv * lo / 2, 2) if lo is not None else None, "best_10": r4(mv * hi / 2, 2) if hi is not None else None, "cost": r4(FEE + tax_close / 2, 2)},
        {"choice": "close", "expected_next_day": 0.0, "worst_10": 0.0, "best_10": 0.0, "cost": r4(FEE + tax_close, 2)}]
    if out["kept"]:
        out["note"] = "Your decision to keep %s stands; these are the numbers of the earnings risk, not a case for selling." % t
    return out


def cdf(pts, x):
    if not pts:
        return 0.0
    if x <= pts[0][1]:
        return pts[0][0] * (1 if x == pts[0][1] else max(0.0, 0.5))
    for (q0, v0), (q1, v1) in zip(pts, pts[1:]):
        if v0 <= x <= v1:
            return q0 + (q1 - q0) * ((x - v0) / (v1 - v0) if v1 > v0 else 0.0)
    return pts[-1][0] + (1 - pts[-1][0]) * 0.5 if x > pts[-1][1] else 1.0


# ---------------------------------------------------------------- after the call: drift
def drift(scen, r1, own, pool):
    same = [c for c in own + pool if c["scen"] == scen and (c["r1"] > 0) == (r1 > 0) and "d5" in c]
    own_n = sum(1 for c in own if c["scen"] == scen and (c["r1"] > 0) == (r1 > 0) and "d5" in c)
    if not same:
        return {"cases": 0, "note": "no past cases with this outcome"}
    cont5 = sum(1 for c in same if (c["d5"] > 0) == (r1 > 0)) / len(same)
    d20 = [c["d20"] for c in same if "d20" in c]
    q5 = wquant([(c["d5"], 1.0) for c in same], (0.1, 0.5, 0.9))
    q20 = wquant([(v, 1.0) for v in d20], (0.1, 0.5, 0.9))
    return {"cases": len(same), "own_cases": own_n, "p_keeps_direction_5d": r4(cont5, 3), "next_5_days": [r4(v) for v in q5], "next_20_days": [r4(v) for v in q20],
            "few": len(same) < FEW, "method": "past calls of this and the other shares with the same outcome (%s) and the same first-day direction; moves after the reaction day" % scen}


# ---------------------------------------------------------------- log, score, back-test
def log_path():
    return os.path.join(ROOT, "state", "earnings", "log.jsonl")


def read_log():
    out = []
    try:
        for line in open(log_path(), encoding="utf-8"):
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def append_log(entry):
    # append-only: a prediction is written once, on the day it is made, and never edited
    os.makedirs(os.path.dirname(log_path()), exist_ok=True)
    with open(log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def trading_days_between(a, b):
    n, d = 0, a
    while d < b:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def stage_for(call, today):
    # "early" once the call is within five trading days; "final" on the last day before the news
    cd = day(call["date"])
    if today > cd or (today == cd and call.get("time") == "bmo"):
        return None
    last = (cd == today and call.get("time") == "amc") or (call.get("time") == "bmo" and trading_days_between(today, cd) == 1)
    if last:
        return "final"
    return "early" if trading_days_between(today, cd) <= 5 else None


def score(log, outcomes):
    # every logged prediction whose outcome is known: right or wrong, against the two rivals
    rows = []
    for e in log:
        o = outcomes.get("%s|%s" % (e["t"], e["call_date"]))
        if not o or o.get("r1") is None:
            continue
        up = o["r1"] > 0
        m = abs(o["r1"])
        row = {"id": e["id"], "t": e["t"], "call_date": e["call_date"], "stage": e["stage"], "actual_next_day": r4(o["r1"]),
               "said_p_up": e.get("p_up_1d"), "right_direction": (e.get("p_up_1d") or 0.5) > 0.5 if up else (e.get("p_up_1d") or 0.5) < 0.5,
               "brier_up": r4(((e.get("p_up_1d") or 0.5) - (1 if up else 0)) ** 2), "in_range": (e.get("q10") is not None and e.get("q90") is not None and e["q10"] <= o["r1"] <= e["q90"]),
               "err_ours": r4(abs((e.get("exp_abs") or 0) - m)), "err_implied": r4(abs(e["implied"] - m)) if e.get("implied") else None,
               "err_own_avg": r4(abs(e["own_avg_abs"] - m)) if e.get("own_avg_abs") is not None else None}
        if o.get("scen"):
            row["actual_scenario"] = o["scen"]
            row["brier_beat"] = r4(((e.get("p_beat") or 0) - (1 if o["scen"] == "beat" else 0)) ** 2)
        rows.append(row)
    return rows


def summary(rows, label):
    finals = [r for r in rows if r["stage"] == "final"] or rows
    n = len(finals)
    out = {"label": label, "calls": n}
    if not n:
        out["verdict"] = "No call scored yet."
        return out
    def mean(k):
        v = [r[k] for r in finals if r.get(k) is not None]
        return r4(sum(v) / len(v)) if v else None
    out.update({"right_direction": r4(sum(1 for r in finals if r["right_direction"]) / n, 3), "brier_up": mean("brier_up"), "brier_coin": 0.25,
                "in_range_10_90": r4(sum(1 for r in finals if r["in_range"]) / n, 3),
                "move_error_ours": mean("err_ours"), "move_error_implied": mean("err_implied"), "move_error_own_avg": mean("err_own_avg"),
                "calibration": calibration(finals)})
    if n < JUDGE:
        out["verdict"] = "Too early to judge: %d of the %d calls needed have been scored." % (n, JUDGE)
    else:
        beats = [k for k in ("move_error_implied", "move_error_own_avg") if out.get(k) is not None and out["move_error_ours"] < out[k]]
        coin = " Direction: %.3f error score against 0.250 for a coin flip%s." % (out["brier_up"], "" if out["brier_up"] < 0.25 else ", so no better than a coin")
        out["verdict"] = "Our size-of-move error is %.2f points against %s; direction right %.0f%% of the time." % (
            100 * out["move_error_ours"], ", ".join("%s %.2f" % (k.replace("move_error_", ""), 100 * out[k]) for k in ("move_error_implied", "move_error_own_avg") if out.get(k) is not None),
            100 * out["right_direction"]) + (" It beats %s." % " and ".join(b.replace("move_error_", "") for b in beats) if beats else " It beats neither rival.") + coin
    return out


def calibration(rows):
    out = []
    for lo, hi in ((0, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 1.01)):
        b = [r for r in rows if r.get("said_p_up") is not None and lo <= r["said_p_up"] < hi]
        if b:
            out.append({"said": "%d-%d%%" % (100 * lo, min(100, 100 * hi)), "calls": len(b), "said_avg": r4(sum(r["said_p_up"] for r in b) / len(b), 3),
                        "happened": r4(sum(1 for r in b if r["actual_next_day"] > 0) / len(b), 3), "few": len(b) < FEW})
    return out


def backtest(all_cases, min_prior=8):
    # each past call predicted with only the calls before it (this share's and the pool's), then scored like a live one
    rows = []
    by_t = {}
    for c in all_cases:
        by_t.setdefault(c["t"], []).append(c)
    for t, cs in by_t.items():
        cs = sorted(cs, key=lambda c: c["date"])
        for i, c in enumerate(cs):
            prior = cs[:i]
            if len(prior) < min_prior:
                continue
            pool = [x for x in all_cases if x["t"] != t and x["date"] < c["date"]]
            p = predict(t, {"date": c["date"]}, prior, pool)
            p.pop("_mix1", None)
            e = {"id": "bt|%s|%s" % (t, c["date"]), "t": t, "call_date": c["date"], "stage": "final", "p_up_1d": p["overall"]["p_up_next_day"],
                 "q10": p["overall"]["next_day"]["p10"], "q90": p["overall"]["next_day"]["p90"], "exp_abs": p["overall"]["expected_abs_move"],
                 "own_avg_abs": p["past_reactions"]["mean_abs_next_day"], "implied": None, "p_beat": p["eps"]["p_beat"]}
            rows += score([e], {"%s|%s" % (t, c["date"]): c})
    s = summary(rows, "back-test on past calls")
    if rows:
        beat_rows = [r for r in rows if r.get("brier_beat") is not None]
        s["brier_beat"] = r4(sum(r["brier_beat"] for r in beat_rows) / len(beat_rows)) if beat_rows else None
        s["shares"] = sorted(by_t)
        s["note"] = ("The options market's expected move has no free history, so the back-test compares only with the share's own average past reaction "
                     "and with a coin flip for direction. Cases use only data from before each call.")
    return s, rows


# ---------------------------------------------------------------- the whole run
def tickers_of_interest():
    snap = rj("treasury/snapshot.json", {}) or {}
    held = [p["ticker"] for p in snap.get("positions") or [] if p.get("ticker")]
    watch = [x.get("ticker") if isinstance(x, dict) else x for x in (rj("state/known_companies.json", {}) or {}).get("tickers") or []]
    ideas = [c.get("ticker") for c in (rj("state/decisions.json", {}) or {}).get("cards") or [] if c.get("status") == "open" and c.get("ticker")]
    return [t for t in dict.fromkeys(held + watch + ideas) if t and t not in ("SPY", "portfolio") and re.match(r"^[A-Z.]{1,6}$", t)], set(held)


def run(now=None, closes=None, net=True):
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = day(now)
    closes = closes or (lambda t: [])
    tick, held = tickers_of_interest()
    cal, failed = calendar(set(tick), today) if net else ({}, 0)
    second = dict((k, v.get("next_earnings_date")) for k, v in ((rj("digests/latest.json", {}) or {}).get("technicals") or {}).items() if v.get("next_earnings_date"))
    prev = rj("state/earnings.json", {}) or {}
    if not cal and prev.get("calendar") and failed:
        cal = dict((r["ticker"], r) for r in prev["calendar"] if day(r["date"]) >= today)   # Nasdaq unreachable: keep the last calendar
    for t, d2 in second.items():
        # a share Nasdaq did not list: the pipeline's date alone (one source, time of day unknown)
        if t in tick and t not in cal and d2 and today <= day(d2) <= today + datetime.timedelta(days=WINDOW_DAYS):
            cal[t] = {"date": d2, "time": "unknown", "eps_consensus": None, "estimates": None, "one_source": True}
    # histories, kept current from Nasdaq's last four quarters
    hist, allc, outcomes = {}, [], {}
    # the time of day of each call (before the open or after the close) from the calendars we have seen
    times = dict(("%s|%s" % (r["ticker"], r["date"]), r.get("time")) for r in prev.get("calendar") or [])
    times.update(dict(("%s|%s" % (k, v["date"]), v.get("time")) for k, v in cal.items()))
    for t in tick:
        h = rj("state/earnings/history/%s.json" % t, {"rows": []}) or {"rows": []}
        if net:
            new = nasdaq_surprises(t)
            if new:
                known = dict((x["date"], x.get("time")) for x in h["rows"])
                h["rows"] = merge_rows(h.get("rows"), [dict(r, time=known.get(r["date"]) or times.get("%s|%s" % (t, r["date"]))) for r in new])
                wj("state/earnings/history/%s.json" % t, h)
        hist[t] = h.get("rows") or []
        cs = cases(t, hist[t], closes(t))
        allc += cs
        for c in cs:
            outcomes["%s|%s" % (t, c["date"])] = c
    snap = rj("treasury/snapshot.json", {}) or {}
    plans = (rj("state/plans.json", {}) or {}).get("holdings") or []
    keeps = (rj("state/decisions.json", {}) or {}).get("keeps") or {}
    logged = set(e["id"] for e in read_log())
    preds, rows_cal = {}, []
    for t in tick:
        c = cal.get(t)
        if not c:
            continue
        agree = second.get(t)
        c = dict(c, ticker=t, second_source=agree, sources_agree=(agree == c["date"]) if agree else None)
        rows_cal.append(c)
        if day(c["date"]) < today:
            continue
        own = [x for x in allc if x["t"] == t]
        pool = [x for x in allc if x["t"] != t]
        imp, exp = implied_move(t, c["date"]) if net else (None, None)
        cons = rj("state/earnings/consensus/%s.json" % t, None)
        cons = cons if cons and cons.get("date") == c["date"] else None
        if cons:
            cons = dict(cons, _rows=hist.get(t) or [])
        p = predict(t, c, own, pool, imp, cons)
        p["implied_expiry"] = exp
        if t in held:
            p["position"] = position(t, p, snap, plans, keeps)
        st = stage_for(c, today)
        if st:
            pid = "%s|%s|%s" % (t, c["date"], st)
            p["logged"] = pid
            if pid not in logged:
                append_log({"id": pid, "made_at": now, "t": t, "call_date": c["date"], "time": c["time"], "stage": st,
                            "p_beat": p["eps"]["p_beat"], "p_miss": p["eps"]["p_miss"], "eps_consensus": p["eps"]["consensus"], "eps_ours": p["eps"]["ours"],
                            "p_up_1d": p["overall"]["p_up_next_day"], "q10": p["overall"]["next_day"]["p10"], "q50": p["overall"]["next_day"]["median"],
                            "q90": p["overall"]["next_day"]["p90"], "exp_abs": p["overall"]["expected_abs_move"], "implied": p["implied_move"],
                            "own_avg_abs": p["past_reactions"]["mean_abs_next_day"], "p_bigger_than_implied": p["overall"]["p_bigger_than_implied"],
                            "own_cases": p["own_cases"], "pool_cases": p["pool_cases"]})
                logged.add(pid)
        p.pop("_mix1", None)
        preds[t] = p
    # after the call: the actual result, the read, the drift
    after = {}
    for t in tick:
        rows = hist.get(t) or []
        last = rows[-1] if rows else None
        if not last or (today - day(last["date"])).days > 10:
            continue
        o = outcomes.get("%s|%s" % (t, last["date"]))
        own = [x for x in allc if x["t"] == t and x["date"] < last["date"]]
        pool = [x for x in allc if x["t"] != t]
        s = surprise(last.get("eps"), last.get("est"))
        ours = next((e for e in reversed(read_log()) if e["t"] == t and e["call_date"] == last["date"]), None)
        rd = next((r for r in reversed(read_files(t)) if r.get("call_date") == last["date"]), None)
        after[t] = {"call_date": last["date"], "eps": last.get("eps"), "consensus": last.get("est"), "surprise": r4(s, 4), "scenario": scenario(s),
                    "our_estimate": (ours or {}).get("eps_ours"), "our_p_beat": (ours or {}).get("p_beat"), "predicted": bool(ours),
                    "next_day": r4((o or {}).get("r1")), "five_days": r4((o or {}).get("r5")),
                    "drift": drift(scenario(s), o["r1"], own, pool) if o and s is not None else {"note": "waiting for the first trading day after the call"},
                    "read": rd or {"note": "the Earnings Reader has not read this call's transcript yet"}}
    live = score(read_log(), outcomes)
    bt, _ = backtest(allc)
    out = {"as_of": now, "calendar": sorted(rows_cal, key=lambda r: (r["date"], r["ticker"])), "calendar_failed_days": failed,
           "predictions": preds, "after": after, "score": summary(live, "live predictions"), "scored": live[-30:], "backtest": bt,
           "sources": {"dates": "Nasdaq earnings calendar; checked against the pipeline's Twelve Data date", "history": "Alpha Vantage seed, kept current from Nasdaq",
                       "implied": "Cboe delayed option chain, at-the-money straddle", "prices": "the engine's daily closes", "reads": "Earnings Reader routine (agent)"},
           "honesty": HONEST + " Fewer than %d cases: too few cases to rely on. The record is judged after %d scored calls." % (FEW, JUDGE)}
    wj("state/earnings.json", out)
    return out


def due(now=None):
    # what the Earnings Reader has to read: the previous call of shares reporting within 10 days (drivers), and calls just reported
    today = day(now or datetime.datetime.now(datetime.timezone.utc).isoformat())
    # only shares you hold or that today's action list would buy: reading transcripts is the one step that costs agent time
    e = rj("state/earnings.json", {}) or {}
    held = set(p.get("ticker") for p in (rj("treasury/snapshot.json", {}) or {}).get("positions") or [])
    buys = set(a.get("ticker") or (a.get("buy") or {}).get("ticker") for a in (rj("state/actions.json", {}) or {}).get("actions") or [] if a.get("type") in ("BUY", "SWAP"))
    mine = held | buys
    hist = lambda t: (rj("state/earnings/history/%s.json" % t, {}) or {}).get("rows") or []
    pre = [{"ticker": r["ticker"], "call": r["date"], "read_previous_call": (hist(r["ticker"]) or [{}])[-1].get("date")}
           for r in e.get("calendar") or [] if r["ticker"] in mine and 0 <= (day(r["date"]) - today).days <= 10 and not drivers(r["ticker"]).get("items")]
    post = [{"ticker": t, "call": a["call_date"]} for t, a in (e.get("after") or {}).items()
            if t in mine and (today - day(a["call_date"])).days <= 3 and not any(r.get("call_date") == a["call_date"] for r in read_files(t))]
    return {"pre": pre, "post": post}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "due":
        print(json.dumps(due()))
    else:
        o = run()
        print("earnings: %d calls in the next %d days, %d predictions, %d logged" % (len(o["calendar"]), WINDOW_DAYS, len(o["predictions"]), len(read_log())))
