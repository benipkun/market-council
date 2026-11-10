"""Investment committee, plain-code half (Ben, 10 Nov 2026: "point the system at company analysis the way a private
equity firm works").

1. packs(): for each company the Council looks at (holdings, watchlist, open paper ideas) a pack of our own numbers:
   price, risk figures, our DCF as a range with its main assumption named (the discount rate, +-1 point), the paper record
   of ideas on it, next results. Writes state/memos/packs/<T>.json and state/memos/queue.json (which memos are due:
   none yet, older than 90 days, or results since the last memo). The Investment Committee routine (ops/COMMITTEE.md)
   writes the memo, the vote and the reviews from the pack.
2. score(): every memo is scored later against what happened: after 1, 3, 6 and 12 months, the share against the S&P 500
   fund, whether the committee's decision was right, and whether the price moved toward our DCF base value.
3. index(): state/memos/index.json for the MEMOS page. Standard library only.
"""
import datetime
import glob
import json
import os

ROOT = os.environ.get("MC_ROOT", ".")
STALE_DAYS = 90
MARKS = (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252))


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def wj(rel, obj):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
        f.write("\n")


def dcf_value(a, wacc=None, g0=None):
    """Our research DCF (ops/engine/research.py) recomputed from its stored assumptions, so the range uses the same model."""
    w = a["wacc"] if wacc is None else wacc
    g_start = a["growth_start"] if g0 is None else g0
    rev, pv, fcf = float(a["base_revenue"]), 0.0, 0.0
    for y in range(1, 6):
        g = g_start + (a["growth_end"] - g_start) * (y - 1) / 4.0
        new = rev * (1 + g)
        ebit = new * a["ebit_margin"]
        fcf = ebit * (1 - a["tax_rate"]) + new * a["da_pct_revenue"] - new * a["capex_pct_revenue"] - (new - rev) * a["working_capital_pct_of_growth"]
        pv += fcf / (1 + w) ** y
        rev = new
    if w <= a["terminal_growth"]:
        return None
    tv = fcf * (1 + a["terminal_growth"]) / (w - a["terminal_growth"])
    ev = pv + tv / (1 + w) ** 5
    return (ev - float(a["net_debt"])) / float(a["shares"])


def dcf_range(val):
    if not val or val.get("status") != "valued" or not val.get("assumptions"):
        return {"status": "not valued", "reason": (val or {}).get("reason") or "no research card with our own valuation yet"}
    a = val["assumptions"]
    try:
        base = float(val.get("fair_value_per_share") or dcf_value(a))
        low, high = dcf_value(a, wacc=a["wacc"] + 0.01), dcf_value(a, wacc=max(a["terminal_growth"] + 0.01, a["wacc"] - 0.01))
    except Exception as e:
        return {"status": "not valued", "reason": "the stored assumptions could not be recomputed (%s)" % type(e).__name__}
    return {"status": "valued", "low": round(low, 2) if low else None, "base": round(base, 2), "high": round(high, 2) if high else None,
            "main_assumption": "discount rate %.1f%% (range: %.1f%% to %.1f%%)" % (100 * a["wacc"], 100 * (a["wacc"] + 0.01), 100 * (a["wacc"] - 0.01)),
            "other": "growth starts at %.0f%% and fades to %.0f%%; operating margin %.0f%%; terminal growth %.1f%%" % (100 * a["growth_start"], 100 * a["growth_end"], 100 * a["ebit_margin"], 100 * a["terminal_growth"]),
            "as_of": val.get("as_of"), "price_then": val.get("price"), "label": "estimate: our own five-year cash-flow model (ops/engine/research.py)"}


def companies():
    snap = rj("treasury/snapshot.json", {}) or {}
    held = [p["ticker"] for p in snap.get("positions") or [] if p.get("ticker")]
    watch = [str(x.get("ticker") if isinstance(x, dict) else x) for x in (rj("state/known_companies.json", {}) or {}).get("tickers") or []]
    ideas = [c.get("ticker") for c in (rj("state/decisions.json", {}) or {}).get("cards") or [] if c.get("status") == "open" and c.get("kind") == "idea" and c.get("ticker")]
    out = []
    for t in held + watch + ideas:
        if t and t not in out and t not in ("SPY", "VOO", "IVV", "portfolio"):
            out.append(t)
    return out, set(held)


def packs(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    names, held = companies()
    quant = (rj("state/quant.json", {}) or {}).get("assets") or {}
    snap = dict((p["ticker"], p) for p in (rj("treasury/snapshot.json", {}) or {}).get("positions") or [] if p.get("ticker"))
    tech = (rj("digests/latest.json", {}) or {}).get("technicals") or {}
    cal = dict((r.get("ticker"), r.get("date")) for r in (rj("state/earnings.json", {}) or {}).get("calendar") or [])
    track = [i for i in (rj("state/track.json", {}) or {}).get("ideas") or []]
    queue = []
    for t in names:
        card = rj("research/cards/%s.json" % t, {}) or {}
        q = quant.get(t) or {}
        px = (snap.get(t) or {}).get("last_price") or (tech.get(t) or {}).get("price") or (card.get("quote") or {}).get("price")
        rec = [i for i in track if i.get("t") == t]
        pack = {"ticker": t, "name": card.get("name") or t, "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "held": t in held, "price": px,
                "position": {k: (snap.get(t) or {}).get(k) for k in ("qty", "market_value", "pct_nav", "cost_basis")} if t in held else None,
                "risk": {k: q.get(k) for k in ("vol_1y", "beta_1y", "from_high_1y", "mdd_1y", "ret_1M", "ret_1Y", "sector")},
                "dcf": dcf_range(card.get("valuation")),
                "outside_fair_value": {"value": (tech.get(t) or {}).get("fair_value"), "method": (tech.get(t) or {}).get("fair_value_method"), "label": "outside model, named; not independent of analyst estimates"},
                "next_results": cal.get(t), "news": [n.get("title") for n in (card.get("news") or [])[:5] if isinstance(n, dict)],
                "smart_money": card.get("smart_money"),
                "paper_record": {"ideas": len(rec), "measured": len([i for i in rec if i.get("now")]),
                                 "vs_spy": (sum(float(i["now"]["idea"]) - float(i["now"]["spy"]) for i in rec if i.get("now")) / len([i for i in rec if i.get("now")])) if [i for i in rec if i.get("now")] else None},
                "sources": "state/quant.json, research/cards/%s.json, treasury/snapshot.json, digests/latest.json, state/earnings.json, state/track.json" % t}
        wj("state/memos/packs/%s.json" % t, pack)
        last = sorted(glob.glob(os.path.join(ROOT, "state", "memos", "memos", "%s-*.json" % t)))
        why = None
        if not last:
            why = "no memo yet"
        else:
            d = os.path.basename(last[-1])[len(t) + 1:len(t) + 11]
            if (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(d)).days > STALE_DAYS:
                why = "the last memo is over %d days old" % STALE_DAYS
            elif cal.get(t) and d < str(cal[t]) <= today:
                why = "results came out since the last memo"
        if why:
            queue.append({"ticker": t, "why": why, "held": t in held})
    queue.sort(key=lambda x: (not x["held"], x["ticker"]))
    wj("state/memos/queue.json", {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "due": queue, "per_run": 2,
                                  "rule": "A memo is due when a company has none, its last one is over %d days old, or results came out since. Holdings first; at most two a run." % STALE_DAYS})
    return queue


def score(closes, now=None):
    """Score every memo against what happened. closes(t) -> [(date, close), ...] oldest first."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    spy = closes("SPY") or []
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, "state", "memos", "memos", "*.json"))):
        try:
            m = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        t, d0 = m.get("ticker"), str(m.get("date") or "")[:10]
        cs = closes(t) or []
        s = {"ticker": t, "date": d0, "decision": (m.get("vote") or {}).get("decision"), "marks": {}}
        def after(series, n):
            i = next((k for k, x in enumerate(series) if str(x[0])[:10] >= d0), None)
            if i is None or i + n >= len(series):
                return None
            return float(series[i + n][1]) / float(series[i][1]) - 1
        base = ((m.get("dcf") or {}).get("base"))
        p0 = next((float(x[1]) for x in cs if str(x[0])[:10] >= d0), None)
        for name, n in MARKS:
            r, rs = after(cs, n), after(spy, n)
            if r is None or rs is None:
                continue
            vs = r - rs
            right = None
            if s["decision"] == "APPROVE":
                right = vs > 0
            elif s["decision"] == "DECLINE":
                right = vs < 0
            toward = None
            if base and p0:
                toward = abs(p0 * (1 + r) - base) < abs(p0 - base)
            s["marks"][name] = {"share": round(r, 4), "spy": round(rs, 4), "vs_spy": round(vs, 4), "decision_right": right, "toward_dcf": toward}
        out.append(s)
    done = [x for x in out if x["marks"]]
    rights = [v["decision_right"] for x in done for k, v in x["marks"].items() if k == max(x["marks"], key=lambda z: dict(MARKS)[z]) and v["decision_right"] is not None]
    summary = {"memos": len(out), "scored": len(done), "decision_right": (sum(1 for r in rights if r) / len(rights)) if rights else None, "cases": len(rights),
               "honesty": "Fewer than 20 scored decisions is too few cases to rely on." if len(rights) < 20 else ""}
    wj("state/memos/scores.json", {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "summary": summary, "memos": out,
                                   "method": "Each memo is measured from the close on its date: the share against the S&P 500 fund after 1, 3, 6 and 12 months (21, 63, 126, 252 trading days). APPROVE is right when the share beat the fund, DECLINE when it trailed it. 'Toward our DCF' asks whether the price moved closer to the memo's base value."})
    return summary


def index(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    memos = []
    for p in sorted(glob.glob(os.path.join(ROOT, "state", "memos", "memos", "*.json")), reverse=True):
        try:
            memos.append(json.load(open(p, encoding="utf-8")))
        except Exception:
            pass
    sc = rj("state/memos/scores.json", {}) or {}
    scored = dict(("%s|%s" % (x["ticker"], x["date"]), x) for x in sc.get("memos") or [])
    for m in memos:
        m["score"] = scored.get("%s|%s" % (m.get("ticker"), str(m.get("date"))[:10]))
    latest = {}
    for m in memos:
        latest.setdefault(m.get("ticker"), m)
    wj("state/memos/index.json", {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": list(latest.values()), "all": memos[:60],
                                  "queue": (rj("state/memos/queue.json", {}) or {}).get("due") or [], "scores": sc.get("summary"), "score_method": sc.get("method"),
                                  "private": rj("state/memos/private_data_report.json", None)})


def run(closes=None, now=None):
    q = packs(now)
    s = score(closes or (lambda t: []), now)
    index(now)
    return {"due": len(q), "scored": s.get("scored"), "memos": s.get("memos")}
