"""Behaviour model: how investors are likely to act around big events, measured from free data, tested walk-forward,
and fed into the earnings forecasts only where a pattern has earned its place. Plain code, standard library.

Ben, 3 Nov 2026. Signals per share (daily): attention (the pipeline's picks and headlines), options positioning
(Cboe: put/call open interest and volume, puts against calls, implied against realised volatility), short interest
(Nasdaq, Nasdaq-listed shares only), run-up into the event against the share's normal pre-event move, anchors
(52-week high and low, round numbers), insider alerts (state/smart_money.json) and market mood (Cboe's VIX and the
Market Council stress level). Each signal shows today's value, its normal range for the share where a history exists,
and one plain sentence. Missing sources are listed as missing, never guessed.

Patterns are fixed rules, tested on past events using only data from before each event (walk-forward, one event at a
time, rolling forward). A pattern adjusts a forecast only if it improved accuracy out of sample. Estimates, never
promises. Nothing here places an order.
"""
import datetime
import json
import math
import os
import sys

import earnings as ER

ROOT = os.environ.get("MC_ROOT", ".")
FEW, JUDGE, K = 20, 30, 20          # honesty threshold; live judging threshold; shrink weight of a pattern's effect
COST = 0.005                        # round trip used for any trade-style test (as the other back-tests)
RUNUP_Z, STRESS_VIX, STRESS_DD = 1.0, 25.0, -0.10
HONEST = "Estimates from counting past cases, never promises. A pattern counts only if it improved forecasts on data it was not fitted on."


def rj(rel, d=None):
    return ER.rj(rel, d)


def wj(rel, o):
    ER.wj(rel, o)


r4, num = ER.r4, ER.num


def rets(cs):
    return [cs[i] / cs[i - 1] - 1 for i in range(1, len(cs)) if cs[i - 1] > 0]


def sd(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def pct_rank(x, xs):
    xs = [v for v in xs if v is not None]
    return (sum(1 for v in xs if v <= x) / len(xs)) if xs and x is not None else None


def quant(xs, q):
    xs = sorted(v for v in xs if v is not None)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else None


def idx_on_or_before(ds, d):
    lo = None
    for i, x in enumerate(ds):
        if x <= d:
            lo = i
        else:
            break
    return lo


# ---------------------------------------------------------------- market mood
def vix_history(fetch=None):
    try:
        rows = (fetch or ER.http_json)("https://cdn.cboe.com/api/global/delayed_quotes/charts/historical/_VIX.json").get("data") or []
        return [(r["date"], float(r["close"])) for r in rows if r.get("close")]
    except Exception:
        return []


def stressed_at(d, spy, vix):
    # stressed: the VIX at 25 or more, or the S&P 500 fund 10% or more below its 12-month high, on the last close before d
    v = None
    if vix:
        i = idx_on_or_before([x for x, _ in vix], d)
        v = vix[i][1] if i is not None else None
    dd = None
    if spy:
        ds = [x for x, _ in spy]
        i = idx_on_or_before(ds, d)
        if i is not None and i >= 1:
            w = [c for _, c in spy[max(0, i - 251):i + 1]]
            dd = w[-1] / max(w) - 1
    return bool((v is not None and v >= STRESS_VIX) or (dd is not None and dd <= STRESS_DD)), v, dd


# ---------------------------------------------------------------- per-event features, from data before the event only
def features(case, closes):
    ds = [d for d, _ in closes]
    cs = [c for _, c in closes]
    i = idx_on_or_before(ds, case["base_date"])
    if i is None or i < 30:
        return None
    rr = rets(cs[i - 20:i + 1])
    v = sd(rr)
    run = cs[i] / cs[i - 10] - 1
    return {"runup10": run, "vol20": v, "runup_z": (run / (v * math.sqrt(10))) if v else None}


def event_table(tickers, closes, spy, vix):
    out = []
    for t in tickers:
        rows = (rj("state/earnings/history/%s.json" % t, {}) or {}).get("rows") or []
        cl = closes(t)
        for c in ER.cases(t, rows, cl):
            f = features(c, cl)
            if not f:
                continue
            st, v, dd = stressed_at(c["base_date"], spy, vix)
            out.append(dict(c, **f, stressed=st, vix=v, spy_dd=dd))
    return sorted(out, key=lambda e: e["date"])


# ---------------------------------------------------------------- the patterns
COND = {
    "run_up": lambda e: e.get("runup_z") is not None and e["runup_z"] >= RUNUP_Z,
    "stressed": lambda e: bool(e.get("stressed")),
}
RULES = [
    {"id": "sell_the_news", "name": "Buy the rumour, sell the news",
     "rule": "the share rose more than one normal 10-day move into the call (run-up z of 1 or more) and then beat EPS consensus: does it fall the next day?"},
    {"id": "crowded", "name": "Crowded trade", "rule": "heavy positioning one way (put/call ratio or put prices at an extreme for the share) and a surprise the other way",
     "untestable": "no free history of options positioning; recorded daily from 3 Nov 2026, testable once 20 events have it"},
    {"id": "squeeze", "name": "Short squeeze", "rule": "short interest of 5 or more days to cover and good news",
     "untestable": "no free short-interest history for NYSE shares (Nasdaq gives it only for Nasdaq-listed shares)"},
    {"id": "underreaction", "name": "Underreaction (post-earnings drift)",
     "rule": "after a surprise of more than 2%, does the share keep moving in the direction of its first day over the next five days?"},
    {"id": "overreaction", "name": "Overreaction",
     "rule": "a one-day fall of more than three times the share's normal daily move (any day): does it partly bounce back within five days, after a 0.5% round-trip cost?"},
    {"id": "attention_fade", "name": "Attention fade", "rule": "a spike in news attention against the share's normal level: does the move fade back?",
     "untestable": "the pipeline's headline record starts on 21 Sep 2026: too short to test; recorded daily"},
    {"id": "fear_discount", "name": "Fear discount",
     "rule": "in a stressed market (VIX 25 or more, or the S&P 500 fund 10% below its high): do beats move the share less and misses more?"},
]


def describe(events, overs):
    rows = []
    for r in RULES:
        row = dict(r)
        if r.get("untestable"):
            row.update(status="dropped", why=r["untestable"], cases=0)
        elif r["id"] == "sell_the_news":
            c = [e for e in events if COND["run_up"](e) and e["scen"] == "beat"]
            b = [e for e in events if not COND["run_up"](e) and e["scen"] == "beat"]
            row.update(cases=len(c), how_often=r4(sum(1 for e in c if e["r1"] < 0) / len(c), 3) if c else None,
                       base_rate=r4(sum(1 for e in b if e["r1"] < 0) / len(b), 3) if b else None, base_cases=len(b),
                       typical_move=r4(sum(e["r1"] for e in c) / len(c)) if c else None, few=len(c) < FEW)
            row.update(words="beats after a big run-up fell the next day in %s of %d cases, against %s of %d beats without one" % (
                           pc(row.get("how_often") if c else None), len(c), pc(sum(1 for e in b if e["r1"] < 0) / len(b) if b else None), len(b)))
        elif r["id"] == "underreaction":
            c = [e for e in events if abs(e["surprise"]) > ER.BAND and "d5" in e]
            same = [e for e in c if (e["d5"] > 0) == (e["r1"] > 0)]
            row.update(cases=len(c), how_often=r4(len(same) / len(c), 3) if c else None, base_rate=0.5,
                       typical_move=r4(sum(e["d5"] * (1 if e["r1"] > 0 else -1) for e in c) / len(c)) if c else None, few=len(c) < FEW)
            row.update(words="the five days after the first day went the same way in %s of %d cases (a coin is 50%%)" % (pc(row.get("how_often") if c else None), len(c)))
        elif r["id"] == "overreaction":
            drops = [o for o in overs if o["kind"] == "drop"]
            bounce = [o for o in drops if o["next5"] > 0]
            after = [o["next5"] - COST for o in drops]
            row.update(cases=len(drops), how_often=r4(len(bounce) / len(drops), 3) if drops else None, base_rate=None,
                       typical_move=r4(sum(after) / len(after)) if after else None, few=len(drops) < FEW)
            row.update(words="after an extreme one-day fall the next five days were up in %s of %d cases; average %s after costs" % (
                           pc(row.get("how_often") if drops else None), len(drops), sp(row.get("typical_move") if after else None)))
        elif r["id"] == "fear_discount":
            out = {}
            for s in ("beat", "miss"):
                for st in (True, False):
                    xs = [e["r1"] for e in events if e["scen"] == s and bool(e["stressed"]) == st]
                    out["%s_%s" % (s, "stressed" if st else "calm")] = (r4(sum(xs) / len(xs)) if xs else None, len(xs))
            n = out["beat_stressed"][1] + out["miss_stressed"][1]
            row.update(cases=n, few=n < FEW, detail=out,
                       words="beats moved %s in stressed markets (%d cases) against %s in calm ones (%d); misses %s (%d) against %s (%d)" % (
                           sp(out["beat_stressed"][0]), out["beat_stressed"][1], sp(out["beat_calm"][0]), out["beat_calm"][1],
                           sp(out["miss_stressed"][0]), out["miss_stressed"][1], sp(out["miss_calm"][0]), out["miss_calm"][1]))
        rows.append(row)
    return rows


def overreactions(tickers, closes):
    out = []
    for t in tickers:
        cl = closes(t)
        ds, cs = [d for d, _ in cl], [c for _, c in cl]
        for i in range(22, len(cs) - 6):
            r = cs[i] / cs[i - 1] - 1
            v = sd(rets(cs[i - 21:i]))
            if v and abs(r) > 3 * v:
                out.append({"t": t, "date": ds[i], "r": r, "kind": "drop" if r < 0 else "spike", "next5": cs[i + 5] / cs[i] - 1})
    return out


# ---------------------------------------------------------------- the adjustment, and the walk-forward test
def effects(prior):
    # each condition's effect on the chance of a rise and on the size of the move, shrunk by case count
    allr = [e["r1"] for e in prior]
    if len(allr) < 10:
        return {}
    up_all = sum(1 for x in allr if x > 0) / len(allr)
    mag_all = sum(abs(x) for x in allr) / len(allr)
    out = {}
    for k, f in COND.items():
        c = [e for e in prior if f(e)]
        if not c:
            continue
        w = len(c) / (len(c) + K)
        up = sum(1 for e in c if e["r1"] > 0) / len(c)
        mag = sum(abs(e["r1"]) for e in c) / len(c)
        out[k] = {"cases": len(c), "d_up": w * (up - up_all), "f_mag": 1 + w * (mag / mag_all - 1) if mag_all else 1.0}
    return out


def adjust(base_up, base_abs, e, eff, keep):
    d, f, why = 0.0, 1.0, []
    for k, x in eff.items():
        if k in keep and COND[k](e):
            d += x["d_up"]
            f *= x["f_mag"]
            why.append(k)
    up = min(0.95, max(0.05, base_up + d)) if base_up is not None else None
    return up, (base_abs * f if base_abs is not None else None), d, f, why


def walk_forward(events, start=40):
    # every event from the 41st on: the base forecast and the adjusted one, both made only from the events before it
    rows = []
    for i, e in enumerate(events):
        prior = events[:i]
        if i < start:
            continue
        own = [x for x in prior if x["t"] == e["t"]]
        pool = [x for x in prior if x["t"] != e["t"]]
        p = ER.predict(e["t"], {"date": e["date"]}, own, pool)
        p.pop("_mix1", None)
        bu, ba = p["overall"]["p_up_next_day"], p["overall"]["expected_abs_move"]
        eff = effects(prior)
        row = {"t": e["t"], "date": e["date"], "year": e["date"][:4], "up": e["r1"] > 0, "move": abs(e["r1"]), "base_up": bu, "base_abs": ba}
        for name, keep in (("all", set(COND)),) + tuple((k, {k}) for k in COND):
            up, ab, d, f, why = adjust(bu, ba, e, eff, keep)
            row[name] = {"up": up, "abs": ab, "fired": bool(why)}
        rows.append(row)
    return rows


def brier(p, y):
    return (p - (1 if y else 0)) ** 2


def judge(rows):
    out = {"events": len(rows)}
    if not rows:
        return out, set()
    out["base"] = {"brier_up": r4(sum(brier(r["base_up"], r["up"]) for r in rows) / len(rows)), "move_error": r4(sum(abs(r["base_abs"] - r["move"]) for r in rows) / len(rows))}
    keep, per = set(), {}
    for k in ["all"] + list(COND):
        fired = [r for r in rows if r[k]["fired"]]
        b = sum(brier(r["base_up"], r["up"]) for r in rows) / len(rows)
        a = sum(brier(r[k]["up"], r["up"]) for r in rows) / len(rows)
        mb = sum(abs(r["base_abs"] - r["move"]) for r in rows) / len(rows)
        ma = sum(abs(r[k]["abs"] - r["move"]) for r in rows) / len(rows)
        years = sorted(set(r["year"] for r in fired))
        good_years = sum(1 for y in years if sum(brier(r[k]["up"], r["up"]) - brier(r["base_up"], r["up"]) for r in fired if r["year"] == y) < 0)
        per[k] = {"fired_on": len(fired), "brier_up": r4(a), "brier_change": r4(a - b), "move_error": r4(ma), "move_error_change": r4(ma - mb),
                  "years_better": "%d of %d" % (good_years, len(years))}
        if k != "all":
            helps = (a < b or ma < mb) and len(fired) >= FEW and good_years * 2 >= len(years)
            per[k]["kept"] = helps
            per[k]["why"] = ("improved the forecasts out of sample (direction score %+.4f, move error %+.2f points, better in %d of %d years)" % (a - b, 100 * (ma - mb), good_years, len(years))
                             if helps else ("fired on only %d events: too few cases to rely on" % len(fired) if len(fired) < FEW else
                                            "did not improve the forecasts out of sample (direction score %+.4f, move error %+.2f points, better in %d of %d years)" % (a - b, 100 * (ma - mb), good_years, len(years))))
            if helps:
                keep.add(k)
    out["per_condition"] = per
    return out, keep


# ---------------------------------------------------------------- today's readings
def options_now(t, fetch=None):
    try:
        d = (fetch or ER.http_json)("https://cdn.cboe.com/api/global/delayed_quotes/options/%s.json" % t)["data"]
    except Exception:
        return None
    px = num(d.get("current_price"))
    today = datetime.date.today()
    oi = {"C": 0.0, "P": 0.0}
    vol = {"C": 0.0, "P": 0.0}
    otm = {"C": [], "P": []}
    atm = []
    import re
    for o in d.get("options") or []:
        m = re.match(r"^%s(\d{6})([CP])(\d{8})$" % re.escape(t), str(o.get("option")))
        if not m:
            continue
        exp = datetime.date(2000 + int(m.group(1)[:2]), int(m.group(1)[2:4]), int(m.group(1)[4:]))
        days = (exp - today).days
        if days < 0 or days > 60:
            continue
        side = m.group(2)
        oi[side] += num(o.get("open_interest")) or 0
        vol[side] += num(o.get("volume")) or 0
        dl, iv = num(o.get("delta")), num(o.get("iv"))
        if iv and dl is not None and 7 <= days <= 45:
            if 0.2 <= abs(dl) <= 0.3:
                otm[side].append(iv)
            if 0.45 <= abs(dl) <= 0.55:
                atm.append(iv)
    mean = lambda xs: sum(xs) / len(xs) if xs else None
    return {"price": px, "put_call_oi": r4(oi["P"] / oi["C"], 3) if oi["C"] else None, "put_call_volume": r4(vol["P"] / vol["C"], 3) if vol["C"] else None,
            "atm_iv": r4(mean(atm), 4), "put_skew": r4(mean(otm["P"]) - mean(otm["C"]), 4) if otm["P"] and otm["C"] else None}


def short_now(t):
    try:
        d = ER.http_json("https://api.nasdaq.com/api/quote/%s/short-interest?assetClass=stocks" % t).get("data")
        rows = ((d or {}).get("shortInterestTable") or {}).get("rows") or []
        if rows:
            return {"days_to_cover": num(rows[0].get("daysToCover")), "settlement": rows[0].get("settlementDate"), "interest": num(rows[0].get("interest"))}
    except Exception:
        pass
    return None


def pc(v, d=0):
    return "n/a" if v is None else ("%." + str(d) + "f%%") % (100 * v)


def sp(v):
    return "n/a" if v is None else "%+.1f%%" % (100 * v)


def readings(t, closes, events, hist, opt, short, mood, smart, attention, event=None):
    cl = closes(t)
    cs = [c for _, c in cl]
    out = []
    add = lambda name, value, normal, basis, sentence, ok=True: out.append({"name": name, "value": value, "normal": normal, "normal_basis": basis, "sentence": sentence, "available": ok})
    # run-up into the event against the share's normal pre-event move
    if len(cs) > 31:
        v = sd(rets(cs[-21:]))
        run = cs[-1] / cs[-11] - 1
        z = run / (v * math.sqrt(10)) if v else None
        past = [e["runup10"] for e in events if e["t"] == t]
        lo, hi = quant(past, 0.1), quant(past, 0.9)
        add("Run-up (last 10 trading days)", r4(run), [r4(lo), r4(hi)] if past else None, "%d past calls of this share" % len(past),
            ("Moved %s in ten days, %s this share's range before its past calls (%s to %s)%s." % (sp(run), "above" if hi is not None and run > hi else "below" if lo is not None and run < lo else "within",
             sp(lo), sp(hi), "; against its usual daily moves that is a large run-up (%.1f times a normal 10-day move), so some good news may be priced in" % z if z is not None and z >= RUNUP_Z else "")) if past else "Moved %s in ten days; no past calls to compare." % sp(run))
        hi52, lo52 = max(cs[-252:]), min(cs[-252:])
        add("Distance from the 52-week high", r4(cs[-1] / hi52 - 1), None, "one year of closes", "%s below its 52-week high ($%.2f), %s above its low ($%.2f)." % (pc(1 - cs[-1] / hi52, 1), hi52, pc(cs[-1] / lo52 - 1, 1), lo52))
        step = 1 if cs[-1] < 20 else (5 if cs[-1] < 150 else 10)
        rn = round(cs[-1] / step) * step
        add("Nearest round number", rn, None, "price", "The price ($%.2f) is %s from the round number $%s, a level many orders cluster around." % (cs[-1], pc(abs(cs[-1] / rn - 1), 1), rn))
    else:
        add("Run-up (last 10 trading days)", None, None, None, "No price history for this share yet.", False)
    add("Price where most recent volume traded", None, None, None, "Not available: the engine keeps closing prices only, no volume.", False)
    # options positioning, with the share's own recorded history as the normal range once it exists
    h = hist.get("options") or []
    if opt:
        for key, name, sent in (("put_call_oi", "Put/call open interest", "puts against calls held open"), ("put_skew", "Puts against calls (price)", "how much more puts cost than calls")):
            val = opt.get(key)
            past = [x.get(key) for x in h if x.get(key) is not None]
            norm = [r4(quant(past, 0.1)), r4(quant(past, 0.9))] if len(past) >= FEW else None
            add(name, val, norm, ("%d days recorded" % len(past)) if past else "recorded from 3 Nov 2026",
                ("%s: %s, %s." % (sent.capitalize(), val, "unusually high: the crowd is hedged or bearish" if norm and val > norm[1] else "unusually low: little protection bought" if norm and val < norm[0] else "within its normal range")) if norm and val is not None
                else "%s: %s; its normal range appears once %d days are recorded (%d so far)." % (sent.capitalize(), val, FEW, len(past)))
        rv = sd(rets(cs[-21:])) if len(cs) > 21 else None
        iv = opt.get("atm_iv")
        ratio = (iv / (rv * math.sqrt(252))) if iv and rv else None
        add("Options price against actual moves", r4(ratio, 2), None, "implied volatility over the last 20 days' realised volatility",
            "Options price in moves %s than the share has made lately (%.1fx)%s." % ("bigger" if ratio and ratio > 1 else "smaller", ratio or 0, ": the event is expected to move it" if ratio and ratio > 1.3 else "") if ratio else "No option prices to compare.", ratio is not None)
    else:
        add("Options positioning", None, None, None, "No option chain from Cboe for this share today.", False)
    if short:
        add("Short interest (days to cover)", short.get("days_to_cover"), None, "Nasdaq, settlement %s" % short.get("settlement"),
            "%.1f days of normal volume to cover the short positions%s." % (short["days_to_cover"] or 0, ": high enough for a squeeze on good news" if (short["days_to_cover"] or 0) >= 5 else ""))
    else:
        add("Short interest", None, None, None, "Not available: Nasdaq's free short-interest data covers Nasdaq-listed shares only.", False)
    # expectations: the EPS consensus against its value 30 days ago, from the daily snapshots
    cons = hist.get("consensus") or []
    if event and event.get("eps_consensus") is not None and cons:
        old = next((x for x in cons if x["date"] <= str(datetime.date.today() - datetime.timedelta(days=30))), None)
        if old and old.get("eps"):
            ch = event["eps_consensus"] / old["eps"] - 1
            add("EPS estimate change, 30 days", r4(ch), None, "daily snapshots", "Analysts moved the EPS estimate %s in 30 days." % sp(ch))
        else:
            add("EPS estimate change, 30 days", None, None, "daily snapshots from 3 Nov 2026", "Recorded daily from 3 Nov 2026; the 30-day change appears on 3 Dec.", False)
    add("Consensus against company guidance", None, None, None, "Not available: no free source for company guidance; the Earnings Reader records it from each call.", False)
    # attention and insiders
    a = attention.get(t)
    add("Attention (pipeline picks and headlines, 7 days)", a["week"] if a else 0, None, "the pipeline's record since 21 Sep 2026",
        ("%d mentions in 7 days against %.1f a week before: %s." % (a["week"], a["normal"], "a spike" if a["normal"] and a["week"] > 2 * a["normal"] else "normal")) if a else "No mentions by the pipeline in 7 days.")
    s = [x for x in smart if x.get("ticker") == t]
    add("Insider buying and selling (14 days)", len(s), None, "SEC filings via the insider watch", ("%d large insider trades filed: %s." % (len(s), "; ".join(str(x.get("text") or x.get("line") or "")[:90] for x in s[:2]))) if s else "No insider trade of $250,000 or more filed in 14 days.")
    add("Big funds", None, None, None, "Not available: no free daily source for fund flows.", False)
    add("Search and social media", None, None, None, "Not available: no free source the code can read.", False)
    return out


def attention_counts(today):
    h = (rj("digests/history.json", {}) or {}).get("entries") or []
    out = {}
    for e in h:
        d = str(e.get("as_of"))[:10]
        try:
            age = (today - datetime.date.fromisoformat(d)).days
        except Exception:
            continue
        for p in e.get("picks") or []:
            t = p.get("ticker")
            if not t:
                continue
            o = out.setdefault(t, {"week": 0, "prior": 0})
            if age <= 7:
                o["week"] += 1
            elif age <= 37:
                o["prior"] += 1
    for t, o in out.items():
        o["normal"] = round(o["prior"] / (30 / 7.0), 1)
    return out


# ---------------------------------------------------------------- the run
def log_path():
    return os.path.join(ROOT, "state", "behaviour", "log.jsonl")


def read_log():
    out = []
    try:
        for line in open(log_path(), encoding="utf-8"):
            if line.strip():
                out.append(json.loads(line))
    except Exception:
        pass
    return out


def run(now=None, closes=None, net=True):
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    today = ER.day(now)
    closes = closes or (lambda t: [])
    earn = rj("state/earnings.json", {}) or {}
    tick, held = ER.tickers_of_interest()
    hdir = os.path.join(ROOT, "state", "earnings", "history")
    seeded = [f[:-5] for f in os.listdir(hdir) if f.endswith(".json")] if os.path.isdir(hdir) else []
    universe = sorted(set(tick) | set(seeded))
    spy, vix = closes("SPY"), (vix_history() if net else [])
    events = event_table(universe, closes, spy, vix)
    overs = overreactions(universe, closes)
    patterns = describe(events, overs)
    wf = walk_forward(events)
    test, keep = judge(wf)
    for p in patterns:
        if p["id"] == "sell_the_news":
            p.update(status="kept" if "run_up" in keep else "dropped", why=test.get("per_condition", {}).get("run_up", {}).get("why"))
        elif p["id"] == "fear_discount":
            p.update(status="kept" if "stressed" in keep else "dropped", why=test.get("per_condition", {}).get("stressed", {}).get("why"))
        elif p["id"] == "underreaction":
            hit = p.get("how_often")
            ok = hit is not None and p["cases"] >= FEW and hit > 0.55
            p.update(status="kept (used in the after-call drift)" if ok else "dropped", why="the drift went the first day's way %s of the time in %d cases%s" % (pc(hit), p["cases"], "" if ok else ", not clearly better than a coin"))
        elif p["id"] == "overreaction":
            drops = [o for o in overs if o["kind"] == "drop"]
            yrs = sorted(set(o["date"][:4] for o in drops))
            good = sum(1 for y in yrs if sum(o["next5"] - COST for o in drops if o["date"][:4] == y) > 0)
            ok = p.get("typical_move") is not None and p["typical_move"] > 0 and p["cases"] >= FEW and good * 10 >= 6 * max(1, len(yrs))
            p.update(status="kept" if ok else "dropped", years_better="%d of %d" % (good, len(yrs)),
                     why=("bounced after costs on average and in %d of %d years" % (good, len(yrs))) if ok else ("after costs it did not bounce reliably: positive in %d of %d years" % (good, len(yrs))))
    eff = effects(events)
    # today's readings for holdings, and the adjusted event forecasts
    mood_vix = vix[-1][1] if vix else None
    stress = ((rj("state/quant.json", {}) or {}).get("stress") or {})
    st_now, _, dd_now = stressed_at(str(today), spy, vix)
    mood = {"vix": mood_vix, "vix_pct_1y": r4(pct_rank(mood_vix, [v for _, v in vix[-252:]]), 3) if vix else None, "stress_level": stress.get("level"),
            "stressed": st_now, "spy_from_high": r4(dd_now), "fear_greed": "not available (the free source blocks automated reads)"}
    smart = (rj("state/smart_money.json", {}) or {}).get("alerts") or []
    att = attention_counts(today)
    out_read, cards = {}, {}
    for t in sorted(set(held) | set((earn.get("predictions") or {}).keys())):
        hp = "state/behaviour/history/%s.json" % t
        hist = rj(hp, {"options": [], "consensus": []}) or {"options": [], "consensus": []}
        opt = options_now(t) if net else None
        if opt and not any(x.get("date") == str(today) for x in hist["options"]):
            hist["options"].append(dict(opt, date=str(today)))
        ev = (earn.get("predictions") or {}).get(t, {}).get("call")
        if ev and ev.get("eps_consensus") is not None and not any(x.get("date") == str(today) for x in hist["consensus"]):
            hist["consensus"].append({"date": str(today), "eps": ev["eps_consensus"], "call": ev.get("date")})
        hist["options"], hist["consensus"] = hist["options"][-400:], hist["consensus"][-400:]
        wj(hp, hist)
        rd = readings(t, closes, events, hist, opt, short_now(t) if net else None, mood, smart, att, ev)
        out_read[t] = rd
        q = (earn.get("predictions") or {}).get(t)
        if not q:
            continue
        cl = closes(t)
        cs = [c for _, c in cl]
        f = {"runup_z": None, "stressed": st_now}
        if len(cs) > 31:
            v = sd(rets(cs[-21:]))
            f["runup_z"] = ((cs[-1] / cs[-11] - 1) / (v * math.sqrt(10))) if v else None
        bu, ba = q["overall"]["p_up_next_day"], q["overall"]["expected_abs_move"]
        up, ab, d, fm, why = adjust(bu, ba, f, eff, keep)
        nd = q["overall"]["next_day"]
        med = nd.get("median") or 0
        adjq = dict((k, r4(med + (v - med) * fm)) for k, v in nd.items() if v is not None)
        words = {"run_up": "the share already ran up into the call", "stressed": "the market is stressed"}
        fired = [k for k in COND if COND[k](f)]
        line = ("Base forecast %s up; behaviour adjustment %+.0f points (%s); final %s." % (pc(bu), 100 * d, ", ".join(words[k] for k in why), pc(up)) if why else
                "Base forecast %s up; no behaviour adjustment (%s); final %s." % (pc(bu), ("%s, but that pattern did not improve forecasts out of sample" % " and ".join(words[k] for k in fired)) if fired else "no tested pattern fires", pc(up)))
        top = [x for x in rd if x["available"]][:3]
        card = {"ticker": t, "call": q["call"], "base_p_up": bu, "adjustment": r4(d, 4), "final_p_up": r4(up, 3), "base_abs": ba, "final_abs": r4(ab),
                "final_next_day": adjq, "line": line, "why": why, "fired_untested": [k for k in fired if k not in keep], "top_readings": [x["sentence"] for x in top]}
        pos = q.get("position")
        if pos:
            mv = pos.get("value") or 0
            card["position"] = {"hold": {"middle": r4(mv * (adjq.get("median") or 0), 2), "worst_10": r4(mv * (adjq.get("p10") or 0), 2), "best_10": r4(mv * (adjq.get("p90") or 0), 2)},
                                "kept": pos.get("kept"), "stop": pos.get("stop"),
                                "note": "With the behaviour adjustment; your decision to keep %s stands." % t if pos.get("kept") else "With the behaviour adjustment."}
        st = ER.stage_for(q["call"], today)
        if st:
            pid = "%s|%s|%s" % (t, q["call"]["date"], st)
            if pid not in set(e["id"] for e in read_log()):
                os.makedirs(os.path.dirname(log_path()), exist_ok=True)
                with open(log_path(), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"id": pid, "made_at": now, "t": t, "call_date": q["call"]["date"], "stage": st, "base_p_up": bu, "final_p_up": card["final_p_up"],
                                         "adjustment": card["adjustment"], "base_abs": ba, "final_abs": card["final_abs"], "why": why}, sort_keys=True) + "\n")
            card["logged"] = pid
        cards[t] = card
    # live score: adjusted against base, after each event
    outcomes = dict(("%s|%s" % (e["t"], e["date"]), e) for e in events)
    live = []
    for e in read_log():
        o = outcomes.get("%s|%s" % (e["t"], e["call_date"]))
        if o and e["stage"] == "final" and e.get("base_p_up") is not None:
            live.append({"t": e["t"], "call_date": e["call_date"], "up": o["r1"] > 0, "brier_base": r4(brier(e["base_p_up"], o["r1"] > 0)), "brier_final": r4(brier(e["final_p_up"], o["r1"] > 0)),
                         "err_base": r4(abs(e["base_abs"] - abs(o["r1"]))), "err_final": r4(abs(e["final_abs"] - abs(o["r1"])))})
    n = len(live)
    live_sum = {"events": n, "verdict": ("Too early to judge: %d of the %d events needed have been scored." % (n, JUDGE)) if n < JUDGE else
                ("The adjustment %s the direction score (%.4f against %.4f without it)." % ("improves" if sum(x["brier_final"] for x in live) < sum(x["brier_base"] for x in live) else "does not improve",
                                                                                          sum(x["brier_final"] for x in live) / n, sum(x["brier_base"] for x in live) / n))}
    # standalone setups: an extreme fall today in a held or watched share, raised only if the overreaction pattern was kept
    over_kept = next((p for p in patterns if p["id"] == "overreaction"), {}).get("status") == "kept"
    setups = [o for o in overreactions(tick, closes) if o["date"] == max((d for d, _ in closes(o["t"])), default="") and o["kind"] == "drop"] if tick else []
    out = {"as_of": now, "mood": mood, "readings": out_read, "patterns": patterns, "backtest": dict(test, kept=sorted(keep),
           method="Walk-forward: each of %d past earnings events after the first 40 was forecast twice from the events before it only: the plain earnings forecast and the same forecast "
                  "with the behaviour adjustment. A condition is kept only if it improved the direction score or the size-of-move error out of sample, fired on at least %d events "
                  "and was better in at least half of the years it fired." % (len(wf), FEW)),
           "events_used": len(events), "cards": cards, "live": live_sum, "live_scored": live[-30:],
           "setups": {"pattern_kept": over_kept, "today": setups, "note": None if over_kept else "The overreaction pattern did not earn its place after costs, so no card is raised from it."},
           "honesty": HONEST}
    wj("state/behaviour.json", out)
    return out


if __name__ == "__main__":
    o = run()
    print("behaviour: %d events, kept %s, %d event cards" % (o["events_used"], o["backtest"].get("kept"), len(o["cards"])))
