"""Market Council keeper: the parts of the daily bookkeeping that need no judgement, done by plain code on GitHub's
servers, so they keep working when the AI routines are down. Standard library only. Nothing here places an order.

    python3 ops/engine/keeper.py books   re-price the holdings from the engine's latest closes (never touches cash,
                                         share counts or cost) and add the day's USD/HUF and EUR/HUF reference rates
    python3 ops/engine/keeper.py asks    answer questions waiting in inbox/queue/ for more than 20 minutes with the
                                         action list's own code; money entries and settings are left for the Trade
                                         Inbox routine, which keeps the full rules
"""
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.environ.get("MC_ROOT", ".")
CACHE = os.environ.get("MC_CACHE", os.path.join(ROOT, ".cache", "prices"))
WAIT_MIN = 10                     # the Trade Inbox routine answers first with a capable model; this is the backup
NL = "\n"
OFFLINE_NOTE = ("The chat assistant could not answer (the AI routines are switched off on the account), so your own "
                "system's code answered this from the action list.")


def rj(rel, default=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def wj(rel, obj):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write(NL)


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def last_close(sym):
    try:
        with open(os.path.join(CACHE, sym.replace("^", "_") + ".csv"), encoding="utf-8") as f:
            rows = [ln.split(",")[:2] for ln in f.read().split(NL) if "," in ln]
        d, v = rows[-1]
        return d, float(v)
    except Exception:
        return None, None


def remark(snap, closes, now):
    # bring every holding to its latest close the way the routines do: market value scales with the price; cash,
    # share counts and cost are never touched
    changed = []
    for p in snap.get("positions") or []:
        d, q = closes.get(p.get("ticker"), (None, None))
        if not q or q <= 0 or str(p.get("price_as_of") or "")[:10] > d:
            continue
        lp = float(p.get("last_price") or 0)
        if lp > 0:
            p["market_value"] = round(float(p.get("market_value") or 0) * q / lp, 2)
        elif p.get("qty") not in (None, ""):
            p["market_value"] = round(float(p["qty"]) * q, 2)
        else:
            continue
        if abs(q - lp) > 1e-9 or str(p.get("price_as_of") or "")[:10] != d:
            changed.append(p["ticker"])
        p["last_price"], p["price_as_of"] = round(q, 4), d + "T21:00:00Z"
    if not changed:
        return []
    cash = float(snap.get("cash") or 0)
    nav = cash + sum(float(p.get("market_value") or 0) for p in snap.get("positions") or [])
    for p in snap.get("positions") or []:
        p["pct_nav"] = round(100.0 * float(p.get("market_value") or 0) / nav, 2) if nav else 0
    snap["nav"], snap["cash_pct_of_nav"], snap["as_of"] = round(nav, 2), (round(100.0 * cash / nav, 2) if nav else 0), now
    return changed


def mnb_rates():
    # the Hungarian central bank's official rates (the ones used for Hungarian tax), from its public web service
    body = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:web="http://www.mnb.hu/webservices/"><soap:Body><web:GetCurrentExchangeRates/></soap:Body></soap:Envelope>')
    last = None
    for url in ("https://www.mnb.hu/arfolyamok.asmx", "http://www.mnb.hu/arfolyamok.asmx"):
        try:
            req = urllib.request.Request(url, data=body.encode("utf-8"), headers={"Content-Type": "text/xml; charset=utf-8", "User-Agent": "market-council",
                                         "SOAPAction": "http://www.mnb.hu/webservices/MNBArfolyamServiceSoap/GetCurrentExchangeRates"})
            with urllib.request.urlopen(req, timeout=25) as r:
                x = r.read().decode("utf-8", "replace").replace("&lt;", "<").replace("&gt;", ">")
            day = re.search(r'Day date="(\d{4}-\d\d-\d\d)"', x)
            usd = re.search(r'curr="USD">([\d.,]+)<', x)
            eur = re.search(r'curr="EUR">([\d.,]+)<', x)
            if day and usd and eur:
                return {"date": day.group(1), "usd_huf": float(usd.group(1).replace(",", ".")), "eur_huf": float(eur.group(1).replace(",", ".")), "source": "MNB"}
        except Exception as e:
            last = e
    raise last or ValueError("no MNB rates in the answer")


def ecb_rates():
    # the European Central Bank's daily reference rates (through frankfurter.app, free and keyless)
    def get(base):
        req = urllib.request.Request("https://api.frankfurter.app/latest?from=%s&to=HUF" % base, headers={"User-Agent": "market-council"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j = json.load(r)
        return j["date"], float(j["rates"]["HUF"])
    d1, usd = get("USD")
    d2, eur = get("EUR")
    return {"date": max(d1, d2), "usd_huf": usd, "eur_huf": eur, "source": "ECB reference rate"}


def books(now):
    snap = rj("treasury/snapshot.json")
    out = []
    if snap:
        closes = dict((p.get("ticker"), last_close(p.get("ticker"))) for p in snap.get("positions") or [] if p.get("ticker"))
        changed = remark(snap, closes, now)
        if changed:
            wj("treasury/snapshot.json", snap)
            out.append("books re-priced: %d holding%s" % (len(changed), "" if len(changed) == 1 else "s"))
    fx = rj("state/fx.json", {"rates": []}) or {"rates": []}
    rates = fx.get("rates") or []
    if not rates or rates[-1].get("date", "") < now[:10]:
        r, why = None, []
        for src in (mnb_rates, ecb_rates):
            try:
                r = src()
                break
            except Exception as e:
                why.append("%s: %s" % (src.__name__.split("_")[0].upper(), type(e).__name__))
        if r and (not rates or r["date"] > rates[-1].get("date", "")):
            rates.append(r)
            fx["rates"] = rates[-400:]
            wj("state/fx.json", fx)
            out.append("exchange rate added for %s from %s" % (r["date"], r["source"]))
        fx = rj("state/fx.json", fx) or fx
        fx["checked"] = {"at": now, "source": r["source"] if r else None, "problems": why}
        wj("state/fx.json", fx)
        if why:
            out.append("rate sources that failed: " + ", ".join(why))
    return out


def command(text):
    for ln in text.split(NL):
        s = ln.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def asks(now, wait_min=WAIT_MIN):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import actions
    qdir = os.path.join(ROOT, "inbox", "queue")
    try:
        names = sorted(n for n in os.listdir(qdir) if n.endswith(".md"))
    except Exception:
        names = []
    ledger = rj("treasury/ledger.json", {"entries": []}) or {"entries": []}
    done = set(e.get("id") for e in ledger.get("entries") or [])
    msgs = rj("state/messages.json", {"messages": [], "notified_picks": {}}) or {"messages": [], "notified_picks": {}}
    t_now = datetime.datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ")
    answered, waiting, ctx = [], 0, None
    done |= set(m.get("id") for m in msgs.get("messages") or [])
    for n in names:
        fid = n[:-3]
        m = re.match(r"(\d{8}T\d{6})", fid)
        try:
            with open(os.path.join(qdir, n), encoding="utf-8") as f:
                cmd = command(f.read())
        except Exception:
            continue
        if fid in done:
            continue
        if not cmd.lower().startswith("ask:"):
            waiting += 1
            continue
        if not m or (t_now - datetime.datetime.strptime(m.group(1), "%Y%m%dT%H%M%S")).total_seconds() < wait_min * 60:
            continue
        q = cmd[4:].strip()[:1000]
        if ctx is None:
            ctx = actions.build_ctx()
            ctx["spy"] = ctx.get("spy") or ((rj("state/actions.json", {}) or {}).get("inputs") or {}).get("spy")
        import answer as ANS
        reply, meta = ANS.reply(q)
        via = "ntfy" if "-ntfy-" in fid else "app"
        msgs["messages"] = (msgs.get("messages") or []) + [
            {"id": fid, "at": now, "from": "ben", "text": q, "via": via, "reply_to": None, "status": None},
            {"id": fid + "-r", "at": now, "from": "council", "text": reply, "via": None, "reply_to": fid, "status": "answered", "model": meta.get("model"), "note": meta.get("note")}]
        # the trade ledger is left to the Trade Inbox, so this can never overwrite a trade it records at the same moment
        os.remove(os.path.join(qdir, n))
        answered.append(fid)
    if answered:
        msgs["messages"] = msgs["messages"][-200:]
        wj("state/messages.json", msgs)
        stamp = now.replace("-", "").replace(":", "")
        wj("outbox/queue/%s-reply.json" % stamp, {"title": "Market Council reply", "message": "Your answer%s ready in the app (%d question%s)." % (
            "s are" if len(answered) > 1 else " is", len(answered), "" if len(answered) == 1 else "s"), "click": "https://benipkun.github.io/market-council/#chat", "tags": []})
    st = rj("state/keeper.json", {}) or {}
    st.update({"as_of": now, "answered": len(answered), "waiting_for_the_inbox": waiting,
               "note": ("%d money entr%s or setting%s wait for the Trade Inbox routine, which keeps the full bookkeeping rules." % (
                   waiting, "y" if waiting == 1 else "ies", "" if waiting == 1 else "s")) if waiting else None})
    wj("state/keeper.json", st)
    return ["%d question%s answered, %d other entr%s waiting for the Trade Inbox" % (len(answered), "" if len(answered) == 1 else "s", waiting, "y" if waiting == 1 else "ies")]


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "books"
    t = now_iso()
    for line in (books(t) if what == "books" else asks(t)):
        print("keeper:", line)