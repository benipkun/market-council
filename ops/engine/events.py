"""Event study (Ben, 21 Nov 2026): for each event type, how share prices moved 1, 5 and 20 trading days afterwards,
against the S&P 500 fund, going back as far as the free data allows.

Events: every 8-K the SEC holds for the shares the back-checks follow (about 300), sorted by its item codes
(results, deals, management changes, legal and accounting trouble, restructuring, impairments, new debt), plus each
results date split into a beat or a miss where our earnings history has the estimate. Prices: the back-checks' own
daily closes (.cache/history). Every number is a count of past cases: the median, the 10th and 90th percentiles and
the share that rose, with the number of cases. Fewer than 20 cases is labelled too few to rely on.
Writes state/news/event_study.json. Runs nightly after the back-checks; the SEC lists are cached for 7 days.
"""
import bisect
import datetime
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import news as N  # noqa: E402

ROOT = N.ROOT
HDIR = os.environ.get("MC_HIST", os.path.join(ROOT, ".cache", "history"))
HORIZONS = (1, 5, 20)
FEW = 20
TYPES = {"2.02": "earnings", "1.01": "M&A", "2.01": "M&A", "5.02": "management", "1.03": "legal", "4.02": "legal", "1.05": "legal", "3.01": "legal",
         "2.05": "restructuring", "2.06": "impairment", "2.03": "new debt", "7.01": "investor presentation", "8.01": "other"}
NAMES = {"earnings": "Results released (8-K 2.02)", "earnings beat": "Results beat the estimate", "earnings miss": "Results missed the estimate", "M&A": "Deal signed or completed (8-K 1.01, 2.01)",
         "management": "Director or officer change (8-K 5.02)", "legal": "Legal or accounting trouble (8-K 1.03, 4.02, 1.05, 3.01)", "restructuring": "Restructuring or layoffs (8-K 2.05)",
         "impairment": "Impairment (8-K 2.06)", "new debt": "New debt (8-K 2.03)", "investor presentation": "Investor presentation (8-K 7.01)", "other": "Other company news (8-K 8.01)",
         "guidance": "Restructuring or impairment (8-K 2.05, 2.06), our nearest measure of a guidance cut", "macro": "Fed rate decision days (S&P 500 fund itself, raw move)"}
NOT_MEASURABLE = {"rating change": "no free history of analyst changes; our own log of changes builds it from 21 Nov 2026",
                  "product": "no free dated history that separates product news; counted under other company news",
                  "regulation": "no free dated history; counted under other company news"}


def rows(sym):
    p = os.path.join(HDIR, "p_" + re.sub("[^A-Za-z0-9]", "_", sym) + ".csv")
    try:
        with open(p, encoding="utf-8") as f:
            return [(a, float(b)) for a, b in (ln.split(",")[:2] for ln in f.read().split("\n") if "," in ln)]
    except Exception:
        return []


def filings(t, cik):
    """Every 8-K date with items, from the SEC's full list (recent block plus the older pages); cached 7 days."""
    cp = os.path.join(HDIR, "sec8k_%s.json" % re.sub("[^A-Za-z0-9]", "_", t))
    try:
        c = json.load(open(cp, encoding="utf-8"))
        if (datetime.datetime.utcnow() - datetime.datetime.strptime(c["at"], "%Y-%m-%d")).days < 7:
            return c["rows"]
    except Exception:
        pass
    if N.OFFLINE or not cik:
        return []
    out = []
    try:
        sub = N.get("https://data.sec.gov/submissions/CIK%010d.json" % cik, N.SEC_UA)
        blocks = [(sub.get("filings") or {}).get("recent") or {}]
        for f in (sub.get("filings") or {}).get("files") or []:
            time.sleep(0.12)
            try:
                blocks.append(N.get("https://data.sec.gov/submissions/" + f["name"], N.SEC_UA))
            except Exception:
                pass
        for r in blocks:
            for i, form in enumerate(r.get("form") or []):
                if form == "8-K":
                    out.append([r["filingDate"][i], str((r.get("acceptanceDateTime") or [""] * (i + 1))[i])[11:16], str((r.get("items") or [""] * (i + 1))[i] or "")])
    except Exception:
        return []
    os.makedirs(HDIR, exist_ok=True)
    json.dump({"at": datetime.datetime.utcnow().strftime("%Y-%m-%d"), "rows": out}, open(cp, "w", encoding="utf-8"))
    time.sleep(0.12)
    return out


def moves(px, spy, day, after_close):
    """Returns against the S&P 500 fund after h trading days, from the last close before the news reached the market."""
    ds = [d for d, _ in px]
    i = bisect.bisect_right(ds, day) - 1 if after_close else bisect.bisect_left(ds, day) - 1
    if i < 0 or i >= len(px) - 1:
        return None
    sd = [d for d, _ in spy]
    j = bisect.bisect_right(sd, ds[i]) - 1
    if j < 0 or sd[j] != ds[i]:
        return None
    out = {}
    for h in HORIZONS:
        if i + h >= len(px) or j + h >= len(spy):
            continue
        out[h] = (px[i + h][1] / px[i][1] - 1) - (spy[j + h][1] / spy[j][1] - 1)
    return out


def summary(v):
    v = sorted(v)
    n = len(v)
    if not n:
        return {"n": 0}
    q = lambda p: v[min(n - 1, max(0, int(round(p * (n - 1)))))]
    return {"n": n, "median": round(q(0.5), 4), "p10": round(q(0.1), 4), "p90": round(q(0.9), 4), "mean": round(sum(v) / n, 4), "up": round(sum(1 for x in v if x > 0) / float(n), 3),
            "few": n < FEW}


def run():
    spy = rows("SPY")
    syms = sorted(os.path.basename(p)[2:-4] for p in glob.glob(os.path.join(HDIR, "p_*.csv")))
    syms = [s for s in syms if s not in ("SPY", "SHY", "TLT", "GLD", "IEF", "QQQ") and not s.startswith("_")]
    cikmap = {}
    if not N.OFFLINE:
        try:
            for v in N.get("https://www.sec.gov/files/company_tickers.json", N.SEC_UA).values():
                cikmap[str(v.get("ticker")).upper()] = int(v.get("cik_str"))
        except Exception:
            pass
    acc = {}
    first, used = None, 0
    for s in syms:
        px = rows(s)
        if len(px) < 300:
            continue
        f8 = filings(s, cikmap.get(s.replace("_", "-").upper()) or cikmap.get(s.upper()))
        if not f8:
            continue
        used += 1
        eh = dict((r["date"], r) for r in ((N.rj("state/earnings/history/%s.json" % s, {}) or {}).get("rows") or []) if r.get("est") is not None and r.get("eps") is not None)
        for day, hm, items in f8:
            its = [x.strip() for x in items.split(",") if x.strip()]
            after = bool(hm) and hm >= "16:00"          # SEC stamps are US Eastern time
            m = moves(px, spy, day, after)
            if not m:
                continue
            first = min(first or day, day)
            kinds = set(TYPES[i] for i in its if i in TYPES)
            if "2.05" in its or "2.06" in its:
                kinds.add("guidance")
            if "2.02" in its:
                e = eh.get(day) or eh.get((datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat())
                if e:
                    kinds.add("earnings beat" if float(e["eps"]) > float(e["est"]) else "earnings miss" if float(e["eps"]) < float(e["est"]) else "earnings")
            for k in kinds:
                for h, v in m.items():
                    acc.setdefault(k, {}).setdefault(h, []).append(v)
    # Fed decision days: the S&P 500 fund's own move (raw, no benchmark to take away)
    fomc = [e["date"] for e in (N.rj("state/news/macro.json", {}) or {}).get("events") or [] if "FOMC" in e.get("what", "")]
    sd = [d for d, _ in spy]
    for d in fomc:
        i = bisect.bisect_left(sd, d) - 1
        if 0 <= i and sd[min(len(sd) - 1, i + 1)] == d:
            for h in HORIZONS:
                if i + h < len(spy):
                    acc.setdefault("macro", {}).setdefault(h, []).append(spy[i + h][1] / spy[i][1] - 1)
    types = {}
    for k, hs in acc.items():
        types[k] = {"name": NAMES.get(k, k)}
        for h in HORIZONS:
            types[k]["%dd" % h] = summary(hs.get(h) or [])
    out = {"as_of": N.iso(), "since": first, "shares": used, "types": types, "not_measurable": NOT_MEASURABLE, "few": FEW,
           "method": ("Each 8-K the SEC lists for the shares the back-checks follow, dated by its SEC time stamp (after 16:00 US Eastern counts from that day's close, "
                      "otherwise from the close before). Move = the share's return minus the S&P 500 fund's over 1, 5 and 20 trading days. Beat or miss from our earnings "
                      "history where it has the estimate. Median, 10th and 90th percentile and the share of cases that rose; a count of past cases, not a forecast. "
                      "Survivorship: only shares listed today are in the set, which flatters the averages a little.")}
    N.wj("state/news/event_study.json", out)
    return out


if __name__ == "__main__":
    o = run()
    print("events ok: %d shares since %s; %s" % (o["shares"], o["since"], ", ".join("%s %d" % (k, (v.get("5d") or {}).get("n", 0)) for k, v in sorted(o["types"].items()))))
