"""Results in separate parts (Ben's standing decision of 15 Nov 2026).

  - System picks: every position bought on a Council suggestion, gain or loss after fees, against the S&P 500 fund over
    the same days (open and closed).
  - Your own picks: positions bought before the decision desk existed or without a Council card, shown apart so they
    neither flatter nor hurt the system's record.
  - Conviction holding: the share(s) Ben keeps by his own choice (state/decisions.json keeps, UBER), kept separate and
    never counted in the system's record.
  - The total, with one line saying plainly whether it is up or down, and whether that is because of the conviction holding.
Writes state/results.json. Standard library only.
"""
import datetime
import json
import os

ROOT = os.environ.get("MC_ROOT", ".")
# Which buys the Council suggested: tickers with an offered idea or decision card on or before the buy day. Ben's own:
# NVO and CHWY (bought 25 Sep 2026, before the decision desk) and FISN (bought 28 Oct 2026 with no card).
OWN_BEFORE_DESK = "2026-10-01"


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def suggested(ticker, day):
    """True when a Council idea for this share was logged on or before the day of the buy."""
    for i in (rj("state/track.json", {}) or {}).get("ideas") or []:
        if i.get("t") == ticker and str(i.get("day")) <= day and i.get("offered", True):
            return i.get("id")
    for c in (rj("state/decisions.json", {}) or {}).get("cards") or []:
        if c.get("ticker") == ticker and str(c.get("created", ""))[:10] <= day and c.get("kind") in ("idea", "buy"):
            return c.get("id")
    return None


def fund_return(closes, d0, d1):
    a = next((float(c) for d, c in closes if str(d)[:10] >= d0), None)
    b = [float(c) for d, c in closes if str(d)[:10] <= d1]
    return (b[-1] / a - 1) if a and b else None


def run(closes=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    today = now.strftime("%Y-%m-%d")
    spy = (closes or (lambda t: []))("SPY") or []
    keeps = (rj("state/decisions.json", {}) or {}).get("keeps") or {}
    snap = rj("treasury/snapshot.json", {}) or {}
    pos = dict((p["ticker"], p) for p in snap.get("positions") or [] if p.get("ticker"))
    lots = {}
    for e in (rj("treasury/ledger.json", {}) or {}).get("entries") or []:
        if e.get("status") != "applied" or e.get("action") not in ("buy", "sell") or not e.get("ticker"):
            continue
        t, d = e["ticker"], str(e.get("at"))[:10]
        L = lots.setdefault(t, {"ticker": t, "bought": d, "cost": 0.0, "fees": 0.0, "proceeds": 0.0, "sold": None})
        usd, fee = float(e.get("usd") or 0), float(e.get("fee") or 0)
        if e["action"] == "buy":
            L["cost"] += usd
            L["fees"] += fee
        else:
            L["proceeds"] += usd - fee
            L["fees"] += fee
            L["sold"] = d
    rows = {"system": [], "own": [], "conviction": []}
    for t, L in lots.items():
        open_v = float((pos.get(t) or {}).get("market_value") or 0)
        if t in keeps:
            cost = float((pos.get(t) or {}).get("cost_basis") or L["cost"])      # UBER was held before the ledger began
        else:
            cost = L["cost"]
        value = open_v + L["proceeds"]
        gain = value - cost - (L["fees"] if t not in keeps else 0)
        end = L["sold"] if (L["sold"] and not open_v) else today
        fr = fund_return(spy, L["bought"], end)
        r = {"ticker": t, "bought": L["bought"], "closed": end if (L["sold"] and not open_v) else None, "cost": round(cost, 2), "value": round(value, 2),
             "gain": round(gain, 2), "gain_pct": round(gain / cost, 4) if cost else None, "fund_pct": round(fr, 4) if fr is not None else None,
             "vs_fund": round(gain / cost - fr, 4) if cost and fr is not None else None, "card": None}
        if t in keeps:
            r["standing"] = "Conviction holding: kept by Ben's choice; not sold, trimmed or argued against."
            rows["conviction"].append(r)
            continue
        card = suggested(t, L["bought"]) if L["bought"] >= OWN_BEFORE_DESK else None
        r["card"] = card
        rows["system" if card else "own"].append(r)
    for t in keeps:                                   # a conviction holding older than the ledger
        if t in pos and not any(x["ticker"] == t for x in rows["conviction"]):
            p = pos[t]
            g = float(p.get("market_value") or 0) - float(p.get("cost_basis") or 0)
            rows["conviction"].append({"ticker": t, "cost": round(float(p.get("cost_basis") or 0), 2), "value": round(float(p.get("market_value") or 0), 2),
                                       "gain": round(g, 2), "gain_pct": round(g / float(p.get("cost_basis") or 1), 4), "standing": "Conviction holding: kept by Ben's choice; not sold, trimmed or argued against."})

    def part(xs, name):
        cost = sum(x["cost"] for x in xs)
        gain = sum(x["gain"] for x in xs)
        fund = [x for x in xs if x.get("fund_pct") is not None]
        fund_gain = sum(x["cost"] * x["fund_pct"] for x in fund)
        return {"name": name, "positions": sorted(xs, key=lambda x: x.get("bought") or ""), "cost": round(cost, 2), "gain": round(gain, 2),
                "gain_pct": round(gain / cost, 4) if cost else None, "fund_gain": round(fund_gain, 2) if fund else None,
                "vs_fund_usd": round(gain - fund_gain, 2) if fund else None}
    sysp, own, conv = part(rows["system"], "System picks"), part(rows["own"], "Your own picks"), part(rows["conviction"], "Conviction holding")
    total = round(sysp["gain"] + own["gain"] + conv["gain"], 2)
    if total < 0 and conv["gain"] < 0 and total - conv["gain"] >= 0:
        line = "Total is down because of UBER: without it the rest is up $%.2f." % (total - conv["gain"])
    elif total < 0:
        line = "Total is down $%.2f, and not only because of UBER: the rest is down $%.2f too." % (abs(total), abs(total - conv["gain"]))
    else:
        line = "Total is up $%.2f." % total
    sys_line = ("System picks: %s$%.2f after recorded fees (%+.1f%%) on $%.0f invested; the S&P 500 fund over the same days: %s$%.2f." % (
        "+" if sysp["gain"] >= 0 else "-", abs(sysp["gain"]), 100 * (sysp["gain_pct"] or 0), sysp["cost"], "+" if (sysp["fund_gain"] or 0) >= 0 else "-", abs(sysp["fund_gain"] or 0))) if rows["system"] else "System picks: none yet."
    out = {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "system": sysp, "own": own, "conviction": conv, "total": total, "total_line": line, "system_line": sys_line,
           "conviction_line": "UBER (conviction holding, kept by your choice): %s$%.2f (%+.1f%%)." % ("+" if conv["gain"] >= 0 else "-", abs(conv["gain"]), 100 * (conv["gain_pct"] or 0)) if rows["conviction"] else "",
           "method": "Gain = today's value plus sale proceeds minus cost and recorded fees (two trades have $0 fees recorded, so results may be slightly flattering). The fund comparison buys the S&P 500 fund with the same money on the same day. Dividends are not included. A position counts as a system pick when a Council idea for it was logged on or before the buy day."}
    with open(os.path.join(ROOT, "state", "results.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    return out
