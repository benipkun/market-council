"""The contradiction check (Ben, 4 Nov 2026: "a contradiction can never reach me again").

Runs after every engine run, once the brief is rebuilt. It reads what every screen shows (the decision cards, the
morning check, the order plans and their events), the brief and today's phone messages, and finds any buy or sell
wording that is not one of the actions in the one final answer (state/actions.json "final"), and any "do nothing"
next to an action. If it finds one, the run fails: the last good answer stays up marked STALE, the brief is rebuilt
with it, and the phone gets an alert. Standard library only.
"""
import datetime
import glob
import html
import json
import os
import re
import sys

ROOT = os.environ.get("MC_ROOT", ".")
LABELS = ("WATCHING", "PAPER ONLY", "REJECTED TODAY", "not a buy now", "not an action", "Not a buy now", "No orders")
ACTION = re.compile(r"\b(BUY|SELL|SWAP|Buy|Sell)\b(?:\s+[\d.,$]+(?:\s+of)?)?\s+([A-Z]{1,5})\b")
EXIT_WORDS = re.compile(r"\b(sell with a limit order|place a stop|buy at)\b", re.I)


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def scan(text, allowed, where, out):
    for line in re.split(r"[\n\r]+|(?<=\.)\s{2,}", str(text or "")):
        if any(w in line for w in LABELS):
            continue
        for m in ACTION.finditer(line):
            if m.group(2) not in allowed:
                out.append("%s says '%s' for %s, which is not in today's answer" % (where, m.group(0), m.group(2)))


def check(root=None):
    global ROOT
    if root:
        ROOT = root
    v = []
    acts = rj("state/actions.json", {}) or {}
    fin = acts.get("final") or {}
    if not fin.get("headline"):
        return ["the action list has no final answer"]
    allowed = set(fin.get("action_tickers") or [])
    keys = set(fin.get("action_keys") or [])
    nothing = fin["headline"].startswith("DO NOTHING")
    if nothing and fin.get("lines"):
        v.append("the answer says DO NOTHING TODAY but lists actions")
    if not nothing and not fin.get("lines"):
        v.append("the answer lists no action but does not say DO NOTHING TODAY")
    if nothing and allowed:
        v.append("the answer says DO NOTHING TODAY next to actions for %s" % ", ".join(sorted(allowed)))
    # the decision desk and the morning check
    dec = rj("state/decisions.json", {}) or {}
    for c in dec.get("cards") or []:
        if c.get("status") != "open":
            continue
        offered = not c.get("greyed")
        if offered and c.get("key") not in keys and c.get("kind") in ("idea", "buy", "sell", "rebalance"):
            v.append("card %s ('%s') offers a yes outside today's answer" % (c.get("id"), c.get("title")))
        if not offered and re.match(r"^\s*(Buy|Sell|BUY|SELL)\b", str(c.get("title") or "")):
            v.append("card %s is not in today's answer but its title says '%s'" % (c.get("id"), c.get("title")))
    action_ids = set(c.get("id") for c in dec.get("cards") or [] if c.get("key") in keys)
    for q in (dec.get("morning") or {}).get("questions") or []:
        if q.get("kind") == "decision" and q.get("id") not in action_ids:
            v.append("the morning check asks '%s', which is not in today's answer" % q.get("text"))
    # the order plans: no orders for ideas outside the answer; plan events that tell you to trade must match it
    plans = rj("state/plans.json", {}) or {}
    for p in plans.get("ideas") or []:
        if (p.get("revolut") or []) and not (p.get("verdict") or {}).get("buy"):
            v.append("the order plan for %s gives orders, but it is not in today's answer" % p.get("ticker"))
    kept = set((dec.get("keeps") or {}).keys())
    for e in plans.get("events") or []:
        t = str(e.get("id") or "").split(":")[-1]
        if EXIT_WORDS.search(str(e.get("text") or "")) and t not in allowed and t not in kept:
            v.append("a plan event says '%s', which is not in today's answer" % e.get("text"))
    # the brief: the answer word for word, and no other buy or sell
    try:
        raw = open(os.path.join(ROOT, "brief", "index.html"), encoding="utf-8").read()
        txt = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
        for line in fin["text"].split("\n"):
            if line.strip() and line.strip() not in txt:
                v.append("the brief does not show the answer line '%s'" % line[:80])
        scan(txt, allowed, "the brief", v)
    except FileNotFoundError:
        pass
    # today's phone messages
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    for p in glob.glob(os.path.join(ROOT, "outbox", "queue", today + "*.json")):
        m = rj(os.path.relpath(p, ROOT), {}) or {}
        if "contradiction" in str(m.get("title", "")).lower():
            continue
        scan(m.get("message"), allowed, "the phone message '%s'" % m.get("title"), v)
    return sorted(set(v))


def fail(v):
    # keep the last good answer, marked STALE; rebuild the brief with it; alert the phone
    acts = rj("state/actions.json", {}) or {}
    good = rj("state/actions_last_good.json", None)
    fin = dict((good or {}).get("final") or acts.get("final") or {})
    fin.update(stale=True, stale_note="The newest run contradicted itself (%d problem%s), so this is the last good answer." % (len(v), "" if len(v) == 1 else "s"))
    acts["final"] = fin
    acts["contradictions"] = v
    with open(os.path.join(ROOT, "state", "actions.json"), "w", encoding="utf-8") as f:
        json.dump(acts, f, indent=1)
        f.write("\n")
    d = os.path.join(ROOT, "outbox", "queue")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "%s-contradiction.json" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")), "w", encoding="utf-8") as f:
        json.dump({"title": "Market Council: contradiction found", "message": "The newest run contradicted itself, so the app shows the last good answer, marked STALE. Open TODAY.",
                   "click": "https://benipkun.github.io/market-council/#today", "tags": ["warning"]}, f, indent=1)
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
        import render_brief
        render_brief.main()
    except Exception:
        pass


def main():
    v = check()
    state = {"as_of": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": not v, "problems": v}
    with open(os.path.join(ROOT, "state", "consistency.json"), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
        f.write("\n")
    if v:
        fail(v)
        print("consistency: %d contradiction%s; the last good answer stays up, marked STALE" % (len(v), "" if len(v) == 1 else "s"))
        for x in v[:10]:
            print(" -", x)
        return 1
    acts = rj("state/actions.json", {}) or {}
    with open(os.path.join(ROOT, "state", "actions_last_good.json"), "w", encoding="utf-8") as f:
        json.dump({"as_of": acts.get("as_of"), "final": acts.get("final")}, f, indent=1)
        f.write("\n")
    print("consistency: ok, one answer everywhere: " + str((acts.get("final") or {}).get("headline")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
