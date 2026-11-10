"""What changed since the last pipeline cycle (Ben, 10 Nov 2026: "call Claude only when the plain-code engine sees a change").

Runs in the watch job at :07 and :37 every hour and writes state/changes.json. The hourly pipeline routine reads it first
and skips its whole cycle (no Claude analysis, no commit) when nothing changed and it has already run today. A change is:
a held share moving 2% or more, or a watched share moving 3% or more, against its price in the last digest; or an
earnings call since the last digest. Standard library only.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prices as P  # noqa: E402

ROOT = os.environ.get("MC_ROOT", ".")
MOVE_HELD, MOVE_WATCH = 0.02, 0.03


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def check(now=None, quote=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    quote = quote or P.quote
    dig = rj("digests/latest.json", {}) or {}
    since = str(dig.get("as_of") or "")
    tech = dig.get("technicals") or {}
    held = set(p.get("ticker") for p in (rj("treasury/snapshot.json", {}) or {}).get("positions") or [] if p.get("ticker"))
    watch = set(str(x.get("ticker") if isinstance(x, dict) else x) for x in (rj("state/known_companies.json", {}) or {}).get("tickers") or [])
    reasons, moves, checked = [], {}, []
    for t in sorted(held | watch):
        then = (tech.get(t) or {}).get("price")
        if not then:
            continue
        try:
            px = float(quote(t)[0] or 0)
        except Exception:
            px = 0
        if not px:
            continue
        checked.append(t)
        m = px / float(then) - 1
        moves[t] = round(m, 4)
        if abs(m) >= (MOVE_HELD if t in held else MOVE_WATCH):
            reasons.append("%s %s %.1f%% since the last cycle (%s)" % (t, "up" if m > 0 else "down", 100 * abs(m), "held" if t in held else "watched"))
    for r in (rj("state/earnings.json", {}) or {}).get("calendar") or []:
        d = str(r.get("date") or "")
        if r.get("ticker") in held | watch and since[:10] <= d <= now.strftime("%Y-%m-%d"):
            reasons.append("%s reported results on %s" % (r["ticker"], d))
    return {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "since": since or None, "changed": bool(reasons), "reasons": reasons,
            "moves": moves, "checked": checked, "rule": "A held share moving 2% or more, a watched share 3% or more, against its price in the last digest, or an earnings call since then. The pipeline also runs once every weekday whatever happens."}


def main():
    out = check()
    # every push to the records starts the Trade Inbox routine, so write only when the answer changes, or every 3 hours
    # to keep it fresh for the pipeline's gate (which accepts up to 4 hours)
    old = rj("state/changes.json", {}) or {}
    try:
        age = (datetime.datetime.now(datetime.timezone.utc) - datetime.datetime.fromisoformat(str(old.get("as_of")).replace("Z", "+00:00"))).total_seconds()
    except Exception:
        age = 1e9
    if old and old.get("changed") == out["changed"] and old.get("reasons") == out["reasons"] and age < 3 * 3600:
        print("changes: same as %s, not rewritten (%s)" % (old.get("as_of"), "CHANGED" if out["changed"] else "nothing new"))
        return
    with open(os.path.join(ROOT, "state", "changes.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("changes: %s (%d shares checked)%s" % ("CHANGED" if out["changed"] else "nothing new", len(out["checked"]), (": " + "; ".join(out["reasons"][:4])) if out["reasons"] else ""))


if __name__ == "__main__":
    main()
