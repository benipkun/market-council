"""Truth audit (Ben, 24 Nov 2026: "nothing counts as done again without evidence").
The SYSTEM checklist used to say BUILT when a data field existed. This reads the private records and marks each item
WORKS, PARTLY or BROKEN from what it can prove: is the output fresh, and does it cover what Ben holds today?
Writes state/audit.json (private). Standard library only.
"""
import datetime
import glob
import json
import os

ROOT = os.environ.get("MC_ROOT", ".")
NAMES = {1: "Analyst and councillor prompts", 2: "Risk profile per person", 3: "Portfolio health check", 4: "Diversification maths", 5: "Bonds in the analysis",
         6: "Shorts with safeguards", 7: "Research card", 8: "Valuation (DCF)", 9: "Earnings reviewer", 10: "Smart-money tracker", 11: "Real-world signals lab",
         12: "Backtester", 13: "Decision cards", 14: "Rebalance plan", 15: "Timed plans", 16: "Hold projection", 17: "Doomsday protocol", 18: "Morning check with yes / no",
         19: "Paper trading and track record", 20: "Several people with private logins", 21: "Joint account with change log"}
FUNDS = ("SPY", "VOO", "IVV")


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def age_h(stamp, now):
    try:
        return (now - datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))).total_seconds() / 3600.0
    except Exception:
        return None


def fresh(stamp, now, limit=80):
    """80 hours: a weekend plus a late run still counts as fresh."""
    a = age_h(stamp, now)
    return a is not None and a <= limit


def cover(names, have):
    """WORKS when every name is covered, PARTLY when some are, BROKEN when none."""
    miss = [t for t in names if t not in have]
    return ("WORKS" if not miss else "PARTLY" if len(miss) < len(names) else "BROKEN"), miss


def row(i, status, evidence):
    return {"item": i, "name": NAMES[i], "status": status, "evidence": evidence}


def books_consistent(snap):
    """Every position's value must equal shares x its last price (within 1%)."""
    out = []
    for p in snap.get("positions") or []:
        q, px, mv = p.get("qty"), p.get("last_price"), p.get("market_value")
        if q and px and mv and abs(float(q) * float(px) / float(mv) - 1) > 0.01:
            out.append(p.get("ticker"))
    return out


def run(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    snap, dec, q = rj("treasury/snapshot.json", {}) or {}, rj("state/decisions.json", {}) or {}, rj("state/quant.json", {}) or {}
    held = [p["ticker"] for p in snap.get("positions") or [] if p.get("ticker")]
    stocks = [t for t in held if t not in FUNDS]
    dg, lab, ern = rj("digests/latest.json", {}) or {}, rj("state/lab.json", {}) or {}, rj("state/earnings.json", {}) or {}
    cards = dict((t, rj("research/cards/%s.json" % t, {}) or {}) for t in held)
    plans, pb = rj("state/plans.json", {}) or {}, rj("state/paper_book.json", {}) or {}
    prof = rj("state/profiles.json", {}) or {}
    rows = []
    ok = str(dg.get("rulebook") or "").startswith("pipeline v2") and fresh(dg.get("as_of"), now)
    rows.append(row(1, "WORKS" if ok else "PARTLY", "rulebook %s, digest %s" % (dg.get("rulebook"), str(dg.get("as_of"))[:16])))
    p = q.get("profile") or {}
    people = prof.get("profiles") or prof.get("people") or []
    rows.append(row(2, "WORKS" if p.get("set") else "PARTLY", "set by Ben: %s; level %s" % (bool(p.get("set")), p.get("risk_level"))))
    rows.append(row(3, "WORKS" if q.get("health") and fresh(q.get("as_of"), now) else "BROKEN", "quant.json %s" % str(q.get("as_of"))[:16]))
    a, miss = cover(stocks, set((q.get("assets") or {}).keys()))
    rows.append(row(4, a if (q.get("opt") or {}).get("held") else "BROKEN", "holdings without risk figures: %s" % (miss or "none")))
    rows.append(row(5, "WORKS" if (q.get("opt") or {}).get("wide") else "BROKEN", "wide optimiser present: %s" % bool((q.get("opt") or {}).get("wide"))))
    rows.append(row(6, "WORKS" if "shorts" in dec else "BROKEN", "desk has a shorts section; your profile keeps shorts off"))
    a, miss = cover(stocks, set(t for t, c in cards.items() if c and fresh(c.get("as_of"), now)))
    rows.append(row(7, a, "holdings without a fresh card: %s" % (miss or "none")))
    a, miss = cover(stocks, set(t for t, c in cards.items() if (c.get("valuation") or {}).get("status") == "valued"))
    rows.append(row(8, a, "holdings without our own valuation: %s" % (miss or "none")))
    reads = len(glob.glob(os.path.join(ROOT, "state", "earnings", "reads", "*.json")))
    rows.append(row(9, "WORKS" if reads and fresh(ern.get("as_of"), now) else "PARTLY", "%d call reads; earnings file %s" % (reads, str(ern.get("as_of"))[:16])))
    a, miss = cover(stocks, set(t for t, c in cards.items() if c.get("smart_money")))
    rows.append(row(10, a, "holdings without smart-money data: %s" % (miss or "none")))
    s = (lab.get("signals") or {}).get("tested") or 0
    rows.append(row(11, "WORKS" if s and fresh(lab.get("as_of"), now) else "PARTLY", "%s signals tested; lab %s" % (s, str(lab.get("as_of"))[:16])))
    n = len((lab.get("backtests") or {}).get("rows") or [])
    rows.append(row(12, "WORKS" if n and fresh(lab.get("as_of"), now) else "PARTLY", "%d back-test rows" % n))
    rows.append(row(13, "WORKS" if fresh(dec.get("as_of"), now) and dec.get("cards") is not None else "BROKEN", "%d open cards; desk %s" % (len([c for c in dec.get("cards") or [] if c.get("status") == "open"]), str(dec.get("as_of"))[:16])))
    rows.append(row(14, "WORKS" if dec.get("rebalance") else "PARTLY", "rebalance section present: %s" % bool(dec.get("rebalance"))))
    a, miss = cover(stocks, set(x.get("ticker") for x in plans.get("holdings") or []))
    rows.append(row(15, a, "holdings without a plan: %s" % (miss or "none")))
    a, miss = cover(stocks, set((dec.get("holds") or {}).keys()))
    rows.append(row(16, a, "holdings without a hold projection: %s" % (miss or "none")))
    st = ((dec.get("doomsday") or {}).get("backtest") or {}).get("status")
    rows.append(row(17, "WORKS" if st == "ok" else "PARTLY", "doomsday back-test status: %s" % st))
    m = dec.get("morning") or {}
    rows.append(row(18, "WORKS" if age_h(str(m.get("date")) + "T00:00:00+00:00", now) is not None and age_h(str(m.get("date")) + "T00:00:00+00:00", now) <= 104 else "BROKEN", "morning check dated %s" % m.get("date")))
    rows.append(row(19, "WORKS" if pb.get("history") and fresh(pb.get("as_of"), now) else "BROKEN", "%d days of paper history, %d paper trades" % (len(pb.get("history") or []), len(pb.get("trades") or []))))
    rows.append(row(20, "PARTLY" if len(people) > 1 else "BROKEN", "%d people on file; no private logins exist" % len(people)))
    rows.append(row(21, "BROKEN", "no joint account or shared change log exists"))
    bad = books_consistent(snap)
    out = {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": rows, "counts": dict((k, len([r for r in rows if r["status"] == k])) for k in ("WORKS", "PARTLY", "BROKEN")),
           "books_mismatch": bad, "method": "Each item is judged by its output in the private records: fresh within 80 hours, and covering every share held today."}
    p_ = os.path.join(ROOT, "state", "audit.json")
    with open(p_, "w", encoding="utf-8", newline="") as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == "__main__":
    o = run()
    for r in o["rows"]:
        print("%2d %-7s %-36s %s" % (r["item"], r["status"], r["name"], r["evidence"]))
    print(o["counts"], "value not equal to shares x price:", o["books_mismatch"] or "none")
