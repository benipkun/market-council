"""Running cost for today, for the SYSTEM screen (Ben, 10 Nov 2026: "show the daily cost on SYSTEM").

Two kinds of cost, kept apart because only one of them is a bill:
  - Claude routines run on Ben's Claude plan: no per-call bill, but every run uses the plan's limits. Counted from the
    records' own history (each routine commits under its own name), so the numbers are counts, not estimates, except the
    skipped pipeline cycles and the Trade Inbox starts, which are worked out from the schedule and the pushes (labelled).
  - Paid API calls (ops/engine/answer.py, only once an API key is set): dollars, from state/agents/spend.json.
Standard library only.
"""
import datetime
import json
import os
import re
import subprocess

ROOT = os.environ.get("MC_ROOT", ".")
PIPE_HOURS = (6, 7, 9, 11, 13, 14, 16, 18, 20, 21, 23)   # the Hourly Pipeline's weekday schedule (UTC)
ROUTINES = [  # name, model, commit subject pattern
    ("Hourly Pipeline", "Sonnet 5", r"^Market Council hourly cycle"),
    ("Trade Inbox", "Sonnet 5", r"^Trade [Ii]nbox"),
    ("Daily Books", "account default", r"^Daily Books"),
    ("Review Board", "account default", r"^Review [Bb]oard"),
    ("Partner Meeting", "account default", r"^Partner"),
    ("Earnings Reader", "account default", r"^Earnings read"),
]


def rj(rel, d=None):
    try:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return d


def commits_today(day):
    try:
        out = subprocess.run(["git", "-C", ROOT, "log", "--since=%sT00:00:00Z" % day, "--format=%an|%s"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    return [ln.split("|", 1) for ln in out.splitlines() if "|" in ln]


def run(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    day = now.strftime("%Y-%m-%d")
    cs = commits_today(day)
    rows = []
    if cs is not None:
        for name, model, pat in ROUTINES:
            n = sum(1 for a, s in cs if re.search(pat, s))
            rows.append({"name": name, "model": model, "worked": n})
        weekday = now.weekday() < 5
        slots = sum(1 for h in PIPE_HOURS if weekday and h <= now.hour)
        pipe = rows[0]
        pipe["started"] = max(slots, pipe["worked"])
        pipe["skipped"] = max(0, slots - pipe["worked"])
        pipe["note"] = "%d of %d scheduled cycles did the full work; %d stopped at the cost gate (worked out from the schedule)" % (pipe["worked"], pipe["started"], pipe["skipped"])
        inbox = rows[1]
        inbox["started"] = len(cs) + (1 if now.hour >= 5 else 0)
        inbox["note"] = "started by each of today's %d pushes (an upper bound) and once a day; %d had work, the rest stopped at its gate within seconds" % (len(cs), inbox["worked"])
    spend = ((rj("state/agents/spend.json", {}) or {}).get("days") or {}).get(day) or {}
    usd = float(spend.get("usd") or spend.get("total") or 0) if isinstance(spend, dict) else float(spend or 0)
    full = sum(r.get("worked", 0) for r in rows)
    started = sum(r.get("started", r.get("worked", 0)) for r in rows)
    text = ("Today: %d Claude routine runs did work and about %d more stopped at a cheap gate (they use your Claude plan's limits, not a per-call bill); paid API calls $%.2f." % (full, max(0, started - full), usd)) if rows else "Run counts unavailable today."
    out = {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "day": day, "routines": rows, "api_usd": round(usd, 4), "api_note": "answer.py calls the paid API only once an API key is set; caps $2 a day, $20 a month",
           "text": text, "method": "Counts come from today's commits in the private records (each routine commits under its own name). Skipped pipeline cycles = scheduled slots so far minus full cycles. Trade Inbox starts = today's pushes plus its daily run. Routine runs have no per-call price on a Claude plan; the dollar figure is the paid API only."}
    with open(os.path.join(ROOT, "state", "costs.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    return out


if __name__ == "__main__":
    print(run()["text"])
