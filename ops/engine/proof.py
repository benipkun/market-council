"""Prove it first (Ben, 10 Nov 2026: "first make the system prove itself").

For every signal that raises stock cards this gives three things from our own files, never a forecast:
  - its back-test: how many past cases there are and how often they rose (state/backcheck.json, 300 shares, since 2000);
  - its paper record: every idea it raised since 7 Oct 2026, measured after fees against the S&P 500 fund (state/track.json);
  - whether it may raise a card for real money: only after PAPER_MIN paper ideas have reached the three-month mark and,
    on average, beat the S&P 500 fund after fees. Until then every idea it raises is PAPER ONLY.
It also splits the portfolio into the core (the S&P 500 fund), the declared conviction bet (UBER) and the capped side
portion for stock ideas. Standard library only.
"""
import re

PAPER_MIN = 20          # paper ideas at the three-month mark before a signal may raise real-money cards
MARK = "3m"
SIDE_CAP = 0.25         # stock ideas may take at most this share of the portfolio (outside the core and the conviction bet)
INDEX = ("SPY", "VOO", "IVV", "SPLG", "CSPX", "VUSA", "SXR8", "SPY5", "IUSA", "VUAA")
NAMES = {"SCORE": "Seven-check scorecard (5 or more of 7)", "VALUE": "Price under our fair value",
         "rule:pullback": "Pullback in an uptrend", "rule:dip": "Buy the dip", "rule:breakout": "Breakout", "rule:three_down": "Three down days"}


def signal_of(card):
    k = str(card.get("key") or "")
    if k.startswith("SCORE:"):
        return "SCORE"
    if k.startswith("BUY:") or card.get("kind") == "buy":
        return "VALUE"
    if k.startswith("RULE:"):
        return "rule:" + k.split(":")[1]
    return None


def _pct(x):
    return "%+.1f%%" % (100 * x)


def backtest(sig, back):
    """Past cases and how often they rose, six months on (the back-check's main horizon)."""
    back = back or {}
    if sig == "SCORE":
        rows = [r for r in (back.get("combined") or {}).get("by_k") or [] if r.get("k") == 4]
        r = (rows[0]["rows"].get("6m") or {}) if rows else {}
        at = r.get("at") or {}
        if at.get("n"):
            return {"cases": at["n"], "hit": at.get("win"), "avg": at.get("avg"), "spy": r.get("spy"), "horizon": "6 months",
                    "verdict": "unproven" if not (back.get("combined") or {}).get("works") else "working",
                    "what": "shares passing all four checks we can rebuild in history (the full seven have no history)"}
        return {"cases": 0, "verdict": "no history"}
    cid = "value" if sig == "VALUE" else None
    for c in back.get("checks") or []:
        if cid and c.get("id") == cid:
            r = ((c.get("rows") or {}).get("6m") or {})
            p = r.get("pass") or {}
            return {"cases": p.get("n") or 0, "hit": p.get("win"), "avg": p.get("avg"), "spy": r.get("spy_pass"), "horizon": "6 months",
                    "verdict": c.get("verdict") or "unproven", "what": c.get("name")}
    for o in back.get("other") or []:
        if o.get("id") == sig:
            rec = str(o.get("record") or "")
            n = re.search(r"([\d,]+) trades", rec)
            w = re.search(r"(\d+)% winners", rec)
            return {"cases": int(n.group(1).replace(",", "")) if n else 0, "hit": int(w.group(1)) / 100.0 if w else None, "avg": None, "spy": None,
                    "horizon": "per trade", "verdict": o.get("verdict") or "unproven", "what": rec}
    return {"cases": 0, "verdict": "not back-tested"}


def paper(sig, track):
    """The paper record since 7 Oct 2026: ideas logged, how many reached three months, result against the fund after fees."""
    track = track or {}
    if sig == "SCORE":
        ideas = [i for i in track.get("ideas") or [] if i.get("source") == "SCORE"]
        now = [i["now"] for i in ideas if i.get("now")]
        m3 = [i["m3"] for i in ideas if i.get("m3")]
        avg = lambda xs: (sum(float(x.get("idea") or 0) - float(x.get("spy") or 0) for x in xs) / len(xs)) if xs else None
        return {"logged": len(ideas), "at_mark": len(m3), "vs_spy_mark": avg(m3), "measured_now": len(now), "vs_spy_now": avg(now)}
    cid = "value" if sig == "VALUE" else sig
    c = ((track.get("checks") or {}).get(cid) or {}).get("passed") or {}
    m, n = c.get(MARK) or {}, c.get("now") or {}
    return {"logged": n.get("n") or 0, "at_mark": m.get("n") or 0, "vs_spy_mark": m.get("vs_spy"), "measured_now": n.get("n") or 0, "vs_spy_now": n.get("vs_spy")}


def proven(p):
    return (p.get("at_mark") or 0) >= PAPER_MIN and (p.get("vs_spy_mark") or 0) > 0


def evidence(sig, back, track):
    if not sig:
        return None
    b, p = backtest(sig, back), paper(sig, track)
    ok = proven(p)
    if b.get("hit") is None:
        bt = "Past cases: %s" % "{:,}".format(b.get("cases") or 0)
    elif b.get("horizon") == "per trade":
        bt = "Past cases: %s trades; %d%% of them won" % ("{:,}".format(b["cases"]), round(100 * b["hit"]))
    else:
        bt = "Past cases: %s; %d%% rose over %s" % ("{:,}".format(b["cases"]), round(100 * b["hit"]), b["horizon"])
    if b.get("avg") is not None and b.get("spy") is not None:
        bt += ", on average %s against %s for the S&P 500 fund" % (_pct(b["avg"]), _pct(b["spy"]))
    bt += "; back-test verdict: %s." % b.get("verdict")
    pp = "Paper record: %d ideas since 7 Oct 2026, %d of %d needed at the three-month mark" % (p["logged"], min(p["at_mark"], PAPER_MIN), PAPER_MIN)
    if p.get("vs_spy_mark") is not None and p["at_mark"]:
        pp += ", %s against the S&P 500 fund after fees" % _pct(p["vs_spy_mark"])
    elif p.get("vs_spy_now") is not None and p["measured_now"]:
        pp += "; so far %s against the S&P 500 fund after fees (early read, %d ideas)" % (_pct(p["vs_spy_now"]), p["measured_now"])
    pp += "."
    status = "PROVEN: may raise real-money cards." if ok else "PAPER ONLY until %d paper ideas reach three months and beat the S&P 500 fund after fees." % PAPER_MIN
    return {"signal": sig, "name": NAMES.get(sig, sig), "backtest": b, "paper": p, "proven": ok, "status": status,
            "text": "%s. %s %s %s" % (NAMES.get(sig, sig), bt, pp, status), "progress": "%d of %d" % (min(p["at_mark"], PAPER_MIN), PAPER_MIN)}


def table(back, track):
    return [evidence(s, back, track) for s in NAMES]


def split(snap, keeps=None, cap=None):
    """Core first: the S&P 500 fund is the core, UBER (and any other declared keep) the conviction bet, the rest the side portion."""
    cap = float(cap or SIDE_CAP)
    pos = (snap or {}).get("positions") or []
    nav = float((snap or {}).get("nav") or 0) or sum(float(p.get("market_value") or 0) for p in pos) + float((snap or {}).get("cash") or 0)
    keeps = keeps or {}
    core = sum(float(p.get("market_value") or 0) for p in pos if p.get("ticker") in INDEX)
    bets = [{"ticker": p["ticker"], "value": round(float(p.get("market_value") or 0), 2), "share": round(float(p.get("market_value") or 0) / nav, 4) if nav else None,
             "target": (keeps.get(p["ticker"]) or {}).get("target"), "review": (keeps.get(p["ticker"]) or {}).get("by") or (keeps.get(p["ticker"]) or {}).get("review")}
            for p in pos if p.get("ticker") in keeps]
    side = sum(float(p.get("market_value") or 0) for p in pos if p.get("ticker") not in INDEX and p.get("ticker") not in keeps)
    used = side / nav if nav else 0
    return {"nav": round(nav, 2), "core_usd": round(core, 2), "core_share": round(core / nav, 4) if nav else None, "conviction": bets,
            "side_usd": round(side, 2), "side_share": round(used, 4), "side_cap": cap, "side_room_usd": round(max(0.0, cap * nav - side), 2),
            "over": used > cap, "cash_usd": round(float((snap or {}).get("cash") or 0), 2),
            "text": "Stock ideas use %.0f%% of the portfolio against a cap of %.0f%%%s." % (100 * used, 100 * cap,
                     (": over the cap by $%.0f, so new money goes to the core (the S&P 500 fund)" % (side - cap * nav)) if used > cap else " ($%.0f of room left)" % max(0.0, cap * nav - side))}
