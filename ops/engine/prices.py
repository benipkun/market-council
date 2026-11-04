"""One price for every holding: Cboe's free delayed quotes (about 15 minutes behind), written into the books.

Ben, 4 Nov 2026: the app showed some holdings at today's price and others at an older close (the hourly pipeline
refreshes only the watchlist). The health job runs this every half hour while the US market is open, and at once
when the app's "Refresh prices" button leaves a request in requests/. Only prices and values change: share counts,
cost and cash are never touched. Standard library only.
"""
import datetime
import glob
import json
import os
import sys
import urllib.request

ROOT = os.environ.get("MC_ROOT", ".")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def quote(t, fetch=None):
    try:
        if fetch:
            d = fetch(t)
        else:
            req = urllib.request.Request("https://cdn.cboe.com/api/global/delayed_quotes/quotes/%s.json" % t, headers={"User-Agent": UA, "Accept": "application/json"})
            d = json.load(urllib.request.urlopen(req, timeout=20)).get("data") or {}
        px = float(d.get("current_price") or 0)
        when = str(d.get("last_trade_time") or "")
        return (px, when) if px > 0 else (None, None)
    except Exception:
        return None, None


def market_open(now):
    # US regular hours, Monday to Friday, 13:30 to 21:00 UTC (winter); a request from the app refreshes at any time
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 13 * 60 + 30 <= m <= 21 * 60 + 10


def refresh(snap, fetch=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    changed = []
    for p in snap.get("positions") or []:
        t = p.get("ticker")
        q = p.get("qty")
        if not t or q in (None, ""):
            continue
        px, when = quote(t, fetch)
        if not px:
            continue
        old = float(p.get("last_price") or 0)
        p["last_price"] = round(px, 4)
        p["market_value"] = round(float(q) * px, 2)
        p["price_as_of"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        p["price_source"] = "Cboe delayed quote" + (" (%s)" % when[:16] if when else "")
        if abs(px - old) > 1e-9:
            changed.append(t)
    cash = float(snap.get("cash") or 0)
    nav = cash + sum(float(p.get("market_value") or 0) for p in snap.get("positions") or [])
    for p in snap.get("positions") or []:
        p["pct_nav"] = round(100.0 * float(p.get("market_value") or 0) / nav, 2) if nav else 0
    if changed:
        snap["nav"], snap["cash_pct_of_nav"] = round(nav, 2), (round(100.0 * cash / nav, 2) if nav else 0)
        snap["as_of"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        snap["prices_as_of"] = snap["as_of"]
    return changed


def run(force=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    reqs = glob.glob(os.path.join(ROOT, "requests", "prices-*.json"))
    if not (force or reqs or market_open(now)):
        print("prices: market closed, no request")
        return []
    p = os.path.join(ROOT, "treasury", "snapshot.json")
    snap = json.load(open(p, encoding="utf-8"))
    changed = refresh(snap, now=now)
    if changed:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(snap, f, indent=1)
            f.write("\n")
    for r in reqs:
        os.remove(r)
    print("prices: %d holdings updated%s" % (len(changed), " (on request)" if reqs else ""))
    return changed


if __name__ == "__main__":
    run(force="--force" in sys.argv)
