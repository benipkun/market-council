"""Company files, sector briefs, the thesis tracker and the three-book comparison (Ben, 21 Nov 2026).

A file per holding, watchlist share and the best five new ideas (state/files/<T>.json), assembled by plain code from
what is already on record, each part with its source and date:
  - the narrative (how it makes money, segments, competitors, what drives the price, management and its record,
    bull and bear case, what would change our mind): the Investment Committee's latest memo (ops/COMMITTEE.md);
  - key numbers and their trend: SEC filings (10-K), re-read only when a new 10-K, 10-Q or results 8-K arrives;
  - the valuation range: our own cash-flow model (research/cards) with its method, beside the analysts' range;
  - the record against estimates: our earnings history (beat or miss, how often);
  - the 7 checks, the Forecaster's range, the event study line for the next event, upcoming dates;
  - news of the last 30 days that scored as important, each marked strengthens / weakens / no change.
Files update on events, not daily: a new filing, results, an important news item or a new memo. An event also puts
the company in the committee's queue (state/files/due.json, read by memos.py), so the narrative is rewritten by the
routine, not by a paid model each day.
Thesis tracker: important items are checked against the file. With an API key and budget left the main model marks
them; otherwise plain rules do (tone, source reliability, severe filings) and say so. A broken thesis on a holding
raises a review card (never for a position you chose to keep: UBER gets facts only, within the standing decision).
Three books: from 21 Nov 2026, on paper, the system with the news and files, the system without them, and the
S&P 500 fund, each idea bought with the same dollars on the day, after Revolut fees (0.25%, at least $1, both ways).
"""
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import news as N  # noqa: E402

ROOT = N.ROOT
FEW, VERDICT_CASES, VERDICT_DAYS = 20, 60, 91
BOOKS_START = "2026-11-21"
STAKE = 250.0
FEE_RATE, FEE_MIN = 0.0025, 1.0
WEAK_DAYS, WEAK_COUNT = 30, 2


def memo_of(t):
    ms = sorted(glob.glob(os.path.join(ROOT, "state", "memos", "memos", "%s-*.json" % t)))
    if not ms:
        return None, None
    m = N.rj(os.path.relpath(ms[-1], ROOT).replace("\\", "/"), {}) or {}
    return m, m.get("date") or os.path.basename(ms[-1])[len(t) + 1:len(t) + 11]


def numbers(t, old):
    """Key numbers from the SEC (10-K), with the trend; re-read only when a new report arrived since the last read."""
    try:
        import sec
    except Exception:
        return old
    try:
        fin = sec.financials(t)
    except Exception:
        fin = None
    if not fin:
        return old or {"note": "No SEC annual figures (foreign filer or not covered); see the memo's key numbers.", "source": "SEC EDGAR companyfacts"}
    heads = fin["incomeStatementTable"]["headers"]
    years = [heads["value%d" % i] for i in range(2, 6) if heads.get("value%d" % i)]
    rows = {}
    for tbl in ("incomeStatementTable", "balanceSheetTable", "cashFlowTable"):
        for r in fin[tbl]["rows"]:
            rows[r["value1"]] = [r.get("value%d" % i) for i in range(2, 2 + len(years))]
    rev, op = rows.get("Total Revenue") or [], rows.get("Operating Income") or []
    capex = rows.get("Capital Expenditures") or []
    out = {"years": years, "unit": "USD thousands", "source": "SEC EDGAR companyfacts (10-K)", "read_at": N.iso()[:10], "rows": rows}
    if len(rev) >= 2 and rev[0] and rev[1]:
        out["revenue_growth"] = round(rev[0] / rev[1] - 1, 4)
    if rev and op and rev[0] and op[0] is not None:
        out["operating_margin"] = round(op[0] / rev[0], 4)
        if len(rev) > 1 and len(op) > 1 and rev[1] and op[1] is not None:
            out["margin_trend"] = round(op[0] / rev[0] - op[1] / rev[1], 4)
    out["trend"] = " ".join(s for s in [
        ("revenue %+.1f%% in the latest year" % (100 * out["revenue_growth"])) if "revenue_growth" in out else "",
        ("operating margin %.1f%%" % (100 * out["operating_margin"])) if "operating_margin" in out else "",
        ("(%+.1f points on the year before)" % (100 * out["margin_trend"])) if "margin_trend" in out else ""] if s)
    return out


def record_vs_estimates(t):
    rows = [r for r in ((N.rj("state/earnings/history/%s.json" % t, {}) or {}).get("rows") or []) if r.get("est") is not None and r.get("eps") is not None]
    if not rows:
        return {"text": "No saved earnings history yet.", "n": 0}
    last = rows[-12:]
    beats = sum(1 for r in last if float(r["eps"]) > float(r["est"]))
    streak = 0
    for r in reversed(rows):
        if float(r["eps"]) > float(r["est"]):
            streak += 1
        else:
            break
    return {"n": len(last), "beats": beats, "streak": streak, "since": last[0]["date"],
            "text": "Beat the analysts' earnings estimate in %d of the last %d quarters (since %s); %d in a row now. Free sources give no history of the company's own guidance, so this is the nearest measure." % (beats, len(last), last[0]["date"], streak)}


def last_event(t, items):
    ev = [x for x in items if x["tickers"][0] == t and x["source"] == "sec" and (x.get("form") in ("10-Q", "10-K", "20-F", "6-K") or "2.02" in (x.get("items") or []))]
    return max([str(x.get("published") or x["first_seen"])[:10] for x in ev] or [None])


def screen_checks(t):
    for r in (N.rj("state/screen.json", {}) or {}).get("rows") or []:
        if (r.get("t") or r.get("ticker")) == t:
            return {"score": r.get("score"), "of": r.get("of"), "checks": [{"name": c.get("name"), "pass": c.get("pass"), "detail": c.get("detail")} for c in r.get("checks") or []],
                    "source": "state/screen.json (the seven checks)", "as_of": (N.rj("state/screen.json", {}) or {}).get("as_of")}
    return None


def forecaster(t):
    for c in (N.rj("state/actions.json", {}) or {}).get("candidates") or []:
        if c.get("t") == t and c.get("fc"):
            f = c["fc"]
            return {"text": "Forecaster: %d%% chance the take-profit comes before the stop, %d%% chance of beating the S&P 500 fund over %s; from %s past cases%s." % (
                round(100 * (f.get("tp_first") or 0)), round(100 * (f.get("beat_index") or 0)), f.get("beat_over") or "a year", "{:,}".format(f.get("cases") or 0),
                " (unproven live)" if f.get("unproven_live") else ""), "range": f.get("range"), "cases": f.get("cases")}
    return None


def upcoming(t):
    out = []
    for r in (N.rj("state/earnings.json", {}) or {}).get("calendar") or []:
        if r.get("ticker") == t and r.get("date", "") >= N.iso()[:10]:
            out.append({"date": r["date"], "what": "Results (%s)" % (r.get("time") or "time not given"), "source": "Nasdaq earnings calendar"})
    for e in (N.rj("state/news/macro.json", {}) or {}).get("events") or []:
        if e["date"] >= N.iso()[:10] and len([o for o in out if o.get("macro")]) < 2:
            out.append({"date": e["date"], "what": e["what"], "source": e["source"], "macro": True})
    return sorted(out, key=lambda x: x["date"])


def build(t, items, held, keeps, old, study, force_numbers=False):
    m, mdate = memo_of(t)
    mm = (m or {}).get("memo") or {}
    card = N.rj("research/cards/%s.json" % t, {}) or {}
    ev = last_event(t, items)
    due = []
    if not old:
        due.append("no file yet")
    if ev and ev > (old or {}).get("built_from_event", ""):
        due.append("new report or results filed on %s" % ev[:10])
    if mdate and mdate != (old or {}).get("memo_date"):
        due.append("new committee memo of %s" % mdate)
    news30 = [x for x in items if x["tickers"][0] == t and x["importance"] >= N.IMPORTANT and not x.get("dup_of")]
    if old and not due and len(news30) == len(old.get("news") or []):
        old["checked_at"] = N.iso()
        return old, (["narrative incomplete (%s)" % ", ".join(old["missing"])] if m and old.get("missing") else [])
    try:
        import memos
        val = memos.dcf_range(card.get("valuation"))
    except Exception:
        val = None
    a = card.get("analysts") or {}
    nb = (old or {}).get("numbers")
    if force_numbers or not nb or any(d.startswith("new report") or d == "no file yet" for d in due):
        nb = numbers(t, nb)
    st_earn = (study.get("earnings") or {}).get("5d") or {}
    f = {
        "ticker": t, "name": card.get("name") or (m or {}).get("name") or t, "updated": N.iso(), "held": t in held, "keep": t in keeps,
        "why_updated": due or ["news"], "memo_date": mdate, "built_from_event": ev or (old or {}).get("built_from_event", ""),
        "business": {"text": mm.get("business"), "source": "committee memo %s" % mdate if mdate else None},
        "segments": {"text": mm.get("segments"), "source": "committee memo %s" % mdate if mm.get("segments") else None},
        "competitors": {"text": mm.get("competitors") or mm.get("moat"), "source": "committee memo %s" % mdate if (mm.get("competitors") or mm.get("moat")) else None},
        "drivers": {"text": mm.get("drivers"), "source": "committee memo %s" % mdate if mm.get("drivers") else None},
        "management": {"text": mm.get("management"), "record": record_vs_estimates(t), "source": "committee memo %s; record from state/earnings/history" % mdate},
        "numbers": nb, "memo_numbers": mm.get("key_numbers"),
        "valuation": {"ours": val, "method": (card.get("valuation") or {}).get("method"), "as_of": (card.get("valuation") or {}).get("as_of"),
                      "analysts": {"low": a.get("target_low"), "mean": a.get("target_mean"), "high": a.get("target_high"), "count": a.get("brokers"), "rating": a.get("rating"), "source": a.get("source")},
                      "price": (card.get("quote") or {}).get("price")},
        "bull": {"text": mm.get("bull") or mm.get("moat"), "source": "committee memo %s" % mdate if (mm.get("bull") or mm.get("moat")) else None},
        "bear": {"items": mm.get("bear") or mm.get("risks"), "source": "committee memo %s" % mdate if (mm.get("bear") or mm.get("risks")) else None},
        "would_change": {"text": mm.get("would_change_view"), "source": "committee memo %s" % mdate if mm.get("would_change_view") else None},
        "checks": screen_checks(t), "forecast": forecaster(t),
        "event_study": {"text": ("Results days for the shares we follow: typical 5-day move %+.1f%% against the S&P 500 fund, range %+.1f%% to %+.1f%%, %s cases." % (
            100 * st_earn["median"], 100 * st_earn["p10"], 100 * st_earn["p90"], "{:,}".format(st_earn["n"]))) if st_earn.get("n") else "Not measured yet."},
        "dates": upcoming(t),
        "news": [{"id": x["id"], "title": x["title"], "url": x.get("url"), "type": x["type"], "first_seen": x["first_seen"], "importance": x["importance"], "thesis": x.get("thesis"),
                  "thesis_how": x.get("thesis_how")} for x in sorted(news30, key=lambda x: x["first_seen"], reverse=True)[:10]],
        "missing": [k for k, v in (("segments", mm.get("segments")), ("competitors", mm.get("competitors")), ("drivers", mm.get("drivers")), ("management", mm.get("management")), ("bull case", mm.get("bull")))
                    if not v] if m else ["the whole narrative: no committee memo yet"],
    }
    if m and f["missing"] and not due:
        due = ["narrative incomplete (%s)" % ", ".join(f["missing"])]
    if t in keeps:
        f["standing"] = "Your conviction holding, kept by your choice. News and the thesis are tracked as facts only; the system never suggests selling or trimming it."
    return f, [d for d in due if not d.startswith("new committee")]


def thesis_mark(x, f, b):
    """strengthens / weakens / no change, with how it was decided."""
    if x.get("thesis"):
        return x["thesis"], x.get("thesis_how")
    bear = json.dumps((f or {}).get("bear") or {})[:1500]
    bull = json.dumps((f or {}).get("bull") or {})[:800]
    if f and not f.get("missing", [""])[0].startswith("the whole"):
        a = N.ask(N.MAIN, "A company file's bull case: %s\nIts bear case: %s\nNews item: %s (%s, from %s)\nDoes this item strengthen or weaken the investment case, or leave it unchanged? "
                  "Answer with one word: strengthens, weakens or unchanged, then a dash and at most 20 words of reason." % (bull, bear, x["title"], x["type"], x["publisher"]), "thesis", b, 60)
        if a:
            w = a.strip().lower()
            k = "strengthens" if w.startswith("strength") else "weakens" if w.startswith("weak") else "no change"
            return k, "main model: " + a.strip()[:160]
    if x["source"] == "sec" and any(i in N.SEVERE for i in x.get("items") or []):
        return "weakens", "rule: a severe filing (%s)" % ", ".join(N.ITEM_TEXT.get(i, i) for i in x.get("items") if i in N.SEVERE)
    if x["reliability"] >= 0.7 and x["tone"] >= 0.25:
        return "strengthens", "rule: positive tone from a reliable source"
    if x["reliability"] >= 0.7 and x["tone"] <= -0.25:
        return "weakens", "rule: negative tone from a reliable source"
    return "no change", "rule: neutral, or from a low-reliability source"


def sector_briefs(held, quant, items):
    snap = N.rj("treasury/snapshot.json", {}) or {}
    nav = float(snap.get("nav") or 0) or 1.0
    by = {}
    for p in snap.get("positions") or []:
        s = str((quant.get(p.get("ticker")) or {}).get("sector") or "Fund or other")
        by.setdefault(s, []).append(p)
    out = []
    for s, ps in sorted(by.items(), key=lambda kv: -sum(float(p.get("market_value") or 0) for p in kv[1])):
        fund = N.SECTOR_FUND.get(s)
        fq = quant.get(fund) or {}
        news = [x for x in items if x["tickers"][0] in ("SECTOR:%s" % fund,) + tuple(p["ticker"] for p in ps) and x["importance"] >= 0.15 and not x.get("dup_of")][:4]
        out.append({"sector": s, "share": round(sum(float(p.get("market_value") or 0) for p in ps) / nav, 4), "holdings": [p["ticker"] for p in ps], "fund": fund,
                    "fund_1m": fq.get("ret_1M"), "fund_1y": fq.get("ret_1Y"),
                    "news": [{"title": x["title"], "url": x.get("url"), "type": x["type"]} for x in news],
                    "text": "%s: %.0f%% of the portfolio (%s).%s" % (s, 100 * sum(float(p.get("market_value") or 0) for p in ps) / nav, ", ".join(p["ticker"] for p in ps),
                                                               (" Sector fund %s: %+.1f%% over a month, %+.1f%% over a year." % (fund, 100 * fq["ret_1M"], 100 * fq["ret_1Y"])) if fq.get("ret_1M") is not None and fq.get("ret_1Y") is not None else "")})
    return out


# ---------------------------------------------------------------- the three books
def fee(usd):
    return max(FEE_MIN, FEE_RATE * usd)


def books(closes=None):
    """Paper books from 21 Nov 2026: ideas the system would buy with the news and files, ideas it would buy without them,
    and the S&P 500 fund, the same dollars on the same day, after fees both ways."""
    b = N.rj("state/news/books.json", {}) or {"start": BOOKS_START, "entries": []}
    a = N.rj("state/actions.json", {}) or {}
    day = N.iso()[:10]
    px = dict((t, (N.rj("research/cards/%s.json" % t, {}) or {}).get("quote", {}).get("price")) for t in set([e["t"] for e in b["entries"]] + ["SPY"]))
    tech = (N.rj("digests/latest.json", {}) or {}).get("technicals") or {}

    def price(t):
        p = (closes or {}).get(t) or (tech.get(t) or {}).get("price") or px.get(t) or (N.rj("research/cards/%s.json" % t, {}) or {}).get("quote", {}).get("price")
        return float(p) if p else None
    spy = price("SPY")
    picks = a.get("news_books") or {}
    if day >= BOOKS_START and spy:
        for book in ("with", "without"):
            for t in picks.get(book) or []:
                if not any(e["t"] == t and e["book"] == book and e["day"] == day for e in b["entries"]) and not any(e["t"] == t and e["book"] == book and e.get("open") for e in b["entries"]):
                    p0 = price(t)
                    if p0:
                        b["entries"].append({"book": book, "t": t, "day": day, "p0": p0, "spy0": spy, "open": True})
    res = {}
    for book in ("with", "without"):
        es = [e for e in b["entries"] if e["book"] == book]
        rs, idx = [], []
        for e in es:
            p1 = price(e["t"])
            if not p1 or not spy:
                continue
            g = STAKE * p1 / e["p0"] - STAKE - fee(STAKE) - fee(STAKE * p1 / e["p0"])
            s = STAKE * spy / e["spy0"] - STAKE - fee(STAKE) - fee(STAKE * spy / e["spy0"])
            rs.append(g / STAKE)
            idx.append(s / STAKE)
            e["now"] = {"idea": round(g / STAKE, 4), "spy": round(s / STAKE, 4), "at": day}
        n = len(rs)
        res[book] = {"cases": n, "avg": round(sum(rs) / n, 4) if n else None, "spy": round(sum(idx) / n, 4) if n else None,
                     "vs_spy": round((sum(rs) - sum(idx)) / n, 4) if n else None, "label": "too few cases" if n < FEW else "enough cases to read"}
    days = (datetime.date.fromisoformat(day) - datetime.date.fromisoformat(BOOKS_START)).days
    n = min(res["with"]["cases"], res["without"]["cases"])
    if n >= VERDICT_CASES or days >= VERDICT_DAYS:
        w, wo = res["with"].get("vs_spy"), res["without"].get("vs_spy")
        earns = w is not None and wo is not None and w > wo
        verdict = ("After %d days and %d cases the news side %s: with it %+.1f%%, without it %+.1f%% against the S&P 500 fund after fees. %s" % (
            days, n, "earns its cost" if earns else "does NOT earn its cost", 100 * (w or 0), 100 * (wo or 0),
            "Keep it." if earns else "Suggestion: cut the news side back to SEC filings and the event study only, and stop the model steps."))
    else:
        verdict = "Verdict due at %d cases or on %s, whichever comes first; %d days and %d cases so far." % (VERDICT_CASES, (datetime.date.fromisoformat(BOOKS_START) + datetime.timedelta(days=VERDICT_DAYS)).isoformat(), days, n)
    b.update({"as_of": N.iso(), "books": res, "verdict": verdict, "stake": STAKE,
              "method": "Each idea the action list would buy on a day goes into its book once, with $%.0f at that day's price; the S&P 500 fund gets the same $%.0f the same day. Fees 0.25%% (at least $1) on the way in and out. Results to today's price; paper only." % (STAKE, STAKE)})
    N.wj("state/news/books.json", b)
    return b


# ---------------------------------------------------------------- run
def run(items=None):
    items = items if items is not None else ((N.rj("state/news/items.json", {}) or {}).get("items") or [])
    names, held, keeps = N.universe()
    quant = (N.rj("state/quant.json", {}) or {}).get("assets") or {}
    study = (N.rj("state/news/event_study.json", {}) or {}).get("types") or {}
    b = N.budget()
    files, due = {}, []
    # the thesis tracker first, so each file carries today's marks
    old_files = dict((t, N.rj("state/files/%s.json" % t)) for t in names)
    log = N.rj("state/files/thesis_log.json", {}) or {"marks": []}
    for x in items:
        if x["importance"] >= N.IMPORTANT and not x.get("dup_of") and x["tickers"][0] in names and not x.get("thesis"):
            x["thesis"], x["thesis_how"] = thesis_mark(x, old_files.get(x["tickers"][0]), b)
            log["marks"].append({"id": x["id"], "t": x["tickers"][0], "title": x["title"], "url": x.get("url"), "mark": x["thesis"], "how": x["thesis_how"], "at": N.iso()})
    cut = (N.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    log["marks"] = [m for m in log["marks"] if m["at"][:10] >= cut]
    for t in names:
        if t in ("SPY", "VOO", "IVV"):
            continue
        f, why = build(t, items, held, keeps, old_files.get(t), study)
        files[t] = f
        N.wj("state/files/%s.json" % t, f)
        if why:
            due.append({"ticker": t, "why": "; ".join(why), "held": t in held})
    # broken thesis: two weakens in 30 days, or one severe filing, on a holding (never on a position you chose to keep)
    wcut = (N.now() - datetime.timedelta(days=WEAK_DAYS)).strftime("%Y-%m-%d")
    broken = []
    for t in held:
        w = [m for m in log["marks"] if m["t"] == t and m["mark"] == "weakens" and m["at"][:10] >= wcut]
        severe = [m for m in w if "severe" in str(m.get("how"))]
        if (len(w) >= WEAK_COUNT or severe) and t not in keeps:
            broken.append({"ticker": t, "why": "%d items weakened the thesis in %d days%s" % (len(w), WEAK_DAYS, " (one a severe filing)" if severe else ""), "items": w[-3:]})
    log.update({"as_of": N.iso(), "broken": broken, "rule": "Broken: two items marked weakens within %d days, or one severe filing, on a holding. Positions you chose to keep are tracked as facts only." % WEAK_DAYS})
    N.wj("state/files/thesis_log.json", log)
    N.wj("state/files/due.json", {"as_of": N.iso(), "due": due, "rule": "A file's narrative is due for the committee when a new report, results or a severe filing arrived since its memo."})
    N.wj("state/files/sectors.json", {"as_of": N.iso(), "briefs": sector_briefs(held, quant, items), "method": "Holdings grouped by sector from state/quant.json; sector fund moves from the same file; news from the news desk."})
    N.wj("state/files/index.json", {"as_of": N.iso(), "files": [{"ticker": t, "name": f.get("name"), "held": f.get("held"), "keep": f.get("keep"), "updated": f.get("updated"),
                                                                "memo_date": f.get("memo_date"), "missing": f.get("missing"), "news": len(f.get("news") or [])} for t, f in sorted(files.items())],
                                     "broken": broken, "due": due})
    N.wj("state/news/budget.json", b)
    # write the marks back onto the items
    keepi = N.rj("state/news/items.json", {}) or {}
    marks = dict((x["id"], (x.get("thesis"), x.get("thesis_how"))) for x in items if x.get("thesis"))
    for x in keepi.get("items") or []:
        if x["id"] in marks:
            x["thesis"], x["thesis_how"] = marks[x["id"]]
    if keepi:
        N.wj("state/news/items.json", keepi)
    books()
    print("files ok: %d files, %d due for the committee, %d broken theses" % (len(files), len(due), len(broken)))
    return files


def drivers(t, n=3):
    """The facts and news that drove a card, with links: for actions.py."""
    f = N.rj("state/files/%s.json" % t, {}) or {}
    out = []
    v = (f.get("valuation") or {})
    ours = v.get("ours") or {}
    if ours.get("base") and v.get("price"):
        out.append({"text": "Our cash-flow value $%.2f against the price $%.2f (%s)" % (float(ours["base"]), float(v["price"]), "range $%.2f to $%.2f" % (float(ours.get("low") or 0), float(ours.get("high") or 0)) if ours.get("low") else "model estimate"),
                    "url": "research/cards/%s.json" % t})
    for x in f.get("news") or []:
        if x.get("thesis") in ("strengthens", "weakens") and len(out) < n:
            out.append({"text": "%s (%s, thesis %s)" % (x["title"], x["first_seen"][:10], x["thesis"]), "url": x.get("url")})
    c = f.get("checks") or {}
    if c.get("score") is not None and len(out) < n:
        out.append({"text": "Passes %s of %s checks: %s" % (c["score"], c.get("of"), ", ".join(k["name"] for k in c.get("checks") or [] if k.get("pass"))[:160]), "url": "state/screen.json"})
    rec = (f.get("management") or {}).get("record") or {}
    if rec.get("n") and len(out) < n:
        out.append({"text": rec["text"], "url": "state/earnings/history/%s.json" % t})
    return out[:n]


def news_block_for(t):
    """Recent important negative news or a weakened thesis: the reasons the news side holds a buy back."""
    f = N.rj("state/files/%s.json" % t, {}) or {}
    cut = (N.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    for x in f.get("news") or []:
        if x["first_seen"][:10] >= cut and x.get("thesis") == "weakens":
            return "news weakened the thesis on %s: %s" % (x["first_seen"][:10], x["title"][:100])
    return None


if __name__ == "__main__":
    run()
