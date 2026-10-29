"""Trade check and exposure. Plain code, standard library only.

Ben, 29 Oct 2026: "as soon as I lock in a trade check it and it should be classified so I know my exposure".

Runs in the health job right after a trade reaches the books (the relay starts it when treasury/ledger.json
changes) and again in every engine run. Each new buy or sell in the ledger is checked against the books, the
last price, the risk profile's limits and the order plans, and its share is classified (type, sector, country,
how jumpy it is, where the idea came from). The whole portfolio's exposure is written to state/exposure.json.
A new trade sends one phone message, which names no share and no amount.
"""
import datetime
import json
import os
import sys

ROOT = os.environ.get("MC_ROOT", ".")
NEW_DAYS = 2           # a trade logged in the last two days, not yet checked, gets a phone message
PRICE_GAP = 0.15       # a logged price more than 15% away from the last price is flagged as a possible typo
SECTOR_GUIDE = 0.40    # a sector above 40% of the portfolio is flagged (a common guide, not part of your profile)
JUMPY = 0.40           # a share moving more than 40% a year (or with a beta above 2) counts as jumpy
COUNTRY = {"US": "United States", "DK": "Denmark", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "NL": "Netherlands",
           "CH": "Switzerland", "IE": "Ireland", "SE": "Sweden", "NO": "Norway", "CA": "Canada", "JP": "Japan", "CN": "China", "HU": "Hungary"}
EUROPE = {"Denmark", "United Kingdom", "Germany", "France", "Netherlands", "Switzerland", "Ireland", "Sweden", "Norway", "Finland", "Spain",
          "Italy", "Belgium", "Austria", "Hungary", "Poland", "Portugal"}


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


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def num(v):
    try:
        return float(v)
    except Exception:
        return None


def known(v):
    return v if v and str(v).strip().lower() not in ("unclassified", "unknown", "none", "n/a") else None


def classify(t, src):
    # the share's type, sector, country and theme, from the first record that knows it
    out = {"type": None, "sector": None, "industry": None, "country": None, "theme": None, "source": None}
    for name, rec in (("your share list", (src["classes"] or {}).get(t)), ("the engine's list", (src["meta"] or {}).get(t)),
                      ("the wide screen", src["screen"].get(t)), ("the engine's prices", (src["quant"] or {}).get(t))):
        rec = rec or {}
        for k, keys in (("type", ("type", "cls")), ("sector", ("sector",)), ("industry", ("industry",)), ("country", ("country",)), ("theme", ("theme",))):
            for kk in keys:
                if not out[k] and known(rec.get(kk)):
                    out[k] = str(rec[kk])
                    out["source"] = out["source"] or name
    out["type"] = {"Equity": "Stock"}.get(out["type"], out["type"])
    out["country"] = COUNTRY.get(out["country"], out["country"])
    c = out["country"]
    out["region"] = None if not c else ("US" if c == "United States" else ("Europe" if c in EUROPE else c))
    q = (src["quant"] or {}).get(t) or {}
    cl = (src["classes"] or {}).get(t) or {}
    vol, beta = num(q.get("vol_1y")), num(cl.get("beta"))
    out["vol_1y"], out["beta"] = vol, beta
    if vol is not None:
        out["risk"] = "jumpy" if vol > JUMPY else ("normal" if vol > 0.25 else "calm")
        out["risk_why"] = "moves about %d%% a year" % round(100 * vol)
    elif beta is not None:
        out["risk"] = "jumpy" if beta > 2 else "normal"
        out["risk_why"] = "beta %.1f (moves %.1f times as much as the market); too little price history to measure it here" % (beta, beta)
    else:
        out["risk"], out["risk_why"] = None, "not measured yet"
    for k in ("note", "listed", "market_cap_usd", "name"):
        if cl.get(k):
            out[k] = cl[k]
    names = [cl.get("name"), ((src["meta"] or {}).get(t) or {}).get("name"), (src["screen"].get(t) or {}).get("name"), q.get("name")]
    out["name"] = next((n for n in names if known(n) and n != t), None)
    return out


def origin(e, cards):
    # where the idea came from: a Market Council card raised before the trade (a buy card for a buy, a sell card or a
    # swap that sells it for a sell), or not
    at = str(e.get("at"))
    day = lambda s: datetime.date.fromisoformat(str(s)[:10])
    if e.get("action") == "sell":
        mine = lambda c: (c.get("kind") == "sell" and c.get("ticker") == e.get("ticker")) or ((c.get("verdict") or {}).get("type") == "SWAP" and ("sell %s" % e.get("ticker")) in str((c.get("verdict") or {}).get("line")))
    else:
        mine = lambda c: c.get("kind") == "idea" and c.get("ticker") == e.get("ticker")
    hits = [c for c in cards if mine(c) and str(c.get("created")) <= at
            and (day(at) - day(c.get("created"))).days <= 30]
    if hits:
        c = sorted(hits, key=lambda c: str(c.get("created")))[-1]
        return {"kind": "suggested", "text": "suggested by Market Council (card %s, %s)" % (c.get("id"), str(c.get("created"))[:10]), "card": c.get("id")}
    why = str(e.get("why") or "")
    if "outside" in why.lower():
        return {"kind": "outside", "text": "an outside source (%s)" % why[:80]}
    return {"kind": "own", "text": "your own idea" + (" (%s)" % why[:80] if why else "")}


def check(e, ctx):
    # every check on one trade: ok, warn (worth knowing) or fail (the books do not match)
    t, out = e["ticker"], []
    pos, nav, lim = ctx["pos"].get(t), ctx["nav"], ctx["lim"]
    add = lambda name, status, text: out.append({"name": name, "status": status, "text": text})
    books_at = str(ctx["books_as_of"] or "")
    if e["action"] == "buy":
        if pos and (num(pos.get("qty")) or 0) > 0:
            add("books", "ok", "In your books: %s shares worth $%.2f." % (("%.4f" % float(pos["qty"])).rstrip("0").rstrip("."), num(pos.get("market_value")) or 0))
        elif books_at and books_at < str(e.get("at")):
            add("books", "warn", "Your books were last updated before this trade (%s); the next bookkeeping run adds it." % books_at[:16])
        else:
            add("books", "fail", "The trade is in the ledger but %s is not in your holdings. Check the entry." % t)
    else:
        left = num((pos or {}).get("qty")) or 0
        add("books", "ok", ("In your books: %s shares of %s left." % (("%.4f" % left).rstrip("0").rstrip("."), t)) if left > 0 else "In your books: you no longer hold %s." % t)
    px, last = num(e.get("price")), num(((ctx["quant"] or {}).get(t) or {}).get("last")) or num((pos or {}).get("last_price"))
    if px and last:
        gap = px / last - 1
        add("price", "warn" if abs(gap) > PRICE_GAP else "ok",
            ("You logged $%.4g; the last price is $%.4g (%+.0f%%). Check the price you typed." if abs(gap) > PRICE_GAP else
             "You logged $%.4g; the last price is $%.4g (%+.0f%%), so the price looks right.") % (px, last, 100 * gap))
    if e["action"] == "buy" and pos and nav:
        share, cap = (num(pos.get("market_value")) or 0) / nav, num(lim.get("stock_cap")) or 0.3
        add("size", "warn" if share > cap else "ok", "%s is %.1f%% of your portfolio; your profile's limit per share is %d%%." % (t, 100 * share, round(100 * cap)))
        plan = ctx["plans"].get(t)
        rpt = num(lim.get("risk_per_trade")) or 0.015
        if plan and num(plan.get("loss_share_of_portfolio")) is not None:
            ls = num(plan["loss_share_of_portfolio"])
            add("risk", "warn" if ls > rpt else "ok", "At its stop ($%.2f) you would lose $%.2f, %.1f%% of your portfolio; your profile's guide is %.1f%% per trade." % (
                num(plan.get("stop")) or 0, num(plan.get("loss_at_stop")) or 0, 100 * ls, 100 * rpt))
        else:
            add("risk", "warn", "No order plan yet: the next engine run writes its stop and take-profit in PLANS.")
    ca = num(e.get("cash_after"))
    if ca is not None and nav:
        buf = (num(lim.get("min_cash")) or 0.03) * nav
        add("cash", "warn" if ca < buf else "ok", "Cash after the trade: $%.2f; your profile keeps a %d%% buffer ($%.2f)." % (ca, round(100 * (num(lim.get("min_cash")) or 0.03)), buf))
    cl = ctx["class"].get(t) or classify(t, ctx["src"])
    if e["action"] == "buy":
        sec = cl.get("sector")
        if sec:
            sp = sum(p["value"] for p in ctx["expo"]["positions"] if p.get("sector") == sec) / nav if nav else 0
            add("sector", "warn" if sp > SECTOR_GUIDE else "ok", "%s is now %.0f%% of your portfolio%s." % (
                sec, 100 * sp, " (above %d%%, a common guide for one sector)" % round(100 * SECTOR_GUIDE) if sp > SECTOR_GUIDE else ""))
        missing = [k for k in ("type", "sector", "country") if not cl.get(k)]
        if missing:
            add("class", "warn", "Not classified yet (%s unknown): the next Trade Inbox run looks it up." % ", ".join(missing))
    st = "fail" if any(c["status"] == "fail" for c in out) else ("warn" if any(c["status"] == "warn" for c in out) else "ok")
    return st, out


def group(positions, key, cash, nav, label=None):
    g = {}
    for p in positions:
        k = p.get(key) or "Not known yet"
        g[k] = g.get(k, 0.0) + p["value"]
    rows = [{"name": (label or {}).get(k, k), "value": round(v, 2), "pct": round(v / nav, 4) if nav else None,
             "tickers": [p["ticker"] for p in positions if (p.get(key) or "Not known yet") == k]} for k, v in g.items()]
    rows.sort(key=lambda r: -r["value"])
    if cash is not None:
        rows.append({"name": "Cash", "value": round(cash, 2), "pct": round(cash / nav, 4) if nav else None, "tickers": []})
    return rows


def build(now=None):
    now = now or now_iso()
    snap = rj("treasury/snapshot.json", {}) or {}
    ledger = rj("treasury/ledger.json", {}) or {}
    dec = rj("state/decisions.json", {}) or {}
    uni = rj("ops/engine/universe.json", {}) or {}
    src = {"classes": rj("state/classes.json", {}) or {}, "meta": uni.get("assets") or {},
           "screen": dict((r.get("t"), r) for r in (rj("state/screen.json", {}) or {}).get("rows") or [] if r.get("t")),
           "quant": (rj("state/quant.json", {}) or {}).get("assets") or {}}
    nav, cash = num(snap.get("nav")) or 0.0, num(snap.get("cash")) or 0.0
    pos = dict((p["ticker"], p) for p in snap.get("positions") or [] if p.get("ticker"))
    plans = dict((p.get("ticker"), p) for p in (rj("state/plans.json", {}) or {}).get("holdings") or [] if p.get("ticker"))
    cards = dec.get("cards") or []
    keeps = dec.get("keeps") or {}
    entries = [e for e in ledger.get("entries") or [] if e.get("status") == "applied" and not e.get("undone_by") and e.get("ticker") and e.get("action") in ("buy", "sell")]
    first_buy = {}
    for e in sorted(entries, key=lambda e: str(e.get("at"))):
        if e["action"] == "buy":
            first_buy.setdefault(e["ticker"], e)
    cls = dict((t, classify(t, src)) for t in set(pos) | set(e["ticker"] for e in entries))
    positions = []
    for t, p in pos.items():
        v = num(p.get("market_value")) or 0.0
        if v <= 0:
            continue
        c = cls[t]
        o = origin(first_buy[t], cards) if t in first_buy else {"kind": "own", "text": "held before the books started"}
        positions.append({"ticker": t, "name": c.get("name"), "value": round(v, 2), "pct": round(v / nav, 4) if nav else None, "type": c.get("type"),
                          "sector": c.get("sector"), "country": c.get("country"), "region": c.get("region"), "theme": c.get("theme"),
                          "risk": c.get("risk"), "risk_why": c.get("risk_why"), "plan": (plans.get(t) or {}).get("label"), "kept": t in keeps,
                          "origin": o["kind"], "origin_text": o["text"]})
    positions.sort(key=lambda p: -p["value"])
    invested = sum(p["value"] for p in positions)
    expo = {"positions": positions, "invested": round(invested, 2),
            "by_sector": group(positions, "sector", cash, nav), "by_region": group(positions, "region", None, nav),
            "by_type": group(positions, "type", None, nav), "by_risk": group(positions, "risk", None, nav, {"jumpy": "Jumpy", "normal": "Normal", "calm": "Calm"}),
            "by_origin": group(positions, "origin", None, nav, {"suggested": "Suggested by Market Council", "outside": "Outside source", "own": "Your own idea"}),
            "largest": positions[0] if positions else None,
            "top3_pct": round(sum(p["value"] for p in positions[:3]) / nav, 4) if nav else None,
            "unknown": [p["ticker"] for p in positions if not (p.get("sector") and p.get("country") and p.get("type"))]}
    ctx = {"pos": pos, "nav": nav, "lim": (dec.get("profile") or {}).get("limits") or {}, "books_as_of": snap.get("as_of"), "quant": src["quant"],
           "plans": plans, "class": cls, "src": src, "expo": expo}
    trades = []
    for e in sorted(entries, key=lambda e: str(e.get("at")), reverse=True)[:10]:
        st, checks = check(e, ctx)
        o = origin(e, cards)
        trades.append({"id": e.get("id"), "at": e.get("at"), "action": e["action"], "ticker": e["ticker"], "usd": num(e.get("usd")), "qty": num(e.get("qty")),
                       "price": num(e.get("price")), "status": st, "checks": checks, "origin": o["text"], "class": cls.get(e["ticker"])})
    return {"as_of": now, "books_as_of": snap.get("as_of"), "nav": round(nav, 2), "cash": round(cash, 2), "trades": trades, "exposure": expo,
            "method": "Each trade is read back against your books, the last price, your risk profile (limit per share, risk per trade, "
                      "cash buffer) and its order plan. Shares are classified from your share list, the engine's list and the wide screen; "
                      "a share none of them knows is looked up by the Trade Inbox. Plain code, ops/engine/tradecheck.py."}, entries


def run(now=None, phone=True):
    out, entries = build(now)
    old = rj("state/exposure.json", None)
    first = old is None
    done = set((old or {}).get("checked_ids") or [])
    cut = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=NEW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new = [t for t in out["trades"] if t["id"] not in done and str(t["at"]) >= cut and not first]
    out["checked_ids"] = sorted(done | set(e.get("id") for e in entries if e.get("id")))
    out["new"] = [t["id"] for t in new]
    strip = lambda d: dict((k, v) for k, v in (d or {}).items() if k not in ("as_of", "new"))
    if strip(out) != strip(old):
        wj("state/exposure.json", out)
    if phone and new:
        bad = any(t["status"] == "fail" for t in new)
        msg = {"title": "Market Council: " + ("a trade needs a look" if bad else "trade checked"),
               "message": ("A check on your new trade did not pass. Open TODAY to see which." if bad else
                           "Your new trade is checked and classified. Open TODAY to see the checks and your exposure."),
               "click": "https://benipkun.github.io/market-council/#today", "tags": ["warning" if bad else "white_check_mark"]}
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        wj("outbox/queue/%s-trade-checked.json" % ts, msg)
    return out


if __name__ == "__main__":
    o = run(phone="--quiet" not in sys.argv)
    print("trade check: %d trades shown, %d new, %d unclassified" % (len(o["trades"]), len(o.get("new") or []), len(o["exposure"]["unknown"])))
