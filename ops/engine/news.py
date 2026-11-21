"""News desk (Ben, 21 Nov 2026: "bring the news readers up to the standard of a professional research desk").

Every item goes through one pipeline, in plain code:
  collect -> remove duplicates -> tag the companies -> sort by event type -> four scores -> importance.
Only items that are new AND unsorted by the rules go to a small model (Haiku), and only items that score as
important go to the thesis check (files.py). Both model steps have a hard daily dollar cap (state/news/budget.json);
with no key or no budget left, the plain-code rules decide and say so.

Sources (free; each one's rules checked, see SOURCES below):
  - SEC EDGAR filings: 8-K (with item codes), 10-Q, 10-K, 6-K, 20-F, Form 4 insider filings, 13D. The 8-K exhibit
    99.1 is the company's own press release, so earnings releases and most investor-relations news arrive here first.
  - Nasdaq headlines per company (already fetched by research.py; mostly opinion sites, scored low for reliability).
  - Analyst rating and target changes: the difference between today's and yesterday's Nasdaq consensus snapshot.
  - Earnings call reads by the Earnings Reader routine (state/earnings/reads/).
  - Macro calendar: FOMC meetings (federalreserve.gov) and BLS releases (CPI, jobs) where BLS answers.
  - Sector headlines: Nasdaq headlines for the sector funds the holdings sit in.
Writes state/news/items.json (30 days), state/news/today.json (at most 5 items for TODAY), state/news/stats.json
(the measurements: items a day by source, duplicates, delay, items that led to a card) and state/news/budget.json.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.environ.get("MC_ROOT", ".")
OFFLINE = os.environ.get("MC_OFFLINE") == "1"
KEEP_DAYS = 30
TOP_N = 5
IMPORTANT = 0.08          # importance at or above this goes to the thesis check and may reach TODAY
CAP_USD = {"sort": 0.05, "thesis": 0.20, "advisor_files": 0.00}   # hard daily caps; the Advisor keeps its own caps in answer.py
SMALL = "claude-haiku-5-5"
MAIN = "claude-sonnet-5-5"
PRICE = {SMALL: (1.0, 5.0), MAIN: (3.0, 15.0)}                     # $ per million tokens in, out (estimate; check the price list)
SEC_UA = ("Market Council research " + os.environ["SEC_CONTACT"]) if os.environ.get("SEC_CONTACT") else "Mozilla/5.0 (Market Council research)"
BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

SOURCES = {
    "sec": {"name": "SEC EDGAR filings", "reliability": 1.0, "rules": "Public; the SEC allows automated access at up to 10 requests a second with a declared User-Agent (we send about 1 a second)."},
    "analyst": {"name": "Nasdaq analyst consensus (change since yesterday)", "reliability": 0.8, "rules": "Public web data; read three times a day, the same as a person checking the page."},
    "reads": {"name": "Earnings call read (Earnings Reader routine)", "reliability": 0.8, "rules": "Our own summary of the company's call."},
    "macro": {"name": "Fed and BLS release calendars", "reliability": 1.0, "rules": "US government sites, public domain."},
    "wire": {"name": "News wire headline", "reliability": 0.7, "rules": "Headline and link only, through Nasdaq's public news page."},
    "opinion": {"name": "Opinion site headline", "reliability": 0.3, "rules": "Headline and link only, through Nasdaq's public news page."},
    "sector": {"name": "Sector fund headline", "reliability": 0.5, "rules": "Headline and link only, through Nasdaq's public news page."},
}
OPINION = ("zacks", "motley fool", "barchart", "bnk invest", "marketbeat", "fintel", "investorplace", "seeking alpha", "24/7 wall", "gurufocus", "simply wall", "tipranks", "insider monkey", "benzinga")
WIRES = ("rttnews", "reuters", "associated press", "ap ", "dow jones", "business wire", "globenewswire", "pr newswire", "accesswire", "nasdaq")
SECTOR_FUND = {"Technology": "XLK", "Information Technology": "XLK", "Health Care": "XLV", "Healthcare": "XLV", "Financials": "XLF", "Financial Services": "XLF",
               "Energy": "XLE", "Industrials": "XLI", "Consumer Discretionary": "XLY", "Consumer Cyclical": "XLY", "Consumer Staples": "XLP", "Consumer Defensive": "XLP",
               "Utilities": "XLU", "Materials": "XLB", "Basic Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC"}

# 8-K item codes -> event type (the SEC's own list of what each item means)
ITEMS = {"2.02": "earnings", "7.01": "other", "8.01": "other", "1.01": "M&A", "2.01": "M&A", "1.02": "M&A", "5.02": "management", "5.03": "other",
         "1.03": "legal", "4.02": "legal", "1.05": "legal", "3.01": "legal", "4.01": "legal", "2.05": "guidance", "2.06": "guidance", "2.03": "other", "5.07": "other", "9.01": "other"}
ITEM_TEXT = {"2.02": "results of operations", "1.01": "material agreement", "2.01": "acquisition or sale completed", "1.02": "agreement ended", "5.02": "director or officer change",
             "1.03": "bankruptcy", "4.02": "earlier statements can no longer be relied on", "1.05": "cybersecurity incident", "3.01": "listing standards notice", "4.01": "auditor change",
             "2.05": "restructuring or layoffs", "2.06": "impairment", "2.03": "new debt", "7.01": "investor presentation", "8.01": "other events", "5.07": "shareholder vote", "5.03": "bylaws change"}
SEVERE = ("1.03", "4.02", "3.01", "1.05")
RULES = [  # headline words -> event type, checked in order
    ("earnings", r"\b(earnings|results|eps|revenue (?:rose|fell|beat|miss)|quarter(?:ly)? (?:profit|loss|results)|beats?|miss(?:es)?\b.*estimates)"),
    ("guidance", r"\b(guidance|outlook|forecast(?:s)? (?:cut|raised|lowered)|raises? (?:its )?(?:full-year|annual)|lowers? (?:its )?(?:full-year|annual)|warns?)\b"),
    ("M&A", r"\b(acquir|acquisition|merger|merge|buyout|takeover|to buy|deal to|stake in|spin[- ]?off|divest)"),
    ("legal", r"\b(lawsuit|sued|sues|probe|investigation|antitrust|settle[sd]? (?:a |the )?(?:lawsuit|case|claims|charges|probe)|settlement|fined|fines|penalt|recall|subpoena|class action|doj|ftc|sec charges|court)"),
    ("management", r"\b(ceo|cfo|chief executive|steps down|resign|appoint|names .* (?:chief|president)|succession|board)"),
    ("regulation", r"\b(fda|approval|approves|approved|regulat|tariff|sanction|ban|ruling|license|epa|fcc)"),
    ("rating change", r"\b(upgrade|downgrade|price target|initiat(?:es|ed) coverage|reiterat|outperform|underperform|overweight|underweight)"),
    ("product", r"\b(launch|unveil|introduc|partnership|contract|order[s]? for|wins?|rollout|release[sd]? new)"),
    ("macro", r"\b(fed|fomc|inflation|cpi|jobs report|payrolls|rate cut|rate hike|treasury yield|recession|gdp)"),
]
POS = set("lifts lift tops top hikes upbeat beat beats raise raises raised record growth upgrade upgraded outperform approval approved wins win surge surges jump jumps strong exceed exceeds exceeded higher gain gains profit buyback dividend increase increased boost accelerat expand expands".split())
NEG = set("miss misses missed cut cuts lower lowered downgrade downgraded underperform probe lawsuit recall warns warning weak decline declines fell fall falls plunge plunges slump loss losses layoffs restructuring impairment bankruptcy fraud resign resigns delay delayed halt halts sued fine fined investigation decrease decreased slow slows".split())
OPINION_HEAD = re.compile(r"(\?$|\bis it (still )?a buy\b|\bshould you\b|\bbetter buy\b|\bvs\.?\b|\btop \d+\b|\b\d+ (stocks?|reasons)\b|\bbuy now\b|\bmillionaire\b|\bforever\b|\bwhy .* (stock|shares) (?:is|are)\b)", re.I)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(d=None):
    return (d or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def wj(rel, obj):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        json.dump(obj, f, indent=1, ensure_ascii=True)


def get(url, ua=BROWSER, as_json=True, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json, text/html, text/calendar, */*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        b = r.read().decode("utf-8", "replace")
    return json.loads(b) if as_json else b


def pdate(s):
    """A timestamp from the formats our sources use; None when only unknown text is given."""
    s = str(s or "").strip()
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y"):
        try:
            d = datetime.datetime.strptime(s[:26] if "T" in f else s, f)
            return d.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            pass
    m = re.match(r"(\d+) (minute|hour|day)s? ago", s)
    if m:
        return now() - datetime.timedelta(**{m.group(2) + "s": int(m.group(1))})
    return None


def norm(t):
    return re.sub(r"[^a-z0-9 ]", "", str(t or "").lower())


def tokens(t):
    stop = {"the", "a", "an", "of", "to", "and", "in", "on", "for", "is", "its", "it", "as", "at", "by", "with", "from", "after", "stock", "shares", "inc", "corp"}
    return set(w for w in norm(t).split() if w not in stop and len(w) > 1)


def uid(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- universe
def universe():
    snap = rj("treasury/snapshot.json", {}) or {}
    nav = float(snap.get("nav") or 0) or sum(float(p.get("market_value") or 0) for p in snap.get("positions") or []) + float(snap.get("cash") or 0)
    held = {p["ticker"]: (float(p.get("market_value") or 0) / nav if nav else 0.0) for p in snap.get("positions") or [] if p.get("ticker")}
    watch = [str(x.get("ticker") if isinstance(x, dict) else x) for x in (rj("state/known_companies.json", {}) or {}).get("tickers") or []]
    ideas = [c.get("ticker") for c in (rj("state/decisions.json", {}) or {}).get("cards") or [] if c.get("status") == "open" and c.get("ticker")]
    cands = [c.get("t") or c.get("ticker") for c in ((rj("state/actions.json", {}) or {}).get("candidates") or [])[:5]]
    names = {}
    for t in list(held) + watch + ideas + cands:
        if t and t not in names and t != "portfolio":
            names[t] = held.get(t, 0.0)
    keeps = set(((rj("state/decisions.json", {}) or {}).get("keeps") or {}).keys())
    return names, set(held), keeps


# ---------------------------------------------------------------- collectors
def from_headlines(t):
    card = rj("research/cards/%s.json" % t, {}) or {}
    out = []
    for n in card.get("news") or []:
        pub = str(n.get("publisher") or "")
        kind = "opinion" if any(o in pub.lower() for o in OPINION) else "wire" if any(w in pub.lower() for w in WIRES) else "opinion" if OPINION_HEAD.search(str(n.get("title") or "")) else "wire"
        if kind == "wire" and OPINION_HEAD.search(str(n.get("title") or "")):
            kind = "opinion"
        out.append({"source": kind, "publisher": pub, "tickers": [t], "title": n.get("title"), "url": n.get("url"), "published": n.get("date"), "day_only": True})
    return out


def from_sec(t, cikmap):
    c = cikmap.get(t.upper())
    if not c:
        return []
    try:
        sub = get("https://data.sec.gov/submissions/CIK%010d.json" % c, SEC_UA)
    except Exception:
        return []
    time.sleep(0.15)
    r = (sub.get("filings") or {}).get("recent") or {}
    out, cut = [], (now() - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for i, form in enumerate(r.get("form") or []):
        fd = r["filingDate"][i]
        if fd < cut:
            break
        if form not in ("8-K", "8-K/A", "10-Q", "10-K", "6-K", "20-F", "4", "SC 13D", "SC 13D/A", "40-F"):
            continue
        acc = r["accessionNumber"][i]
        items = [x.strip() for x in str((r.get("items") or [""] * (i + 1))[i] or "").split(",") if x.strip()]
        url = "https://www.sec.gov/Archives/edgar/data/%d/%s/%s" % (c, acc.replace("-", ""), r["primaryDocument"][i])
        what = {"10-Q": "quarterly report (10-Q)", "10-K": "annual report (10-K)", "20-F": "annual report (20-F)", "40-F": "annual report (40-F)", "6-K": "foreign company report (6-K)",
                "4": "insider trade filing (Form 4)", "SC 13D": "an investor took a 5%+ stake with plans (13D)", "SC 13D/A": "change to a 5%+ holder's stake (13D/A)"}.get(form)
        if form.startswith("8-K"):
            what = "8-K: " + ", ".join(ITEM_TEXT.get(x, x) for x in items if x != "9.01") if items else "8-K"
        out.append({"source": "sec", "publisher": "SEC EDGAR", "tickers": [t], "title": "%s filed %s" % (t, what), "url": url, "form": form, "items": items,
                    "published": r.get("acceptanceDateTime", [None] * (i + 1))[i] or fd, "day_only": False, "id_hint": acc})
    return out


def from_analysts(names):
    prev = rj("state/news/analyst_prev.json", {}) or {}
    cur, out = {}, []
    for t in names:
        a = (rj("research/cards/%s.json" % t, {}) or {}).get("analysts") or {}
        if not a.get("target_mean"):
            continue
        cur[t] = {"rating": a.get("rating"), "target": a.get("target_mean"), "at": a.get("as_of")}
        p = prev.get(t)
        if not p or not p.get("target"):
            continue
        ch = float(a["target_mean"]) / float(p["target"]) - 1
        if a.get("rating") != p.get("rating") or abs(ch) >= 0.03:
            words = []
            if a.get("rating") != p.get("rating"):
                words.append("consensus rating %s -> %s" % (p.get("rating"), a.get("rating")))
            if abs(ch) >= 0.03:
                words.append("average target %s %.1f%% to $%.2f" % ("raised" if ch > 0 else "cut", 100 * abs(ch), float(a["target_mean"])))
            out.append({"source": "analyst", "publisher": "Nasdaq analyst research", "tickers": [t], "title": "%s analysts: %s" % (t, "; ".join(words)),
                        "url": "https://www.nasdaq.com/market-activity/stocks/%s/analyst-research" % t.lower(), "published": iso(), "day_only": False, "tone_hint": 1 if ch > 0 else -1})
    wj("state/news/analyst_prev.json", cur or prev)
    return out


def from_reads():
    out = []
    d = os.path.join(ROOT, "state", "earnings", "reads")
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d))[-40:]:
        x = rj("state/earnings/reads/" + f, {}) or {}
        t = x.get("ticker") or f.split("-")[0]
        line = x.get("summary") or x.get("headline") or x.get("guidance") or ""
        if line:
            out.append({"source": "reads", "publisher": "Earnings Reader", "tickers": [t], "title": "%s call: %s" % (t, str(line)[:180]), "url": x.get("url") or x.get("source"),
                        "published": x.get("date") or x.get("as_of") or f[len(t) + 1:len(t) + 11], "day_only": True})
    return out


def macro_calendar():
    """FOMC meetings and BLS releases from the official calendars; the last good copy is kept when a site does not answer."""
    old = rj("state/news/macro.json", {}) or {}
    ev = []
    try:
        html = get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", as_json=False)
        for yr, body in re.findall(r"(\d{4}) FOMC Meetings(.*?)(?=\d{4} FOMC Meetings|$)", html, re.S):
            for mon, dd in re.findall(r'fomc-meeting__month[^>]*>\s*<strong>([A-Za-z/]+)</strong>.*?fomc-meeting__date[^>]*>([\d\-]+)', body, re.S):
                m1 = mon.split("/")[-1]
                last = dd.split("-")[-1]
                try:
                    d = datetime.datetime.strptime("%s %s %s" % (m1[:3], last, yr), "%b %d %Y").strftime("%Y-%m-%d")
                    ev.append({"date": d, "what": "Fed rate decision (FOMC)", "source": "federalreserve.gov"})
                except Exception:
                    pass
    except Exception:
        ev += [e for e in old.get("events") or [] if "FOMC" in e.get("what", "")]
    try:
        ics = get("https://www.bls.gov/schedule/news_release/bls.ics", as_json=False)
        for blk in ics.split("BEGIN:VEVENT")[1:]:
            s = re.search(r"SUMMARY:(.*)", blk)
            d = re.search(r"DTSTART[^:]*:(\d{8})", blk)
            if s and d and re.search(r"Consumer Price Index|Employment Situation|Producer Price Index", s.group(1)):
                ev.append({"date": "%s-%s-%s" % (d.group(1)[:4], d.group(1)[4:6], d.group(1)[6:]), "what": s.group(1).strip()[:80], "source": "bls.gov"})
    except Exception:
        ev += [e for e in old.get("events") or [] if e.get("source") == "bls.gov"]
    seen, uniq = set(), []
    for e in sorted(ev, key=lambda e: e["date"]):
        k = (e["date"], e["what"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    out = {"as_of": iso(), "events": uniq or old.get("events") or [], "note": "Official calendars; when a site does not answer, the last good copy stays."}
    wj("state/news/macro.json", out)
    return out


def from_macro(cal):
    today = now().strftime("%Y-%m-%d")
    soon = (now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
    return [{"source": "macro", "publisher": e["source"], "tickers": ["MARKET"], "title": "%s on %s" % (e["what"], e["date"]), "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm" if "FOMC" in e["what"] else "https://www.bls.gov/schedule/",
             "published": today, "day_only": True, "event_date": e["date"], "type_hint": "macro"} for e in cal.get("events") or [] if today <= e["date"] <= soon]


def from_sector(held):
    q = (rj("state/quant.json", {}) or {}).get("assets") or {}
    funds = sorted(set(SECTOR_FUND.get(str((q.get(t) or {}).get("sector") or "")) for t in held) - {None})
    out = []
    if OFFLINE:
        return out
    for f in funds[:8]:
        try:
            rows = (get("https://api.nasdaq.com/api/news/topic/articlebysymbol?q=%s%%7Cetf&offset=0&limit=4&fallback=false" % f.lower()).get("data") or {}).get("rows") or []
        except Exception:
            rows = []
        for n in rows:
            out.append({"source": "sector", "publisher": n.get("publisher"), "tickers": ["SECTOR:" + f], "title": n.get("title"), "url": "https://www.nasdaq.com" + str(n.get("url") or ""),
                        "published": n.get("created") or n.get("ago"), "day_only": True})
        time.sleep(0.3)
    return out


# ---------------------------------------------------------------- pipeline
def classify(x):
    if x.get("type_hint"):
        return x["type_hint"], "rule"
    if x["source"] == "analyst":
        return "rating change", "rule"
    if x["source"] == "sec":
        f = x.get("form", "")
        if f in ("10-Q", "10-K", "20-F", "40-F"):
            return "earnings", "rule"
        if f == "4":
            return "insider", "rule"
        if f.startswith("SC 13D"):
            return "M&A", "rule"
        its = [i for i in x.get("items") or [] if i != "9.01"]
        for i in ("2.02",) + SEVERE + ("1.01", "2.01", "5.02", "2.05", "2.06"):
            if i in its:
                return ITEMS[i], "rule"
        return "other", "rule"
    if x["source"] == "reads":
        return "earnings", "rule"
    t = str(x.get("title") or "").lower()
    for kind, rx in RULES:
        if re.search(rx, t):
            return kind, "rule"
    return "other", "unsorted"


def tone(x):
    if x.get("tone_hint") is not None:
        return float(x["tone_hint"])
    if x["source"] == "sec":
        its = x.get("items") or []
        if any(i in SEVERE for i in its):
            return -1.0
        if "2.05" in its or "2.06" in its:
            return -0.5
        return 0.0
    w = norm(x.get("title")).split()
    p, n = sum(1 for a in w if a in POS), sum(1 for a in w if a in NEG)
    return 0.0 if p + n == 0 else round((p - n) / float(p + n), 2)


def about(x, t):
    """Does a headline name the company (ticker or the first word of its name)? Nasdaq's feed files market stories under many tickers."""
    name = str((rj("research/cards/%s.json" % t, {}) or {}).get("name") or "")
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if len(w) > 2 and w.lower() not in ("the", "inc", "corp", "corporation", "company", "holdings", "group", "class")]
    title = str(x.get("title") or "")
    return bool(re.search(r"\b%s\b" % re.escape(t), title)) or bool(words and re.search(r"\b%s" % re.escape(words[0]), title, re.I))


ACTION_TICKERS = set(a.get("ticker") for a in (rj("state/actions.json", {}) or {}).get("actions") or [] if a.get("ticker"))


def scores(x, weights, held, quant, now_):
    t0 = x["tickers"][0]
    if t0 == "MARKET":
        rel = 0.45
    elif t0.startswith("SECTOR:"):
        rel = 0.35
    elif t0 in held:
        rel = min(1.0, 0.5 + 2.0 * weights.get(t0, 0.0))
    elif t0 in ACTION_TICKERS:
        rel = 0.7
    else:
        rel = 0.3
    pub = pdate(x.get("published")) or now_
    if x.get("day_only"):
        pub = pub + datetime.timedelta(hours=12)
    age_h = max(0.0, (now_ - pub).total_seconds() / 3600.0)
    if x.get("event_date"):
        age_h = 0.0
    nov = 0.5 ** (age_h / 48.0)
    # already in the price? the move since the item against the share's usual daily move
    q = quant.get(t0) or {}
    card = rj("research/cards/%s.json" % t0, {}) or {}
    move = (card.get("quote") or {}).get("change_pct")
    vol = q.get("vol_1y")
    if move is not None and vol and age_h < 30:
        dvol = float(vol) / 15.87 * 100
        nov *= 1.0 - 0.5 * min(1.0, abs(float(move)) / (2 * dvol)) if dvol else 1.0
    if x.get("dup_of"):
        nov *= 0.2
    if x["source"] in ("opinion", "wire") and not about(x, t0):
        rel *= 0.4
        x["about_other"] = True
    rely = SOURCES.get(x["source"], {}).get("reliability", 0.5)
    tn = tone(x)
    weight = {"earnings": 1.0, "guidance": 1.0, "M&A": 0.9, "legal": 0.9, "management": 0.7, "rating change": 0.6, "regulation": 0.8, "product": 0.5, "macro": 0.7, "insider": 0.4, "other": 0.3}.get(x["type"], 0.3)
    imp = rel * rely * nov * (0.5 + 0.5 * abs(tn)) * weight
    if x["source"] == "sec" and any(i in SEVERE for i in x.get("items") or []):
        imp = max(imp, 0.8 * rel)
    return {"relevance": round(rel, 2), "novelty": round(nov, 2), "reliability": rely, "tone": tn, "importance": round(imp, 3)}


def dedupe(items, seen):
    """Exact duplicates go; near duplicates (same company, 60% of the same words, within 3 days) are kept as one story."""
    out, groups = [], {}
    dups = 0
    for x in items:
        x["id"] = uid(x.get("id_hint") or norm(x.get("title")), x["tickers"][0] if x["source"] in ("sec", "analyst", "macro") else "")
        same = [y for y in out if y["id"] == x["id"]]
        if same:
            for t in x["tickers"]:
                if t not in same[0]["tickers"]:
                    same[0]["tickers"].append(t)
            dups += 1
            continue
        tk = tokens(x.get("title"))
        for y in groups.get(x["tickers"][0], []):
            ty = y["_tok"]
            if tk and ty and len(tk & ty) / float(len(tk | ty)) >= 0.6:
                x["dup_of"] = y["id"]
                dups += 1
                break
        x["_tok"] = tk
        groups.setdefault(x["tickers"][0], []).append(x)
        x["first_seen"] = seen.get(x["id"]) or iso()
        seen.setdefault(x["id"], x["first_seen"])
        out.append(x)
    for x in out:
        x.pop("_tok", None)
    return out, dups


# ---------------------------------------------------------------- the small and the main model, under a hard cap
def budget():
    b = rj("state/news/budget.json", {}) or {}
    day = now().strftime("%Y-%m-%d")
    if b.get("day") != day:
        b = {"day": day, "spent": {k: 0.0 for k in CAP_USD}, "calls": {k: 0 for k in CAP_USD}, "cap": CAP_USD,
             "rule": "Hard daily caps in dollars. When a cap is reached the plain-code rules decide for the rest of the day and the item says so."}
    b["cap"] = CAP_USD
    return b


def ask(model, prompt, purpose, b, max_tokens=200):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or OFFLINE or b["spent"].get(purpose, 0) >= CAP_USD.get(purpose, 0):
        return None
    body = json.dumps({"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    u = d.get("usage") or {}
    pi, po = PRICE.get(model, (3.0, 15.0))
    b["spent"][purpose] = round(b["spent"].get(purpose, 0) + (u.get("input_tokens", 0) * pi + u.get("output_tokens", 0) * po) / 1e6, 5)
    b["calls"][purpose] = b["calls"].get(purpose, 0) + 1
    return "".join(c.get("text", "") for c in d.get("content") or [])


def sort_new(items, b):
    """The small model sorts only items the rules left unsorted, that are new today and not duplicates."""
    todo = [x for x in items if x.get("how") == "unsorted" and not x.get("dup_of") and x["first_seen"][:10] == now().strftime("%Y-%m-%d") and x["source"] not in ("opinion",)]
    kinds = ["earnings", "guidance", "M&A", "legal", "management", "product", "macro", "regulation", "rating change", "other"]
    for i in range(0, len(todo), 20):
        chunk = todo[i:i + 20]
        prompt = ("Sort each headline into one event type from this list: %s. Answer with JSON only: a list of the types, in order.\n" % ", ".join(kinds) +
                  "\n".join("%d. %s" % (j + 1, x["title"]) for j, x in enumerate(chunk)))
        a = ask(SMALL, prompt, "sort", b, 300)
        try:
            got = json.loads(re.search(r"\[.*\]", a or "", re.S).group(0))
        except Exception:
            break
        for x, k in zip(chunk, got):
            if k in kinds:
                x["type"], x["how"] = k, "small model"


# ---------------------------------------------------------------- run
def run():
    t_start = now()
    names, held, keeps = universe()
    quant = (rj("state/quant.json", {}) or {}).get("assets") or {}
    seen = rj("state/news/seen.json", {}) or {}
    cikmap = {}
    if not OFFLINE:
        try:
            for v in get("https://www.sec.gov/files/company_tickers.json", SEC_UA).values():
                cikmap[str(v.get("ticker")).upper()] = int(v.get("cik_str"))
        except Exception:
            pass
    raw = []
    for t in names:
        raw += from_headlines(t)
        raw += from_sec(t, cikmap)
    raw += from_analysts(names)
    raw += from_reads()
    cal = macro_calendar() if not OFFLINE else (rj("state/news/macro.json", {}) or {})
    raw += from_macro(cal)
    raw += from_sector(held)
    items, dups = dedupe(raw, seen)
    b = budget()
    for x in items:
        x["type"], x["how"] = classify(x)
    sort_new(items, b)
    now_ = now()
    for x in items:
        x.update(scores(x, names, held, quant, now_))
        x["held"] = x["tickers"][0] in held
        x["keep"] = x["tickers"][0] in keeps
        p = pdate(x.get("published"))
        x["delay_h"] = None if (not p or x.get("day_only")) else round((pdate(x["first_seen"]) - p).total_seconds() / 3600.0, 1)
        if x["delay_h"] is not None and x["delay_h"] > 72:
            x["delay_h"], x["backfill"] = None, True
    # keep 30 days of items; older first-seen marks are dropped too
    old = rj("state/news/items.json", {}) or {}
    keep = dict((x["id"], x) for x in old.get("items") or [] if str(x.get("first_seen", ""))[:10] >= (now_ - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d"))
    for x in items:
        if x["id"] in keep:
            x["first_seen"] = keep[x["id"]].get("first_seen", x["first_seen"])
            for k in ("thesis", "thesis_how", "past"):
                if keep[x["id"]].get(k) is not None:
                    x[k] = keep[x["id"]][k]
        keep[x["id"]] = x
    allx = sorted(keep.values(), key=lambda x: (-x["importance"], x["first_seen"]))
    seen = dict((k, v) for k, v in seen.items() if v[:10] >= (now_ - datetime.timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d"))
    wj("state/news/seen.json", seen)
    # the event study's past-cases line on every item
    study = (rj("state/news/event_study.json", {}) or {}).get("types") or {}
    for x in allx:
        x["past"] = past_line(x, study)
    wj("state/news/items.json", {"as_of": iso(), "items": allx, "sources": SOURCES, "method": method()})
    wj("state/news/budget.json", b)
    stats(allx, dups, len(raw), t_start)
    return allx


def past_line(x, study):
    key = x["type"]
    if x["source"] == "sec" and "2.02" in (x.get("items") or []):
        key = "earnings"
    s = study.get(key) or {}
    h = s.get("5d") or {}
    if not h.get("n"):
        return {"text": "Past cases like this: not measured yet for %s." % key, "n": 0}
    few = " (too few cases to rely on)" if h["n"] < 20 else ""
    return {"text": "Past cases like this (%s, 5 trading days, against the S&P 500 fund): typical move %+.1f%%, range %+.1f%% to %+.1f%%, %s cases%s." % (
        key, 100 * h["median"], 100 * h["p10"], 100 * h["p90"], "{:,}".format(h["n"]), few), "n": h["n"], "median": h["median"], "p10": h["p10"], "p90": h["p90"], "type": key}


def method():
    return ("Collected by plain code from the sources listed; exact and near duplicates (60% shared words, same company, 3 days) removed; "
            "event type from SEC 8-K item codes or headline word rules, a small model only for new headlines the rules leave unsorted; "
            "relevance = 0.5 + twice the holding's share of the portfolio for holdings (0.3 for watchlist and ideas, 0.45 macro, 0.35 sector); "
            "novelty halves every 48 hours and drops when the share has already moved more than two usual daily moves; "
            "reliability by source (SEC 1.0, analyst data 0.8, wires 0.7, opinion sites 0.3); tone from finance word lists (-1 to +1); "
            "importance = relevance x reliability x novelty x (0.5 + half the tone's size) x the event type's weight. Estimates, not forecasts.")


def stats(items, dups, raw_n, t_start):
    day = now().strftime("%Y-%m-%d")
    week = [x for x in items if x["first_seen"][:10] >= (now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")]
    by = {}
    for x in week:
        s = by.setdefault(x["source"], {"items": 0, "important": 0, "delays": []})
        s["items"] += 1
        s["important"] += 1 if x["importance"] >= IMPORTANT else 0
        if x.get("delay_h") is not None:
            s["delays"].append(x["delay_h"])
    for s in by.values():
        d = sorted(s.pop("delays"))
        s["per_day"] = round(s["items"] / 7.0, 1)
        s["median_delay_h"] = d[len(d) // 2] if d else None
    led = [c for c in (rj("state/decisions.json", {}) or {}).get("cards") or [] if c.get("news_ids")]
    st = rj("state/news/stats.json", {}) or {}
    hist = [h for h in st.get("runs") or [] if h.get("day") != day][-30:] + [{"day": day, "raw": raw_n, "kept": len(items), "duplicates": dups}]
    wj("state/news/stats.json", {"as_of": iso(), "by_source": by, "runs": hist, "cards_from_news": len(led), "seconds": round((now() - t_start).total_seconds(), 1),
                                 "note": "Delay = when we first saw an item minus when the source stamped it; only sources with a time stamp (SEC filings, analyst changes). Headlines carry the day only."})


def today_block(items, files=None):
    """At most five items for TODAY: important, new in the last 3 days, one per company, what it means for the money."""
    snap = rj("treasury/snapshot.json", {}) or {}
    pos = dict((p["ticker"], p) for p in snap.get("positions") or [] if p.get("ticker"))
    out, used = [], set()
    cut = (now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    for x in items:
        if x["importance"] < IMPORTANT or x["first_seen"][:10] < cut or x.get("dup_of") or x["tickers"][0] in used:
            continue
        t = x["tickers"][0]
        p = pos.get(t)
        past = x.get("past") or {}
        if p and past.get("n"):
            mv = float(p.get("market_value") or 0)
            money = "You hold $%.0f of %s. If it moves like past cases: %+.0f dollars typical, %+.0f to %+.0f dollars range (estimate)." % (mv, t, mv * past["median"], mv * past["p10"], mv * past["p90"])
        elif p:
            money = "You hold $%.0f of %s." % (float(p.get("market_value") or 0), t)
        elif t == "MARKET":
            money = "Affects the whole portfolio; no single holding."
        else:
            money = "You do not hold %s; it is on your watchlist or among the ideas." % t
        th = x.get("thesis")
        out.append({"id": x["id"], "ticker": t, "title": x["title"], "url": x.get("url"), "type": x["type"], "source": SOURCES.get(x["source"], {}).get("name", x["source"]),
                    "scores": {k: x[k] for k in ("relevance", "novelty", "reliability", "tone", "importance")}, "money": money, "past": past.get("text"),
                    "thesis": th, "keep": x.get("keep"), "first_seen": x["first_seen"]})
        used.add(t)
        if len(out) >= TOP_N:
            break
    wj("state/news/today.json", {"as_of": iso(), "items": out, "rule": "At most %d items: importance %.2f or more, first seen in the last 3 days, one per company." % (TOP_N, IMPORTANT)})
    return out


if __name__ == "__main__":
    xs = run()
    try:
        import files
        files.run(xs)
    except Exception as e:
        print("files: not built this run (%s: %s)" % (type(e).__name__, str(e)[:120]))
    xs = (rj("state/news/items.json", {}) or {}).get("items") or xs
    top = today_block(xs)
    b = rj("state/news/budget.json", {}) or {}
    print("news ok: %d items kept, %d for TODAY; model spend today $%.3f of $%.2f cap" % (len(xs), len(top), sum((b.get("spent") or {}).values()), sum(CAP_USD.values())))
