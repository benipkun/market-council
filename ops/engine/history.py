# Market Council back-checks and pattern matches.
# Part A tests every scorecard check against as many years of history as the free sources give: what a
# share did over the next 1, 3, 6 and 12 months after the check passed, after it failed, and what the
# S&P 500 fund did over the same months, on two separate halves of the history.
# Part B describes today's setup of a share, and of the market, in numbers and looks for past days that
# resembled it, then shows what followed.
# Plain arithmetic on public data (CNBC prices, Nasdaq statements and earnings calendar, OpenInsider
# filings). Nothing here is fitted to make the past look good, and nothing places an order.
import bisect
import concurrent.futures
import datetime
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request

import numpy as np

import engine as E
import research as RS

NL = chr(10)
HDIR = os.environ.get("MC_HIST", os.path.join(E.ROOT, ".cache", "history"))
BUDGET = int(os.environ.get("MC_HIST_BUDGET", str(55 * 60)))   # seconds for fetching; the sums need about a minute more
COST = 0.005                      # buy and sell at 0.25% each: half a percent off every result
HZ = (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252))
MAIN, MAIN_MONTHS = "6m", 6       # the horizon the "works" verdict is read on, fixed before any result was seen
MIN_YEARS = 6                     # a check needs at least this much history, so each half has three years
MIN_CASES = 200                   # and at least this many passes and fails in each half
EARN_START = "2009-01-01"
RADIUS = 0.25                     # a past week of a share "looked the same" when it is within a quarter of a standard deviation on average
RADIUS_MARKET = 0.5               # the market is one series, not hundreds, so its net is wider: half a standard deviation
GAP = 63                          # matches in one share closer than three months apart count once
MATCH_CAP = 300
STALE_RESULTS = 130               # trading days after which the last earnings report no longer counts
LONG = ["trend", "momentum", "drift", "insiders"]
ORDER = ["value", "quality", "momentum", "trend", "insiders", "holders", "drift"]
STARTS = ("2000-01-01", "2006-01-01", "2012-01-01", "2017-01-01", "2021-01-01", "2023-01-01")

CHECKS = {
    "value": {"name": "Price at or below our fair value",
              "what": "Compares the share price with our own estimate of what the business is worth from its future cash flows.",
              "why": "Paying less than a business is worth leaves room for error; paying more needs everything to go right.",
              "rule": "Pass when the price is at or under our fair value per share. Fair value = five years of forecast free cash flow plus a terminal value, discounted at the risk-free rate plus beta times 5% (kept between 7% and 12%), less net debt, divided by the share count. Growth starts at the recent pace (2% to 25%) and fades to 4%; terminal growth 2.5%.",
              "source": "Nasdaq annual company statements; share count from market value / price; prices from CNBC.",
              "rebuilt": "Approximate rebuild: each fiscal year's statements are taken as public 90 days after the year-end; today's share count and risk-free rate are used; beta is measured over the year before. The free statements go back four years, which lets only the last two fiscal years be valued."},
    "quality": {"name": "Operating margin of 8% or more",
                "what": "Operating profit as a share of sales in the latest full year.",
                "why": "A business that keeps at least 8 cents of every sales dollar before interest and tax can absorb a bad year; a thin margin leaves no cushion.",
                "rule": "Pass when operating income divided by total revenue in the latest annual statement is 8% or more.",
                "source": "Nasdaq annual company statements.",
                "rebuilt": "Exact rule. Each fiscal year's statements are taken as public 90 days after the year-end. The free statements go back four fiscal years only."},
    "momentum": {"name": "Beat the S&P 500 fund over 12 months (latest month left out)",
                 "what": "The share's price change from 12 months ago to one month ago, against the S&P 500 fund's change over the same days.",
                 "why": "Shares that outran the market over the past year have tended to keep doing so for some months. The latest month is left out because very recent moves tend to reverse.",
                 "rule": "Pass when (close 21 trading days ago / close 252 trading days ago) is higher for the share than for the fund SPY.",
                 "source": "CNBC daily closes, adjusted for splits; dividends are not included, for the share and the fund alike.",
                 "rebuilt": "Exact rule."},
    "trend": {"name": "Price above its 200-day average",
              "what": "The latest close against the average close of the last 200 trading days.",
              "why": "A share above its long average is in an upward trend, and most deep falls happen below it. On the scorecard this is the one check that must pass.",
              "rule": "Pass when the latest close is above the mean of the last 200 closes.",
              "source": "CNBC daily closes.",
              "rebuilt": "Exact rule."},
    "insiders": {"name": "Insiders bought more than they sold in 90 days",
                 "what": "Open-market purchases and sales by the company's own directors and officers, from their SEC filings.",
                 "why": "Insiders sell for many reasons, but they buy with their own money for one: they expect the price to rise.",
                 "rule": "Pass when there is at least one open-market purchase traded in the last 90 days and the dollar value bought is larger than the value sold.",
                 "source": "OpenInsider (SEC Form 4, with trade date and filing date). Foreign companies file none, so the check is unknown for them.",
                 "rebuilt": "Exact rule, counted from the day each filing became public. For the heaviest sellers the source lists only the latest 1,000 filings, so their history starts later."},
    "holders": {"name": "Two or more well-known investors hold it and one added lately",
                "what": "How many of about 80 well-known long-term investors hold the share, and whether any of them bought or added in the latest quarter.",
                "why": "Several careful investors reaching the same share independently is a second opinion on the business.",
                "rule": "Pass when at least two of them hold it and at least one shows a purchase or an addition in the latest quarterly filing.",
                "source": "Dataroma (13F filings: quarterly, published up to 45 days after the quarter ends).",
                "rebuilt": None},
    "drift": {"name": "Last results beat forecasts and the price rose over five days",
              "what": "Whether the latest quarterly earnings per share beat the analysts' forecast, and whether the price was higher five trading days after the report than the day before it.",
              "why": "After a good surprise that the market also liked, prices have tended to keep drifting the same way for weeks.",
              "rule": "Pass when the earnings surprise is above zero and (close four trading days after the report day / close the day before it) is above 1.",
              "source": "Nasdaq earnings calendar (reported and forecast earnings per share); CNBC prices.",
              "rebuilt": "Exact rule; a report older than about six months no longer counts. Only companies still listed today appear in the calendar."}}

FEATS = [("d50", "Price against its 50-day average"), ("d200", "Price against its 200-day average"), ("r21", "Change over one month"),
         ("r63", "Change over three months"), ("dd", "Distance below its 12-month high"), ("vol", "20-day volatility, as a yearly rate"),
         ("vix", "Market fear gauge (VIX)")]
MFEATS = [("d200", "S&P 500 fund against its 200-day average"), ("r63", "Change over three months"), ("dd", "Distance below its 12-month high"),
          ("vol", "20-day volatility, as a yearly rate"), ("vix", "Market fear gauge (VIX)")]


def r4(x, n=4):
    return E.rd(x, n)


def load(name, default=None):
    try:
        with open(os.path.join(HDIR, name), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save(name, obj):
    os.makedirs(HDIR, exist_ok=True)
    with open(os.path.join(HDIR, name), "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=True))


def ppath(sym):
    return os.path.join(HDIR, "p_" + re.sub("[^A-Za-z0-9]", "_", sym) + ".csv")


def read_rows(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [(a, float(b)) for a, b in (ln.split(",")[:2] for ln in f.read().split(NL) if "," in ln)]
    except Exception:
        return []


def write_rows(path, rows):
    os.makedirs(HDIR, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(NL.join(d + "," + ("%.4f" % v) for d, v in rows) + NL)


def epoch(day):
    return datetime.datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp()


def age_days(stamp):
    try:
        return (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.strptime(str(stamp)[:10], "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)).days
    except Exception:
        return 9999


# ---------------------------------------------------------------- fetching (skipped when offline)
def long_prices(sym):
    old = read_rows(ppath(sym))
    if E.OFFLINE:
        return old
    if old and age_days(old[-1][0]) <= 45:
        try:
            new = E.fetch_cnbc(sym, time.time() - 150 * 86400)
            m = dict(old)
            both = [(d, v) for d, v in new if d in m]
            # the same adjustment basis on both sides (no split since the saved copy): only then can the tail be joined on
            if both and all(abs(v / m[d] - 1) < 0.004 for d, v in both[:8]):
                m.update(dict(new))
                rows = sorted(m.items())
                write_rows(ppath(sym), rows)
                return rows
        except Exception:
            return old
    rows = []
    for start in STARTS:
        try:
            rows = E.fetch_cnbc(sym, epoch(start))
        except Exception:
            rows = []
        if len(rows) > 250:
            break
    if len(rows) > 250:
        write_rows(ppath(sym), rows)
        return rows
    return old


def text_get(url, cap=4000000, timeout=40):
    req = urllib.request.Request(url, headers=RS.HEAD)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(cap).decode("utf-8", "replace")


def fetch_earnings(cal, want, deadline, limits):
    data = load("earnings.json") or {"from": None, "through": None, "events": {}, "skipped": []}
    if E.OFFLINE:
        return data
    ev, days = data["events"], [d for d in cal if d >= EARN_START]

    def grab(d):
        for attempt in (0, 1):
            try:
                rows = ((json.loads(text_get(RS.NQ + "calendar/earnings?date=" + d)).get("data") or {}).get("rows")) or []
                return d, [(str(x.get("symbol") or ""), RS.num(x.get("surprise"))) for x in rows]
            except Exception:
                time.sleep(1.0)
        return d, None

    def keep(d, got):
        if got is None:
            data["skipped"] = (data.get("skipped") or []) + [d]
            return False
        for s, sur in got:
            if s in want:
                ev.setdefault(s, {})[d] = sur
        return True
    # the newest days first, one at a time; the last five are read again because surprises arrive late
    newer = []
    if data["through"]:
        newer = days[max(0, len(days) - len([d for d in days if d > data["through"]]) - 5):]
    down = False
    for d in newer:
        if time.time() > deadline:
            break
        if keep(*grab(d)):
            data["through"] = max(data["through"], d)
        time.sleep(0.05)
    # then back through the years, a few requests at a time: the source answers slowly, one day per request
    older = [d for d in reversed(days) if data["from"] is None or d < data["from"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for i in range(0, len(older), 50):
            if time.time() > deadline or down:
                break
            chunk = older[i:i + 50]
            ok = [keep(d, got) for d, got in pool.map(grab, chunk)]
            if not any(ok):
                down = True
                break
            data["from"] = chunk[-1]
            data["through"] = data["through"] or chunk[0]
            if (i // 50) % 6 == 5:
                save("earnings.json", data)
    if down:
        limits.append("Earnings history: the source stopped answering; it is complete from %s to %s and continues on the next run." % (data["from"], data["through"]))
    elif data["from"] and data["from"] > days[0]:
        limits.append("Earnings history: fetched from %s so far (time budget); older years are added on the next runs, back to %s." % (data["from"], EARN_START[:4]))
    save("earnings.json", data)
    return data

def fetch_insiders(tickers, deadline, limits):
    data = load("insiders.json") or {"as_of": None, "by": {}, "trunc": {}}
    if E.OFFLINE:
        return data
    at, misses = data.setdefault("at", {}), 0
    for t in tickers:
        if t in data["by"] and age_days(at.get(t)) <= 6:
            continue
        if time.time() > deadline or misses >= 8:
            limits.append("Insider history: fetched for %d of %d US shares (%s)." % (len(data["by"]), len(tickers), "the source stopped answering" if misses >= 8 else "time budget"))
            break
        try:
            html = RS.get("http://openinsider.com/screener?s=" + urllib.parse.quote(t) + "&fd=0&cnt=1000", as_json=False)
        except Exception:
            misses += 1
            continue
        rows = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            c = [re.sub(r"<[^>]+>", "", x).replace("&nbsp;", " ").strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(c) >= 12 and re.match(r"^\d{4}-\d{2}-\d{2}", c[1]) and re.match(r"^\d{4}-\d{2}-\d{2}$", c[2]) and c[6][:1] in ("P", "S"):
                rows.append([c[1][:10], c[2], c[6][:1], abs(RS.num(c[11]) or 0.0)])
        data["by"][t], at[t], misses = rows, E.now_iso(), 0
        if len(rows) >= 990:
            data["trunc"][t] = min(x[0] for x in rows)
        time.sleep(0.6)
    data["as_of"] = max(at.values()) if at else data.get("as_of")
    save("insiders.json", data)
    return data


def fetch_fin(tickers, deadline, limits):
    data = load("fin.json") or {"as_of": None, "by": {}}
    if E.OFFLINE:
        return data
    at, misses = data.setdefault("at", {}), 0
    for t in tickers:
        if t in data["by"] and age_days(at.get(t)) <= 6:
            continue
        if time.time() > deadline or misses >= 10:
            limits.append("Statements: fetched for %d of %d shares (%s)." % (len(data["by"]), len(tickers), "the source stopped answering" if misses >= 10 else "time budget"))
            break
        fin = RS.nq("company/" + t + "/financials?frequency=1")
        if fin:
            data["by"][t], at[t], misses = fin, E.now_iso(), 0
        else:
            misses += 1
    data["as_of"] = max(at.values()) if at else data.get("as_of")
    save("fin.json", data)
    return data


def fetch_cape(limits):
    data = load("cape.json") or {"as_of": None, "rows": []}
    if E.OFFLINE or age_days(data.get("as_of")) <= 2:
        return data
    mon = {m: i + 1 for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    try:
        html = text_get("https://www.multpl.com/shiller-pe/table/by-month", 2000000)
        seen, rows = set(), []
        for m in re.finditer(r"<td[^>]*>\s*([A-Z][a-z]{2}) (\d{1,2}), (\d{4})\s*</td>\s*<td[^>]*>(?:\s|&#x2002;|<[^>]+>)*([\d.]+)", html):
            ym = "%s-%02d" % (m.group(3), mon.get(m.group(1), 0))
            if ym not in seen:
                seen.add(ym)
                rows.append([ym, float(m.group(4))])
        if len(rows) > 600:
            data = {"as_of": E.now_iso(), "rows": sorted(rows)}
            save("cape.json", data)
    except Exception as e:
        limits.append("Market valuation: the table of the S&P 500's ten-year price-to-earnings ratio did not load (%s); the saved copy is used if there is one." % str(e)[:60])
    return data


# ---------------------------------------------------------------- rolling sums
def roll_mean(x, w):
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def roll_max(x, w):
    out = np.full(len(x), np.nan)
    if len(x) >= w:
        out[w - 1:] = np.lib.stride_tricks.sliding_window_view(x, w).max(axis=1)
    return out


def roll_vol(x, w):
    out = np.full(len(x), np.nan)
    if len(x) > w:
        r = x[1:] / x[:-1] - 1
        c1, c2 = np.cumsum(np.insert(r, 0, 0.0)), np.cumsum(np.insert(r * r, 0, 0.0))
        m = (c1[w:] - c1[:-w]) / w
        v = np.maximum((c2[w:] - c2[:-w]) / w - m * m, 0.0) * w / (w - 1)
        out[w:] = np.sqrt(v) * math.sqrt(252)
    return out


def lag_ratio(x, near, far):
    out = np.full(len(x), np.nan)
    if len(x) > far:
        out[far:] = x[far - near:len(x) - near] / x[:len(x) - far] - 1
    return out


def align(rows, idx, n):
    arr = np.full(n, np.nan)
    for d, v in rows:
        k = idx.get(d)
        if k is not None and v > 0:
            arr[k] = v
    ok = np.where(~np.isnan(arr))[0]
    if len(ok) < 300:
        return None
    a, b = int(ok[0]), int(ok[-1]) + 1
    seg = arr[a:b]
    bad = np.isnan(seg)
    if bad.any():   # a missing day inside the series carries the last price
        last = np.where(~bad, np.arange(len(seg)), 0)
        np.maximum.accumulate(last, out=last)
        seg = seg[last]
    return a, b, seg


def state(cond, known):
    out = np.full(len(cond), -1, dtype=np.int8)
    out[known & cond] = 1
    out[known & ~cond] = 0
    return out


def stats(v):
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return None
    return {"n": int(len(v)), "avg": r4(np.mean(v)), "med": r4(np.median(v)), "win": r4(np.mean(v > 0)), "worst": r4(np.min(v)), "best": r4(np.max(v))}


def shift_fin(fin, k):
    # the same statements as they stood k fiscal years ago: the k newest columns are dropped
    out = {}
    for name in ("incomeStatementTable", "balanceSheetTable", "cashFlowTable"):
        t = (fin or {}).get(name)
        if not t:
            continue
        hk = list((t.get("headers") or {}).keys())
        keep = hk[:1] + hk[1 + k:]
        out[name] = {"headers": {h: t["headers"][h] for h in keep},
                     "rows": [{h: row.get(h) for h in keep} for row in (t.get("rows") or [])]}
    return out


# ---------------------------------------------------------------- one share: features and the state of every check on every day
def build(t, meta, rows, ctx):
    al = align(rows, ctx["idx"], ctx["n"])
    if al is None:
        return None
    a, b, x = al
    m, cal, spy = len(x), ctx["cal"], ctx["spy"]
    j = np.arange(m)
    sma50, sma200 = roll_mean(x, 50), roll_mean(x, 200)
    mom = lag_ratio(x, 21, 252)
    f = {"d50": x / sma50 - 1, "d200": x / sma200 - 1, "r21": lag_ratio(x, 0, 21), "r63": lag_ratio(x, 0, 63), "dd": x / roll_max(x, 252) - 1,
         "vol": roll_vol(x, 20), "vix": ctx["vix"][a:b]}
    old = j >= 260
    st = {"trend": state(x > np.nan_to_num(sma200, nan=np.inf), old), "momentum": state(np.nan_to_num(mom, nan=-9.0) > ctx["spy_mom"][a:b], old)}
    # earnings drift: the state set by each report holds from the fifth day after it until the next report, or until it is stale
    dr = np.full(m, -1, dtype=np.int8)
    evs = (ctx["earn"].get("events") or {}).get(t) or {}
    evs = sorted(evs.items()) if isinstance(evs, dict) else sorted((d, sur) for d, sur in evs)
    marks, surp, react = [], np.full(m, np.nan), np.full(m, np.nan)
    for d, sur in evs:
        j0 = bisect.bisect_left(cal, d) - a
        if 1 <= j0 and j0 + 4 < m:
            mv = x[j0 + 4] / x[j0 - 1] - 1
            marks.append((j0 + 4, -1 if sur is None else int(sur > 0 and mv > 0), sur, mv))
    for i, (k, s, sur, mv) in enumerate(marks):
        end = min(marks[i + 1][0] if i + 1 < len(marks) else m, k + STALE_RESULTS, m)
        dr[k:end] = s
        react[k:end] = mv
        if sur is not None:
            surp[k:end] = max(-100.0, min(100.0, float(sur)))
    st["drift"] = dr
    # insiders: every filing counts from the day it was filed until 90 days after the trade
    ins, insnet = np.full(m, -1, dtype=np.int8), np.full(m, np.nan)
    fl = (ctx["ins"].get("by") or {}).get(t)
    if fl is not None and meta.get("region") != "Europe":
        nb, bv, sv = np.zeros(m + 1), np.zeros(m + 1), np.zeros(m + 1)
        for filed, traded, typ, val in fl:
            k0 = bisect.bisect_left(cal, filed) - a
            try:
                k1 = bisect.bisect_right(cal, (datetime.date.fromisoformat(traded) + datetime.timedelta(days=90)).isoformat()) - a
            except Exception:
                continue
            k0, k1 = max(k0, 0), min(k1, m)
            if k1 > k0:
                if typ == "P":
                    nb[k0] += 1
                    nb[k1] -= 1
                    bv[k0] += val
                    bv[k1] -= val
                else:
                    sv[k0] += val
                    sv[k1] -= val
        nb, bv, sv = np.cumsum(nb)[:m], np.cumsum(bv)[:m], np.cumsum(sv)[:m]
        first = (ctx["ins"].get("trunc") or {}).get(t) or "2004-01-01"
        known = old & (j >= bisect.bisect_left(cal, first) - a + 63)
        ins = state((nb > 0.5) & (bv > sv + 1e-9), known)
        insnet = np.where(known, np.sign(bv - sv), np.nan)
    st["insiders"] = ins
    # quality and value from the annual statements, each taken as public 90 days after its year-end
    q, v = np.full(m, -1, dtype=np.int8), np.full(m, -1, dtype=np.int8)
    fin = (ctx["fin"].get("by") or {}).get(t)
    if fin:
        try:
            inc, years = RS.table(fin.get("incomeStatementTable"))
            rev, op = inc.get("Total Revenue") or [], inc.get("Operating Income") or []
            pub = []
            for k, y in enumerate(years):
                if y:
                    pub.append((bisect.bisect_left(cal, (datetime.date.fromisoformat(y) + datetime.timedelta(days=90)).isoformat()) - a, k))
            pub.sort()
            for i, (k0, k) in enumerate(pub):
                end = pub[i + 1][0] if i + 1 < len(pub) else m
                k0, end = max(k0, 0), min(end, m)
                if end <= k0:
                    continue
                if k < len(rev) and k < len(op) and rev[k] and op[k] is not None:
                    q[k0:end] = int(op[k] / rev[k] >= 0.08)
                if k <= 1 and meta.get("cap") and meta.get("region") != "Europe":
                    w0 = max(k0 - 252, 1)
                    ra, rb = x[w0:k0 + 1], spy[a + w0:a + k0 + 1]
                    beta = None
                    if len(ra) > 120:
                        da, db = ra[1:] / ra[:-1] - 1, rb[1:] / rb[:-1] - 1
                        beta = float(np.cov(da, db)[0, 1] / np.var(db)) if np.var(db) > 0 else None
                    val = RS.dcf(t, shift_fin(fin, k), float(x[min(k0, m - 1)]), meta["cap"] / float(x[-1]) / 1000.0, beta, ctx["rf"],
                                 {"name": t, "sector": meta.get("sector_dcf"), "country": meta.get("country") or "United States", "cls": "Equity"}, save=False)
                    fair = val.get("fair_value_per_share")
                    if fair and fair > 0:
                        v[k0:end] = (x[k0:end] <= fair).astype(np.int8)
        except Exception:
            pass
    q[~old], v[~old] = -1, -1
    st["quality"], st["value"], st["holders"] = q, v, np.full(m, -1, dtype=np.int8)
    raw = {"momx": mom - ctx["spy_mom"][a:b], "surp": surp, "react": react, "insnet": insnet}
    return {"t": t, "a": a, "b": b, "x": x, "f": f, "st": st, "raw": raw, "sector": meta.get("sector") or "", "region": meta.get("region") or "US"}


def fwd(x, js, h):
    out = np.full(len(js), np.nan)
    ok = js + h < len(x)
    out[ok] = x[js[ok] + h] / x[js[ok]] - 1 - COST
    return out


# ---------------------------------------------------------------- part A: the track record of every check
def table_for(S, M, F, G):
    rows = {}
    for h, _ in HZ:
        okp, okf = (S == 1) & ~np.isnan(F[h]), (S == 0) & ~np.isnan(F[h])
        rows[h] = {"pass": stats(F[h][okp]), "fail": stats(F[h][okf]),
                   "spy_pass": r4(np.mean(G[h][okp])) if okp.any() else None, "spy_fail": r4(np.mean(G[h][okf])) if okf.any() else None}
    return rows


def halves_for(S, M, F, G, months):
    ok = ~np.isnan(F[MAIN]) & (S >= 0)
    if not ok.any():
        return []
    m0, m1 = int(M[ok].min()), int(M[ok].max())
    mid = (m0 + m1) // 2
    out = []
    for lo, hi in ((m0, mid - MAIN_MONTHS), (mid + 1, m1)):
        sel = ok & (M >= lo) & (M <= hi)
        p, f = sel & (S == 1), sel & (S == 0)
        out.append({"from": months[lo][:7], "to": months[max(hi, lo)][:7], "n_pass": int(p.sum()), "n_fail": int(f.sum()),
                    "pass": r4(np.mean(F[MAIN][p])) if p.any() else None, "fail": r4(np.mean(F[MAIN][f])) if f.any() else None,
                    "spy": r4(np.mean(G[MAIN][p])) if p.any() else None})
    return out


def verdict(years, halves):
    if not halves or years is None:
        return "unproven", "No free history exists for this check, so it could not be tested."
    if years < MIN_YEARS:
        return "unproven", "Only %.1f years of free history: too short to test on two separate halves of at least three years each." % years
    if any(h["n_pass"] < MIN_CASES or h["n_fail"] < MIN_CASES for h in halves):
        return "unproven", "Too few cases in one half (%s passes and %s fails needed in each)." % (MIN_CASES, MIN_CASES)
    beat_fail = [h["pass"] > h["fail"] for h in halves]
    beat_spy = [h["pass"] > h["spy"] for h in halves]
    if all(beat_fail) and all(beat_spy):
        return "working", "In both halves, shares that passed did better over six months than shares that failed and than the S&P 500 fund."
    bits = []
    for i, h in enumerate(halves):
        bits.append("%s half: passes %s, fails %s, fund %s" % ("first" if i == 0 else "second", E.pc(h["pass"]), E.pc(h["fail"]), E.pc(h["spy"])))
    return "unproven", "It did not hold in both halves over six months (" + "; ".join(bits) + ")."


def backcheck(shares, ctx):
    months, me = ctx["months"], ctx["me"]
    acc = {c: {"S": [], "M": [], "F": {h: [] for h, _ in HZ}, "G": {h: [] for h, _ in HZ}, "n": 0} for c in ORDER + ["combo"]}
    for s in shares:
        js = np.array([k - s["a"] for k in me if s["a"] + 260 <= k < s["b"]], dtype=int)
        if len(js) == 0:
            continue
        mi = np.array([i for i, k in enumerate(me) if s["a"] + 260 <= k < s["b"]], dtype=int)
        F = {h: fwd(s["x"], js, n) for h, n in HZ}
        G = {h: ctx["spy_f"][h][s["a"] + js] for h, _ in HZ}
        sts = dict((c, s["st"][c][js]) for c in ORDER)
        allk = np.all(np.stack([sts[c] for c in LONG]) >= 0, axis=0)
        sts["combo"] = np.where(allk, np.sum(np.stack([sts[c] for c in LONG]), axis=0), -1)
        for c in ORDER + ["combo"]:
            k = sts[c] >= 0
            if k.any():
                a = acc[c]
                a["S"].append(sts[c][k])
                a["M"].append(mi[k])
                a["n"] += 1
                for h, _ in HZ:
                    a["F"][h].append(F[h][k])
                    a["G"][h].append(G[h][k])
    out = {}
    for c in ORDER + ["combo"]:
        a = acc[c]
        if not a["S"]:
            out[c] = None
            continue
        S, M = np.concatenate(a["S"]), np.concatenate(a["M"])
        F = {h: np.concatenate(a["F"][h]) for h, _ in HZ}
        G = {h: np.concatenate(a["G"][h]) for h, _ in HZ}
        hist = {"from": months[int(M.min())][:7], "to": months[int(M.max())][:7], "years": r4((int(M.max()) - int(M.min()) + 1) / 12.0, 1), "shares": a["n"], "cases": int(len(S))}
        if c == "combo":
            by = []
            for k in range(len(LONG) + 1):
                Sk = np.where(S == k, 1, 0).astype(np.int8)
                by.append({"k": k, "rows": {h: {"at": stats(F[h][S == k]), "spy": r4(np.mean(G[h][(S == k) & ~np.isnan(F[h])])) if ((S == k) & ~np.isnan(F[h])).any() else None} for h, _ in HZ},
                           "halves": [{"from": hv["from"], "to": hv["to"], "n": hv["n_pass"], "avg": hv["pass"], "spy": hv["spy"]} for hv in halves_for(Sk, M, F, G, months)]})
            out[c] = {"history": hist, "by_k": by}
        else:
            hv = halves_for(S, M, F, G, months)
            v, why = verdict(hist["years"], hv)
            out[c] = {"history": hist, "rows": table_for(S, M, F, G), "halves": hv, "verdict": v, "verdict_why": why}
    return out


# ---------------------------------------------------------------- part B: past days that looked like today
def grid_of(s, ctx):
    js = np.arange(260 + (4 - (s["a"] + 260) % 5) % 5, len(s["x"]), 5)   # the same weekly days for every share
    X = np.stack([s["f"][k][js] for k, _ in FEATS], axis=1)
    return js, X


def summarise(rs, own, label, since, base, closest, same=None):
    six = rs.get(MAIN) or {}
    n = max([(rs.get(h) or {}).get("n", 0) for h, _ in HZ] + [0])
    few = n < 20
    if n == 0:
        line = "No past day in the history looked like this, so there is nothing to compare with."
    else:
        up = int(round((six.get("win") or 0) * six.get("n", 0)))
        line = "Seen %s times since %s%s; %s." % (("more than %d" % n) if n >= MATCH_CAP else str(n), since, (" (%d in %s itself)" % (own, label)) if own else "",
                                                 ("%d of %d were higher six months later" % (up, six["n"])) if six.get("n") else "too recent to know what followed")
        if few:
            line += " Too few cases to rely on."
    return {"n": n, "own": own, "since": since, "rows": rs, "base": base, "closest": closest, "few": few, "line": line, "same": same, "capped": n >= MATCH_CAP}


def outcomes(F):
    return {h: stats(F[h]) for h, _ in HZ}


def pick(dist, who, when, radius, cap=MATCH_CAP):
    order, kept, last = np.argsort(dist), [], {}
    for i in order:
        if dist[i] > radius or len(kept) >= cap:
            break
        w = who[i]
        if all(abs(int(when[i]) - k) >= GAP for k in last.get(w, [])):
            last.setdefault(w, []).append(int(when[i]))
            kept.append(int(i))
    return kept


def patterns(shares, targets, ctx):
    cal, grids = ctx["cal"], {}
    for s in shares:
        grids[s["t"]] = grid_of(s, ctx)
    pool = np.concatenate([g[1] for g in grids.values()])
    lo, hi = np.nanpercentile(pool, 1, axis=0), np.nanpercentile(pool, 99, axis=0)
    sd = np.nanstd(np.clip(pool, lo, hi), axis=0)
    sd[sd <= 0] = 1.0
    by, out = {s["t"]: s for s in shares}, {}
    for t in targets:
        s = by.get(t)
        if s is None or len(s["x"]) < 261:
            out[t] = {"line": "Not enough price history for a comparison.", "n": 0, "few": True}
            continue
        jT = len(s["x"]) - 1
        now = np.array([s["f"][k][jT] for k, _ in FEATS])
        if np.isnan(now).any():
            out[t] = {"line": "Today's setup could not be measured (a price or the fear gauge is missing).", "n": 0, "few": True}
            continue
        peers = [p for p in shares if p["sector"] and p["sector"] == s["sector"]]
        group = peers if len(peers) >= 15 else shares
        if all(p["t"] != t for p in group):
            group = group + [s]
        limit = s["a"] + jT - 21
        D, W, K, FW, ST = [], [], [], {h: [] for h, _ in HZ}, {"drift": [], "insiders": []}
        for p in group:
            js, X = grids[p["t"]]
            ok = (p["a"] + js <= limit) & ~np.isnan(X).any(axis=1)
            if not ok.any():
                continue
            js, X = js[ok], X[ok]
            D.append(np.sqrt(np.mean(((X - now) / sd) ** 2, axis=1)))
            W += [p["t"]] * len(js)
            K.append(p["a"] + js)
            for h, n in HZ:
                FW[h].append(fwd(p["x"], js, n))
            for c in ST:
                ST[c].append(p["st"][c][js])
        if not D:
            out[t] = {"line": "No history to compare with.", "n": 0, "few": True}
            continue
        D, K = np.concatenate(D), np.concatenate(K)
        FW = {h: np.concatenate(FW[h]) for h, _ in HZ}
        ST = {c: np.concatenate(ST[c]) for c in ST}
        kept = pick(D, W, K, RADIUS)
        rs = outcomes({h: FW[h][kept] for h, _ in HZ}) if kept else {}
        base = {h: {"avg": r4(np.nanmean(FW[h])), "win": r4(np.nanmean(FW[h][~np.isnan(FW[h])] > 0))} for h, _ in HZ}
        closest = [[W[i], cal[int(K[i])], r4(D[i], 2), r4(FW[MAIN][i]), r4(FW["12m"][i])] for i in kept[:5]]
        own = len([i for i in kept if W[i] == t])
        since = min([cal[int(K[i])][:4] for i in kept]) if kept else None
        same, mine = None, {c: int(s["st"][c][jT]) for c in ST}
        if kept and any(v >= 0 for v in mine.values()):
            sub = [i for i in kept if all(mine[c] < 0 or ST[c][i] == mine[c] for c in ST)]
            six = stats(FW[MAIN][sub]) if sub else None
            same = {"n": len(sub), "six": six, "drift": mine["drift"], "insiders": mine["insiders"]}
        res = summarise(rs, own, t, since, base, closest, same)
        res.update({"as_of": cal[s["a"] + jT], "price": r4(s["x"][jT], 2), "setup": {k: r4(now[i]) for i, (k, _) in enumerate(FEATS)},
                    "group": ("%d shares in %s" % (len(group), s["sector"])) if len(peers) >= 15 else ("all %d shares screened" % len(group)),
                    "checks": {c: int(s["st"][c][jT]) for c in ORDER}})
        out[t] = res
    return out


def market(ctx, cape):
    cal, spy, n = ctx["cal"], ctx["spy"], ctx["n"]
    f = {"d200": spy / roll_mean(spy, 200) - 1, "r63": lag_ratio(spy, 0, 63), "dd": spy / roll_max(spy, 252) - 1, "vol": roll_vol(spy, 20), "vix": ctx["vix"]}
    lvl = [E.stress_level(f["dd"][k], f["d200"][k], f["vol"][k]) if k >= 260 and not np.isnan(f["vol"][k]) else None for k in range(n)]
    cmap = dict((a, b) for a, b in (cape.get("rows") or []))
    cp = np.array([cmap.get(d[:7], np.nan) for d in cal], dtype=float)
    js = np.arange(260, n, 5)
    T = n - 1
    F = {h: fwd(spy, js, k) for h, k in HZ}
    out = {"as_of": cal[T], "level": lvl[T], "setup": {k: r4(f[k][T]) for k, _ in MFEATS}, "cape": r4(cp[T], 2) if not np.isnan(cp[T]) else None,
           "base": {h: {"avg": r4(np.nanmean(F[h])), "win": r4(np.nanmean(F[h][~np.isnan(F[h])] > 0)), "n": int((~np.isnan(F[h])).sum())} for h, _ in HZ}}
    for key, names, need_cape in (("stress_trend", [k for k, _ in MFEATS], False), ("with_valuation", [k for k, _ in MFEATS] + ["cape"], True)):
        g = dict(f)
        g["cape"] = cp
        if need_cape and np.isnan(cp[T]):
            out[key] = {"line": "The valuation figure for the market did not load, so this comparison could not be made.", "n": 0, "few": True}
            continue
        X = np.stack([g[k][js] for k in names], axis=1)
        now = np.array([g[k][T] for k in names])
        ok = (js <= T - 21) & ~np.isnan(X).any(axis=1) & np.array([lvl[k] == lvl[T] for k in js])
        sd = np.nanstd(X[~np.isnan(X).any(axis=1)], axis=0)
        sd[sd <= 0] = 1.0
        D = np.full(len(js), 9.0)
        D[ok] = np.sqrt(np.mean(((X[ok] - now) / sd) ** 2, axis=1))
        kept = pick(D, ["SPY"] * len(js), js, RADIUS_MARKET)
        rs = outcomes({h: F[h][kept] for h, _ in HZ}) if kept else {}
        closest = [["S&P 500 fund", cal[int(js[i])], r4(D[i], 2), r4(F[MAIN][i]), r4(F["12m"][i])] for i in kept[:5]]
        res = summarise(rs, 0, "", min([cal[int(js[i])][:4] for i in kept]) if kept else None, out["base"], closest)
        res["matched_on"] = ["the same stress level (%s)" % lvl[T]] + [dict(MFEATS + [("cape", "Ten-year price-to-earnings ratio of the S&P 500")])[k] for k in names]
        out[key] = res
    return out


# ---------------------------------------------------------------- the live seven-check score, logged from now on
def live_score(shares, ctx):
    log = E.rj("state/history/scores.json", {}) or {}
    days = log.get("days") or {}
    today = ctx["cal"][-1]
    rows = {}
    for r in ((E.rj("state/screen.json", {}) or {}).get("rows") or []) + (((E.rj("state/strategy.json", {}) or {}).get("edge") or {}).get("rows") or []):
        bits = {c["id"]: ("1" if c["pass"] else "0" if c["pass"] is False else "-") for c in r.get("checks") or []}
        if r.get("t") and bits:
            rows[r["t"]] = [r.get("score"), "".join(bits.get(c, "-") for c in ORDER)]
    if rows:
        days[today] = rows
    log = {"since": min(days) if days else today, "order": ORDER, "days": days,
           "note": "Every share scored on all seven checks, saved each trading day, so the full score can be tested on what follows."}
    E.wj("state/history/scores.json", log)
    by, res = {s["t"]: s for s in shares}, {}
    for d, rr in days.items():
        k = ctx["idx"].get(d)
        if k is None:
            continue
        for t, (score, bits) in rr.items():
            s = by.get(t)
            if s is None or not (s["a"] <= k < s["b"]) or score is None:
                continue
            for h, n in HZ:
                v = fwd(s["x"], np.array([k - s["a"]]), n)[0]
                res.setdefault(int(score), {}).setdefault(h, []).append(v)
    out = []
    for k in sorted(res):
        out.append({"k": k, "rows": {h: stats(np.array(res[k].get(h) or [np.nan])) for h, _ in HZ}, "logged": len(res[k].get("1m") or [])})
    return {"since": log["since"], "days": len(days), "by_k": out,
            "note": "The full seven-check score cannot be rebuilt for the past, because who held a share and what we thought it was worth were not saved before October 2026. It is saved every trading day from %s; the first one-month results appear about a month later." % log["since"]}


# ---------------------------------------------------------------- everything else a card depends on
def other_checks():
    lab, strat = E.rj("state/lab.json", {}) or {}, E.rj("state/strategy.json", {}) or {}
    out = [{"id": "bar", "name": "The bar: five of seven, and the trend check must pass",
            "what": "A share becomes a card only when it passes at least five of the seven checks and trades above its 200-day average.",
            "rule": "Score = number of checks passed. Card when score is 5 or more and the trend check is one of the passes. The best three by score, then by how far the price is under our fair value, become cards; the others are listed.",
            "record": "The full seven-check score has no history yet (see the combined table); it is logged daily from October 2026."},
           {"id": "fees", "name": "Fee test",
            "what": "Whether the trade can pay for its own costs at your broker at a given amount.",
            "rule": "Fees = 0.25% of each order, at least one euro (about $1.12), for the buy, the later sale and the sale that funds it. A scorecard idea counts as paying when fees take less than a tenth of the planned gain; a short-term rule when its measured average result per trade is larger than the fees.",
            "record": "Arithmetic, not a forecast. Check the fee in your broker's app: the free trades in your plan are not counted."},
           {"id": "stops", "name": "Stop-loss and take-profit on scorecard cards",
            "what": "How far the price may fall before the idea is wrong, and where the gain is taken.",
            "rule": "Stop = twice the share's 20-day volatility scaled to ten trading days, at least 5% under the entry. Take-profit = twice the stop distance above the entry.",
            "record": "No back-test: the levels are a risk rule, not a signal."},
           {"id": "funding", "name": "What pays for it",
            "what": "Every card names the money: a paired sale or new money.",
            "rule": "The weakest holding that passes two or fewer checks and that you have not chosen to keep is proposed for sale; otherwise the card says how much new money it needs. A position you chose to keep is never proposed.",
            "record": "A rule about your own portfolio; nothing to back-test."}]
    for rule in ((lab.get("tactical") or {}).get("rules") or []):
        out.append({"id": "rule:" + str(rule.get("id")), "name": "Short-term rule: " + str(rule.get("name")), "what": "A mechanical entry and exit read from daily closing prices.",
                    "rule": str(rule.get("rule")),
                    "record": "Back-test over %s years on the watchlist: %s trades, %s winners, %s a trade before costs. %s" % (
                        (lab.get("tactical") or {}).get("years"), rule.get("trades"), E.pc(rule.get("win_rate") or 0, 0), E.pc(rule.get("avg_gross") or 0, 2),
                        "It passes its own test after costs." if rule.get("passes") else "It fails its own test after costs, so its signals are shown greyed."),
                    "verdict": "working" if rule.get("passes") else "unproven"})
    bt = (strat.get("backtest") or {})
    ch = [v for v in bt.get("variants") or [] if v.get("id") == strat.get("chosen_id")]
    if ch:
        out.append({"id": "core", "name": "House strategy core", "what": "Four funds (US shares, foreign shares, bonds, gold) held in equal-risk proportions.",
                    "rule": "Each fund's weight is set so that all four add the same risk; proportions are reset monthly.",
                    "record": "Back-test %s to %s: %s a year, worst fall %s." % (str(bt.get("from") or "2005")[:4], str(bt.get("to") or "")[:4], E.pc(ch[0].get("cagr") or 0, 1), E.pc(abs(ch[0].get("mdd") or 0), 0))})
    return out


def main():
    t0 = time.time()
    limits, out = [], {"as_of": E.now_iso(), "status": "ok"}
    quant = E.rj("state/quant.json", {}) or {}
    # 1. which shares: the wide screen's list, plus the watchlist and everything on the desk
    names = load("universe.json") or []
    if not E.OFFLINE:
        try:
            import screen as SC
            got = SC.universe()[0]
            if len(got) > 50:
                names = [{"t": x["t"], "sector": x["sector"], "region": x["region"], "country": x["country"], "cap": x["cap"], "name": x["name"]} for x in got]
                save("universe.json", names)
        except Exception as e:
            limits.append("The share list did not load this run (%s); the saved list is used." % str(e)[:60])
    meta = {x["t"]: dict(x) for x in names}
    uni = (E.rj("ops/engine/universe.json", {}) or {}).get("assets", {})
    cards = (E.rj("research/cards/index.json", {}) or {}).get("cards") or []
    watch = [c.get("t") for c in cards if c.get("t")]
    desk = [c.get("ticker") for c in ((E.rj("state/decisions.json", {}) or {}).get("cards") or []) if c.get("status") == "open" and c.get("ticker")]
    targets = []
    for t in watch + desk:
        if t and t not in targets and (uni.get(t, {}).get("cls", "Equity") == "Equity"):
            targets.append(t)
    for t in targets:
        if t not in meta:
            u = uni.get(t) or {}
            meta[t] = {"t": t, "sector": u.get("sector") or "", "region": "Europe" if (u.get("country") not in (None, "United States", "US")) else "US",
                       "country": u.get("country") or "United States", "cap": None, "name": u.get("name") or t}
    for t, x in meta.items():
        x["sector_dcf"] = "Financials" if x.get("sector") == "Finance" else x.get("sector")
    order = targets + [x["t"] for x in names if x["t"] not in targets]
    # 2. data
    spy_rows = long_prices("SPY")
    if len(spy_rows) < 1000:
        out.update({"status": "no prices", "limits": ["The S&P 500 fund's price history did not load, so nothing could be tested this run."]})
        E.wj("state/backcheck.json", out)
        print("history: no price history for SPY")
        return
    cal = [d for d, v in spy_rows]
    n, idx = len(cal), {d: k for k, d in enumerate(cal)}
    spy = np.array([v for d, v in spy_rows], dtype=float)
    vix_al = align(long_prices(".VIX"), idx, n)
    vix = np.full(n, np.nan)
    if vix_al:
        vix[vix_al[0]:vix_al[1]] = vix_al[2]
        vix[vix_al[1]:] = vix_al[2][-1]
    else:
        limits.append("The fear gauge (VIX) did not load; pattern matches could not be made this run.")
    price_rows, misses = {}, 0
    for t in order:
        if time.time() - t0 > BUDGET * 0.35 or misses >= 12:
            limits.append("Prices: long history loaded for %d of %d shares (%s)." % (len(price_rows), len(order), "the price source stopped answering" if misses >= 12 else "time budget"))
            break
        rows = long_prices(t)
        if len(rows) >= 300:
            price_rows[t], misses = rows, 0
        else:
            misses = misses + 1 if not E.OFFLINE else 0
        if not E.OFFLINE:
            time.sleep(0.1)
    have = [t for t in order if t in price_rows]
    us = [t for t in have if meta[t].get("region") != "Europe"]
    fin = fetch_fin(have, t0 + BUDGET * 0.45, limits)
    ins = fetch_insiders(us[:170], t0 + BUDGET * 0.58, limits)
    cape = fetch_cape(limits)
    earn = fetch_earnings(cal, set(have), t0 + BUDGET, limits)
    fetched = int(time.time() - t0)
    # 3. the state of every check on every day
    spy_mom = lag_ratio(spy, 21, 252)
    me = [k for k in range(n - 1) if cal[k][:7] != cal[k + 1][:7]]
    spy_f = {}
    for h, k in HZ:
        a = np.full(n, np.nan)
        a[:n - k] = spy[k:] / spy[:n - k] - 1 - COST
        spy_f[h] = a
    ctx = {"cal": cal, "idx": idx, "n": n, "spy": spy, "vix": vix, "spy_mom": np.nan_to_num(spy_mom, nan=0.0), "earn": earn, "ins": ins, "fin": fin,
           "rf": (quant.get("opt") or {}).get("rf") or 0.04, "me": me, "months": [cal[k] for k in me], "spy_f": spy_f}
    shares = []
    for t in have:
        s = build(t, meta[t], price_rows[t], ctx)
        if s is not None:
            shares.append(s)
    listed = {}
    for s in shares:
        listed[cal[s["a"]][:4]] = listed.get(cal[s["a"]][:4], 0) + 1
    # 4. part A
    listed_now = set(x["t"] for x in names)
    for s in shares:
        s["listed"] = s["t"] in listed_now
    bc = backcheck([s for s in shares if s["t"] in listed_now] or shares, ctx) if shares else {}
    checks = []
    for c in ORDER:
        d = dict(CHECKS[c])
        d["id"] = c
        r = bc.get(c)
        if r:
            d.update(r)
        else:
            d.update({"history": None, "rows": None, "halves": [], "verdict": "unproven", "verdict_why": verdict(None, [])[1]})
        checks.append(d)
    combo = bc.get("combo") or {}
    span = (datetime.date.fromisoformat(cal[-1]) - datetime.date.fromisoformat(cal[0])).days / 365.25
    out.update({
        "cost": {"round_trip": COST, "note": "Every result is after half a percent for buying and selling (0.25% each way at your broker). Under about $450 the one-euro minimum makes the cost larger than that."},
        "coverage": {"shares": len(shares), "screened": len(names), "from": cal[0], "to": cal[-1], "years": r4(span, 1), "first_year_listed": listed,
                     "universe": "The %d largest US-listed companies the wide screen looks at today (about 240 American, 60 European), plus your watchlist." % len(names),
                     "survivorship": "Results are flattered: the list is today's largest companies, so every share in it survived and grew. Companies that failed or were delisted are missing, because the free price source no longer carries them. This flatters every group, and it flatters shares bought after a fall most of all, since the ones that never recovered are not in the list. Read the gap between pass and fail with that in mind."},
        "verdict_rule": "A check counts as working only if, in both halves of its history, shares that passed did better over the next six months than shares that failed and than the S&P 500 fund, with at least %d passes and %d fails in each half and at least %d years of history. Otherwise it is unproven. The six months before the split are left out of the first half, so no result spans both halves. This rule was fixed before any result was seen." % (MIN_CASES, MIN_CASES, MIN_YEARS),
        "horizons": [h for h, _ in HZ], "main": MAIN, "checks": checks,
        "combined": {"set": LONG, "names": [CHECKS[c]["name"] for c in LONG], "history": combo.get("history"), "by_k": combo.get("by_k") or [],
                     "note": "Only four of the seven checks can be rebuilt over many years (trend, momentum, earnings drift, insider buying), so this table counts passes out of four, not seven. It shows whether more passes went with better results; it cannot say whether five of seven is the right bar."},
        "live_score": live_score(shares, ctx),
        "other": other_checks(),
        "untested": [
            {"what": "Well-known holders", "why": "The free source shows who holds a share today and what they did last quarter, not who held it in past years. Without that history the check cannot be rebuilt, so it is unproven."},
            {"what": "The full seven-check score (3, 4, 5, 6 or 7 of 7)", "why": "Holder data has no history and our fair-value estimate only two years, so the full score cannot be rebuilt. The table uses the four checks that can. The full score is now saved every trading day so it can be tested from here on."},
            {"what": "Value beyond two fiscal years, quality beyond four", "why": "The free company statements go back four years. Longer statement history exists (SEC filings), but that source refuses requests from GitHub's servers without a registered contact address."},
            {"what": "Companies that failed or were delisted", "why": "The free price source drops them, so they are missing from every table. All results are flattered by that."},
            {"what": "Dividends", "why": "Prices are adjusted for splits only. Dividends are left out for shares and for the S&P 500 fund alike, which understates both by one to two percent a year."},
            {"what": "European shares on insider buying and value", "why": "They file no US insider forms, and their statements are in another currency than the US share price."}],
        "limits": limits,
        "method": "At the last trading day of every month, each share is marked pass, fail or unknown on each check using only what was public that day. Its price change over the next 21, 63, 126 and 252 trading days is then taken, less costs, and set beside the S&P 500 fund's over the same days. Cases are share-months; windows longer than a month overlap, so neighbouring cases are not independent.",
        "sources": "CNBC (daily closes from 2000), Nasdaq (annual statements, earnings calendar from %s), OpenInsider (SEC Form 4 from 2003), multpl.com (S&P 500 ten-year price-to-earnings ratio)." % EARN_START[:4],
        "earnings_history": {"from": earn.get("from"), "through": earn.get("through"), "symbols": len(earn.get("events") or {})},
        "insider_history": {"shares": len(ins.get("by") or {}), "as_of": ins.get("as_of")}})
    # 5. part B
    pat = {"as_of": out["as_of"], "radius": RADIUS, "radius_market": RADIUS_MARKET, "cap": MATCH_CAP, "gap_days": GAP, "main": MAIN, "features": [{"id": k, "name": v} for k, v in FEATS],
           "market_features": [{"id": k, "name": v} for k, v in MFEATS],
           "method": "Today's setup is seven numbers: " + "; ".join(v.lower() for k, v in FEATS) + ". Every week of every share's history is measured the same way. A past week counts as a match when, on average across the seven numbers, it sits within a quarter of a standard deviation of today (for the market, which is a single series, half a standard deviation and the same stress level). Matches in one share less than three months apart count once, and at most the closest 300 are kept. The search covers the share itself and the other shares in its sector (or all shares when the sector has fewer than 15). What followed is the price change after costs.",
           "not_matched": "Valuation gap, earnings surprise and insider activity are shown beside the setup. The valuation gap has no history, so it cannot be matched. Earnings and insider history exists for part of the shares and years; the detail shows how many matches also shared today's earnings and insider picture.",
           "honesty": "Past patterns are evidence, not a forecast. Fewer than 20 matches is too few to rely on. The shares are today's survivors, so what followed is flattered."}
    if vix_al:
        pat["shares"] = patterns(shares, targets, ctx)
        pat["market"] = market(ctx, cape)
        ctxs = {c.get("t"): c for c in cards}
        for t, p in pat["shares"].items():
            c, card = ctxs.get(t) or {}, E.rj("research/cards/" + t + ".json", {}) or {}
            rv = (card.get("earnings") or {}).get("review") or {}
            p["context"] = {"valuation_gap": c.get("mos"), "fair": c.get("fair"), "surprise_pct": rv.get("surprise_pct"), "move_5d": rv.get("move_5d"), "reported": rv.get("reported"),
                            "insider_buys_90d": c.get("insider_buys_90d"), "insider_sales_90d": c.get("insider_sales_90d"), "stress": (quant.get("stress") or {}).get("level")}
            p["name"] = c.get("name") or meta.get(t, {}).get("name") or t
    else:
        pat["shares"], pat["market"] = {}, None
    # the quant tools use the same history: outcome ranges, options, pairs and the learned signal, each in its own file
    try:
        import quant
        out["quant"] = quant.run(shares, ctx, meta, targets, limits, load, save)
    except Exception as e:
        limits.append("The quant tools did not run (%s: %s)." % (type(e).__name__, str(e)[:120]))
    # the Forecaster: dated yes-or-no forecasts with probabilities, logged once and scored when their date arrives
    try:
        import forecast
        out["forecast"] = forecast.run(shares, ctx, meta, targets, limits, load, save)
    except Exception as e:
        limits.append("The Forecaster did not run (%s: %s)." % (type(e).__name__, str(e)[:120]))
    # the order plans' stop and take-profit rules, tested on the same price history
    try:
        import plans
        bt = plans.backtest(shares)
        bt["as_of"] = out["as_of"]
        E.wj("state/plans_backtest.json", bt)
        out["plans_backtest"] = len(bt.get("rules") or [])
    except Exception as e:
        limits.append("The order-plan back-test did not run (%s: %s)." % (type(e).__name__, str(e)[:120]))
    # the live track record: every logged idea against the index fund and the average share of the list
    try:
        import track
        out["track"] = track.run(shares, ctx, limits)
    except Exception as e:
        limits.append("The live track record was not measured (%s: %s)." % (type(e).__name__, str(e)[:120]))
    out["runtime_s"], out["fetch_s"] = int(time.time() - t0), fetched
    E.wj("state/backcheck.json", out)
    E.wj("state/patterns.json", pat)
    print("history ok: %d shares, %.1f years, %s checks working, %d patterns, fetch %ds, total %ds" % (
        len(shares), span, len([c for c in checks if c.get("verdict") == "working"]), len(pat.get("shares") or {}), fetched, out["runtime_s"]))
    for x in limits:
        print("limit:", x)


if __name__ == "__main__":
    main()
