"""Target split between STOCKS, BONDS and ETFs (Ben, 16 Nov 2026). Plain code only.

  STOCKS: single company shares, including UBER.
  BONDS:  government and corporate bonds, and bond funds or bond ETFs.
  ETFs:   index and other non-bond funds (for example the S&P 500 index fund).

Writes state/allocation.json: the definitions, Ben's own target (free sliders, no presets: Ben, 16 Nov 2026) and its dated history, the actual split in % and
money, each part's expected return and risk with their correlations (so the app can show the outcome range of ANY split
before it is saved), the drift against the tolerance band, and the plan to reach the target (new money first; sales only
if Ben allowed them; UBER is never sold or trimmed: standing decision of 15 Nov 2026).
A new target comes from the app as answers/alloc-*.json (kind "allocation"); every change is logged with its date.
"""
import datetime
import glob
import json
import math
import os

import numpy as np

ROOT = os.environ.get("MC_ROOT", ".")
PARTS = ("stocks", "bonds", "etfs")
DEFS = {"stocks": "Single company shares, including UBER.",
        "bonds": "Government and corporate bonds, and bond funds or bond ETFs.",
        "etfs": "Index and other non-bond funds (for example the S&P 500 index fund)."}
BOND_FUNDS = ("SHY", "IEF", "TLT", "LQD", "TIP", "BNDX", "BND", "AGG", "VGIT", "IEI", "GOVT", "VCIT", "IBTA", "AGGG", "VAGF")
INDEX_FUNDS = ("SPY", "VOO", "IVV", "SPLG", "CSPX", "VUSA", "SXR8", "VUAA", "VEA", "VWO", "XLP", "XLU", "XLV", "GLD", "QQQ", "VT", "VTI", "IWDA", "SWDA")
BUY_FUND = {"bonds": "IEF", "etfs": "SPY"}          # what new money buys for a fund part (the funds the engine already prices)
FEE_PCT, FEE_MIN, MIN_ORDER, TAX = 0.0025, 1.0, 100.0, 0.15


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


def part_of(t, assets=None):
    a = (assets or {}).get(t) or {}
    cls = str(a.get("cls") or "")
    if t in BOND_FUNDS or cls.startswith("Bond"):
        return "bonds"
    if t in INDEX_FUNDS or "fund" in cls.lower() or cls in ("Commodity", "Cash-like"):
        return "etfs"
    return "stocks"


def fee(usd):
    return round(max(FEE_MIN, FEE_PCT * usd), 2) if usd > 0 else 0.0


def actual(snap, assets):
    pos = [p for p in snap.get("positions") or [] if p.get("ticker") and float(p.get("market_value") or 0) > 0]
    by = dict((k, 0.0) for k in PARTS)
    rows = []
    for p in pos:
        k = part_of(p["ticker"], assets)
        by[k] += float(p["market_value"])
        rows.append({"ticker": p["ticker"], "part": k, "value": round(float(p["market_value"]), 2), "cost": float(p.get("cost_basis") or 0)})
    inv = sum(by.values())
    cash = float(snap.get("cash") or 0)
    return {"invested": round(inv, 2), "cash": round(cash, 2), "usd": dict((k, round(v, 2)) for k, v in by.items()),
            "pct": dict((k, round(100 * v / inv, 1) if inv else 0.0) for k, v in by.items()), "positions": rows}


def assumptions(closes, assets, rf, erp, act):
    """Expected return (the engine's own rule: risk-free plus beta times 5%) and risk of each part, from three years of
    daily closes: STOCKS = Ben's stock holdings as weighted now, BONDS = IEF, ETFs = the S&P 500 fund."""
    names = {"stocks": [r for r in act["positions"] if r["part"] == "stocks"], "bonds": "IEF", "etfs": "SPY"}
    series = {}
    for k in PARTS:
        if k == "stocks":
            rows = names[k] or [{"ticker": "SPY", "value": 1.0}]
            tot = sum(r["value"] for r in rows) or 1.0
            parts = [(r["value"] / tot, dict(closes(r["ticker"]) or [])) for r in rows]
        else:
            parts = [(1.0, dict(closes(names[k]) or []))]
        series[k] = parts
    days = None
    for k in PARTS:
        for w, s in series[k]:
            ds = set(d for d in s)
            days = ds if days is None else (days & ds)
    days = sorted(days or [])[-756:]
    if len(days) < 200:
        return None
    R = []
    for k in PARTS:
        r = np.zeros(len(days) - 1)
        for w, s in series[k]:
            v = np.array([s[d] for d in days], dtype=float)
            r += w * (v[1:] / v[:-1] - 1)
        R.append(r)
    R = np.array(R).T
    cov = np.cov(R, rowvar=False) * 252
    spy = R[:, 2]
    beta = [float(np.cov(R[:, i], spy)[0, 1] / np.var(spy, ddof=1)) for i in range(3)]
    mu = [rf + b * erp for b in beta]
    mu[1] = max(mu[1], rf - 0.005)              # bonds: near the risk-free rate even when their beta to stocks is ~0
    return {"mu": dict(zip(PARTS, [round(x, 4) for x in mu])), "vol": dict(zip(PARTS, [round(float(math.sqrt(cov[i, i])), 4) for i in range(3)])),
            "cov": [[round(float(cov[i, j]), 6) for j in range(3)] for i in range(3)], "days": len(days), "from": days[0], "to": days[-1],
            "method": "Each part's yearly return = risk-free rate %.2f%% + its beta to the S&P 500 fund x %.0f%% (the engine's own assumption), bonds at least the risk-free rate minus 0.5 point; risk and correlations from %d trading days of daily closes (STOCKS = your stock holdings as weighted today, BONDS = IEF, ETFs = the S&P 500 fund). Outcomes assume normal yearly returns compounded (lognormal); estimates, not promises." % (100 * rf, 100 * erp, len(days))}


def outcomes(split, A, years):
    w = np.array([split[k] / 100.0 for k in PARTS])
    mu = float(w @ np.array([A["mu"][k] for k in PARTS]))
    var = float(w @ np.array(A["cov"]) @ w)
    s = math.sqrt(max(var, 1e-12))
    m = (mu - var / 2) * years
    sd = s * math.sqrt(years)
    q = lambda z: round(math.exp(m + z * sd) - 1, 4)
    loss = 0.5 * (1 + math.erf((-m / sd) / math.sqrt(2))) if sd else 0.0
    return {"typical": q(0), "bad_1_in_10": q(-1.2816), "good_1_in_10": q(1.2816), "chance_of_loss": round(loss, 3)}


def preview(split, A, max_loss):
    one, five = outcomes(split, A, 1), outcomes(split, A, 5)
    w = np.array([split[k] / 100.0 for k in PARTS])
    s = math.sqrt(float(w @ np.array(A["cov"]) @ w))
    mu = float(w @ np.array([A["mu"][k] for k in PARTS]))
    bad_year = round(math.exp(mu - s * s / 2 - 1.6449 * s) - 1, 4)          # 1 year in 20
    return {"1y": one, "5y": five, "bad_year": bad_year, "max_loss": -max_loss / 100.0, "breaks_profile": bad_year < -max_loss / 100.0}


def tax_on(row, sell_usd):
    gain = (row["value"] - row["cost"]) * (sell_usd / row["value"]) if row["value"] else 0.0
    return round(max(0.0, gain) * TAX, 2), round(gain, 2)


def plan(target, act, keeps, ideas=None):
    """New money first, to the part furthest below target; sales of other positions only if allowed. UBER never sold."""
    inv, cash = act["invested"], act["cash"]
    total = inv + cash
    band = float(target.get("band") or 5)
    gap = dict((k, round(target[k] / 100.0 * total - act["usd"][k], 2)) for k in PARTS)   # + = below target
    drift = dict((k, round(act["pct"][k] - target[k], 1)) for k in PARTS)
    outside = [k for k in PARTS if abs(act["pct"][k] - target[k]) > band]          # drift in points of the invested money
    steps, facts = [], []
    keep_stock = sum(r["value"] for r in act["positions"] if r["ticker"] in keeps and r["part"] == "stocks")
    if total and keep_stock / total * 100 > target["stocks"]:
        facts.append("UBER alone is %.0f%% of the portfolio, above the %d%% STOCKS target. It is your conviction holding and is not sold; the gap closes only as new money goes to BONDS and ETFs." % (100 * keep_stock / total, target["stocks"]))
    # 1. new money (free cash) to the part furthest below target
    left = cash
    for k in sorted(PARTS, key=lambda x: -gap[x]):
        if left < MIN_ORDER or gap[k] <= 0:
            continue
        put = round(min(left, gap[k]), 2)
        if put < MIN_ORDER:
            continue
        if k == "stocks":
            steps.append({"step": len(steps) + 1, "type": "BUY", "part": k, "usd": put, "fees": fee(put), "what": "the best stock idea on the action list",
                          "line": "STOCKS are below target: $%.2f of new money can go to a stock idea from the action list." % put})
        else:
            t = BUY_FUND[k]
            steps.append({"step": len(steps) + 1, "type": "BUY", "part": k, "ticker": t, "usd": put, "fees": fee(put),
                          "line": "BUY $%.2f of %s (%s) with new money, fees $%.2f." % (put, t, "a US Treasury bond fund, 7-10 years" if k == "bonds" else "the S&P 500 fund", fee(put))})
        left -= put
        gap[k] -= put
    # 2. sales, only if Ben allowed them: from parts above target (never a conviction holding), losses first (no tax)
    if target.get("allow_sales"):
        uber_over = bool(total and keep_stock / total * 100 > target["stocks"])
        for k in PARTS:
            over = -gap[k]
            if over <= band / 100.0 * total:
                continue
            if k == "stocks" and uber_over:
                continue          # UBER alone is above the STOCKS target: that gap closes only with new money (Ben, 16 Nov 2026)
            rows = sorted([r for r in act["positions"] if r["part"] == k and r["ticker"] not in keeps], key=lambda r: r["value"] - r["cost"])
            for r in rows:
                if over < MIN_ORDER:
                    break
                sell = round(min(r["value"], over), 2)
                if sell < MIN_ORDER and sell < r["value"]:
                    continue
                tx, g = tax_on(r, sell)
                steps.append({"step": len(steps) + 1, "type": "SELL", "part": k, "ticker": r["ticker"], "usd": sell, "fees": fee(sell), "tax_estimate": tx,
                              "line": "SELL $%.2f of %s (%s), fees $%.2f, %s." % (sell, r["ticker"], k.upper(), fee(sell), ("tax estimate $%.2f on a $%.2f gain (15%%)" % (tx, g)) if g > 0 else "a loss, so no tax")})
                over -= sell
        sold = sum(s["usd"] - s["fees"] for s in steps if s["type"] == "SELL")
        for k in sorted(PARTS, key=lambda x: -gap[x]):
            if sold < MIN_ORDER or gap[k] <= MIN_ORDER or k == "stocks":
                continue
            put = round(min(sold, gap[k]), 2)
            t = BUY_FUND[k]
            steps.append({"step": len(steps) + 1, "type": "BUY", "part": k, "ticker": t, "usd": put, "fees": fee(put),
                          "line": "BUY $%.2f of %s with the proceeds, fees $%.2f." % (put, t, fee(put))})
            sold -= put
    return {"gap_usd": gap, "drift_points": drift, "outside_band": outside, "band": band, "steps": steps, "facts": facts,
            "fees": round(sum(s["fees"] for s in steps), 2), "tax_estimate": round(sum(s.get("tax_estimate", 0) for s in steps), 2),
            "note": "Sales are suggested only because you allowed them." if target.get("allow_sales") else "New money only: sales are not suggested unless you allow them."}


def read_target():
    tg = rj("state/allocation/target.json", None)
    hist = rj("state/allocation/history.json", {"changes": []}) or {"changes": []}
    for p in sorted(glob.glob(os.path.join(ROOT, "answers", "alloc-*.json"))):
        try:
            a = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if a.get("kind") != "allocation" or any(c.get("id") == a.get("id") for c in hist["changes"]):
            continue
        s = [int(round(float(a.get(k) or 0))) for k in PARTS]
        if sum(s) != 100 or min(s) < 0:
            continue
        tg = dict(zip(PARTS, s))
        tg.update(band=max(1, min(20, int(a.get("band") or 5))), allow_sales=bool(a.get("allow_sales")), set_at=a.get("at"), id=a.get("id"))
        hist["changes"].append(dict(tg))
    wj("state/allocation/history.json", hist)
    if tg:
        wj("state/allocation/target.json", tg)
    return tg, hist


def run(closes=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    closes = closes or (lambda t: [])
    q = rj("state/quant.json", {}) or {}
    assets, opt = q.get("assets") or {}, q.get("opt") or {}
    snap = rj("treasury/snapshot.json", {}) or {}
    keeps = set(((rj("state/decisions.json", {}) or {}).get("keeps") or {}).keys())
    prof = [p for p in (rj("state/profiles.json", {}) or {}).get("people") or [] if p.get("id") == "ben"]
    max_loss = float((prof[0] if prof else {}).get("max_loss_pct") or 30)
    act = actual(snap, assets)
    A = assumptions(closes, assets, float(opt.get("rf") or 0.04), float(opt.get("erp") or 0.05), act)
    tg, hist = read_target()
    cur = dict((k, act["pct"][k]) for k in PARTS)
    out = {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "definitions": DEFS, "presets": [], "actual": act, "target": tg, "history": hist["changes"][-30:],
           "assumptions": A, "max_loss": max_loss, "current_preview": preview(cur, A, max_loss) if A and act["invested"] else None,
           "method": "Plain code (ops/engine/allocation.py). Parts by type: bond funds are BONDS, index and other non-bond funds ETFs, everything else STOCKS. Percentages are of the invested money; cash is shown apart and counts as new money for the plan."}
    if tg:
        out["target_preview"] = preview(tg, A, max_loss) if A else None
        out["plan"] = plan(tg, act, keeps)
        # one phone message when a part drifts outside the band (only when the set of drifting parts changes)
        prev = (rj("state/allocation/alert.json", {}) or {}).get("outside") or []
        now_out = out["plan"]["outside_band"]
        if now_out and sorted(now_out) != sorted(prev):
            fix = (out["plan"]["steps"] or [{"line": "add new money to the parts below target"}])[0]["line"]
            msg = "Your split has drifted: %s outside the +-%d point band (target %s). Suggested fix: %s" % (
                ", ".join("%s %.0f%%" % (k.upper(), act["pct"][k]) for k in now_out), out["plan"]["band"], "/".join(str(tg[k]) for k in PARTS), fix)
            d = os.path.join(ROOT, "outbox", "queue")
            os.makedirs(d, exist_ok=True)
            wj(os.path.relpath(os.path.join(d, "%s-drift.json" % now.strftime("%Y%m%dT%H%M%SZ")), ROOT),
               {"title": "Market Council: split drifted", "message": msg[:600], "click": "https://benipkun.github.io/market-council/#portfolio", "tags": ["scales"]})
            out["alert_sent"] = msg
        wj("state/allocation/alert.json", {"as_of": out["as_of"], "outside": now_out})
    wj("state/allocation.json", out)
    return out
