"""Market Council live track record. Plain code, no AI.

Every idea card with a share behind it is written down once, on the day it is raised, at that day's closing price:
offered or greyed out, good or bad, none left out and none picked by hand. The log is never edited (each entry carries a
fingerprint of the one before it). After each US trading day the ideas are measured at one, three, six and twelve
months and to date, after broker fees, against the index fund over the same days and against the average share of the
same list over the same days (what a random pick from that list would have earned on average).

The rule for dropping a check was written before any result was in, and the code applies it without asking."""
import hashlib
import json
import os

import numpy as np

import engine as E

COST = 0.005                    # buying and selling at 0.25% each way, the same on the idea, the index fund and the list
MARKS = (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252))
MIN_CASES, DROP_CASES = 20, 30
LOG, DROPPED = "state/track/ideas.json", "state/track/dropped.json"
NL = chr(10)
RULE = ("Written on 12 October 2026, before any result was in. A check is dropped when at least 30 logged ideas that passed it have reached the "
        "three-month mark and at least 30 have reached the six-month mark, and at both marks those ideas did worse on average, after fees, than "
        "the index fund AND than the average share of the same list over the same days. A dropped check no longer counts towards a share's score, "
        "and the pass mark shrinks in proportion (5 of 7, rounded up). The code applies this without asking and shows the date and the figures here. "
        "Only you can reinstate a check. A check counts as proven the other way round: at least 30 ideas at both marks, ahead of both. A data source "
        "that delivers nothing makes its check read 'no data', which already counts as not passed.")


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


def read(rel, default):
    try:
        with open(os.path.join(E.ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write(rel, obj):
    path = os.path.join(E.ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(obj, f, separators=(",", ":"))
        f.write(NL)


def log_cards(cards, read_cache, today, entries=None):
    # called by the decision desk on every run. Returns (entries, number added, log intact).
    save = entries is None
    if entries is None:
        entries = (read(LOG, {"entries": []}) or {}).get("entries") or []
    if not chain_ok(entries):
        return entries, 0, False
    have, added = set(e["id"] for e in entries), 0
    for c in sorted(cards, key=lambda c: (str(c.get("created") or ""), str(c.get("id")))):
        t = c.get("ticker")
        if c.get("kind") != "idea" or not t or t == "portfolio" or c.get("id") in have:
            continue
        day = str(c.get("created") or today)[:10]
        past = [(d, v) for d, v in read_cache(t) if d <= day]
        if not past:
            continue
        checks = c.get("checks") or []
        e = {"id": c["id"], "t": t, "day": past[-1][0], "price": round(float(past[-1][1]), 4), "raised": day, "key": c.get("key"),
             "source": (str(c.get("key") or "idea").split(":")[0] or "idea"), "checks": dict((k.get("id"), k.get("pass")) for k in checks),
             "score": len([k for k in checks if k.get("pass")]), "offered": not c.get("greyed"), "late": day < str(today)[:10]}
        e["prev"] = entries[-1]["hash"] if entries else None
        e["hash"] = entry_hash(e["prev"], e)
        entries.append(e)
        have.add(c["id"])
        added += 1
    if save and added:
        write(LOG, {"entries": entries, "note": "Written once, never edited. 'late' marks ideas raised before this log existed, added from the card list at the close of the day each was raised."})
    return entries, added, True


def measure(entries, shares, ctx):
    # each idea against the index fund and the average share of the list over the same days, all after the same fees
    cal, idx, spy, n = ctx["cal"], ctx["idx"], ctx["spy"], ctx["n"]
    by = {s["t"]: s for s in shares}
    listed = [s for s in shares if s.get("listed")] or shares
    rows = []
    for e in entries:
        g, s = idx.get(e["day"]), by.get(e["t"])
        r = {"id": e["id"], "t": e["t"], "day": e["day"], "price": e["price"], "source": e.get("source"), "offered": bool(e.get("offered")), "late": bool(e.get("late")),
             "score": e.get("score"), "checks": e.get("checks") or {}, "m": {}}
        if g is None or s is None or not (s["a"] <= g < s["b"]):
            r["note"] = "its day is not in the price history yet" if g is None else "no long price history for this share, so it cannot be measured"
            rows.append(r)
            continue
        x, a, end = s["x"], s["a"], min(n, s["b"]) - 1
        for h, d in MARKS + (("now", end - g),):
            if d < 1 or g + d > end:
                continue
            lst = np.array([float(q["x"][g + d - q["a"]] / q["x"][g - q["a"]]) for q in listed if q["a"] <= g and g + d < q["b"]]) - 1 - COST
            idea = float(x[g + d - a] / x[g - a]) - 1 - COST
            r["m"][h] = {"idea": E.rd(idea, 4), "spy": E.rd(float(spy[g + d] / spy[g]) - 1 - COST, 4), "list": E.rd(float(lst.mean()), 4) if len(lst) else None,
                         "beat": E.rd(float(np.mean(lst < idea)), 3) if len(lst) else None, "days": int(d)}
        rows.append(r)
    return rows


def table(rows, pick=lambda r: True):
    out = {}
    for h in [m for m, _ in MARKS] + ["now"]:
        v = [r["m"][h] for r in rows if pick(r) and h in r["m"] and r["m"][h].get("list") is not None]
        if not v:
            out[h] = {"n": 0, "few": True}
            continue
        idea, spy, lst = np.array([q["idea"] for q in v]), np.array([q["spy"] for q in v]), np.array([q["list"] for q in v])
        out[h] = {"n": len(v), "few": len(v) < MIN_CASES, "idea": E.rd(float(idea.mean()), 4), "median": E.rd(float(np.median(idea)), 4), "spy": E.rd(float(spy.mean()), 4),
                  "list": E.rd(float(lst.mean()), 4), "beat_spy": E.rd(float(np.mean(idea > spy)), 3), "beat_list": E.rd(float(np.mean(idea > lst)), 3),
                  "vs_spy": E.rd(float((idea - spy).mean()), 4), "vs_list": E.rd(float((idea - lst).mean()), 4), "worst": E.rd(float(idea.min()), 4)}
    return out


def judge_checks(rows, dropped, day):
    ids = sorted(set(k for r in rows for k in r["checks"]))
    out, proven, new = {}, [], {}
    for c in ids:
        t = table(rows, lambda r, c=c: r["checks"].get(c) is True)
        a, b = t.get("3m") or {}, t.get("6m") or {}
        ripe = (a.get("n") or 0) >= DROP_CASES and (b.get("n") or 0) >= DROP_CASES
        bad = ripe and a["vs_spy"] < 0 and a["vs_list"] < 0 and b["vs_spy"] < 0 and b["vs_list"] < 0
        good = ripe and a["vs_spy"] > 0 and a["vs_list"] > 0 and b["vs_spy"] > 0 and b["vs_list"] > 0
        out[c] = {"passed": t, "ripe": bool(ripe), "state": "dropped" if (c in dropped or bad) else "proven" if good else "unproven"}
        if bad and c not in dropped:
            new[c] = {"on": day, "three_months": {k: a[k] for k in ("n", "vs_spy", "vs_list")}, "six_months": {k: b[k] for k in ("n", "vs_spy", "vs_list")}}
        if good and c not in dropped:
            proven.append(c)
    return out, proven, new


def run(shares, ctx, limits):
    entries = (read(LOG, {"entries": []}) or {}).get("entries") or []
    intact = chain_ok(entries)
    if not intact:
        limits.append("Track record: the idea log failed its fingerprint check. Nothing is added to it until it has been looked at by hand.")
    rows = measure(entries, shares, ctx)
    dropped = read(DROPPED, {}) or {}
    checks, proven, new = judge_checks(rows, dropped, ctx["cal"][-1])
    if new:
        dropped.update(new)
        write(DROPPED, dropped)
        limits.append("Track record: dropped by the written rule: %s." % ", ".join(sorted(new)))
    allr = table(rows)
    three = allr.get("3m") or {}
    if not entries:
        verdict = "No idea has been logged yet."
    elif not three.get("n"):
        verdict = "Too early to judge: %d idea%s logged, none has reached the three-month mark yet." % (len(entries), "" if len(entries) == 1 else "s")
    elif three.get("few"):
        verdict = "Too few cases to rely on: %d idea%s at the three-month mark; 20 are needed before the figures mean anything." % (three["n"], "" if three["n"] == 1 else "s")
    else:
        verdict = "At three months the ideas made %s on average after fees; the index fund made %s and the average share of the list %s (%d ideas). %s" % (
            E.pc(three["idea"], 1), E.pc(three["spy"], 1), E.pc(three["list"], 1), three["n"],
            "They are ahead of both." if (three["vs_spy"] > 0 and three["vs_list"] > 0) else "They are behind both." if (three["vs_spy"] < 0 and three["vs_list"] < 0) else "They are ahead of one and behind the other.")
    E.wj("state/track.json", {
        "as_of": E.now_iso(), "to": ctx["cal"][-1], "count": len(entries), "first": entries[0]["day"] if entries else None, "intact": intact, "verdict": verdict,
        "all": allr, "offered": table(rows, lambda r: r["offered"]), "greyed": table(rows, lambda r: not r["offered"]),
        "checks": checks, "proven": proven, "dropped": dropped, "rule": RULE, "cost": COST,
        "ideas": [{k: r.get(k) for k in ("id", "t", "day", "price", "source", "offered", "late", "score", "note")} | {"now": r["m"].get("now"), "m3": r["m"].get("3m")} for r in rows[-150:]],
        "method": "Each idea is measured from the closing price of the day it was raised. Half a percent is taken off for buying and selling, and the same is taken off the index fund and off every share of the list. 'Average share of the list' is what a random pick from the screened list would have earned on average over the same days; 'beat' is the part of the list the idea did better than. The list is today's list, so shares that have since dropped out of it are missing.",
        "honesty": "Fewer than 20 cases: too few to rely on. Ideas marked 'late' were raised before this log existed and were added from the card list afterwards, at the close of the day each was raised."})
    return {"ideas": len(entries), "measured": len([r for r in rows if r["m"]]), "dropped": sorted(dropped)}
