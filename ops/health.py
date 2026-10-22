# Market Council health check. Plain code, no AI.
# Run by .github/workflows/watch.yml every half hour, next to the private records. It asks GitHub when each job last
# ran and how it ended, reads the dates inside the records, and works out three things:
#   late   a job did not run when it was due (a skipped run), or has not succeeded since
#   stale  a file of results or a routine's output is older than its limit, counting weekday hours only
#   held   the price cross-check is holding cards back
# It writes state/health.json (shown on the SYSTEM screen) and sends one phone message when a problem starts, a reminder
# once a day while it lasts, and one message when it is over. Messages never contain amounts or holdings.
import datetime
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GITHUB_REPOSITORY") or "benipkun/market-council"
APP = "https://benipkun.github.io/market-council/#system"
UTC = datetime.timezone.utc
NL = chr(10)

# times are UTC on weekdays; grace_h is how long after its time a run may still start before it counts as skipped
# (GitHub starts scheduled jobs late, sometimes by hours)
JOBS = [
    {"id": "engine", "file": "engine.yml", "name": "Calculation engine", "times": ("06:40", "13:40", "21:40"), "grace_h": 5},
    {"id": "screen", "file": "screen.yml", "name": "Wide screen", "times": ("05:20",), "grace_h": 9},
    {"id": "history", "file": "history.yml", "name": "Back-checks", "times": ("23:10",), "grace_h": 6},
    {"id": "listen", "file": "listen.yml", "name": "Phone message pickup", "every_h": 8},
]
# limit_h counts weekday hours only, so a weekend never makes anything stale; "hours" limits when the check applies
DATA = [
    {"id": "pipeline", "name": "Market pipeline (hourly routine)", "path": "digests/latest.json", "limit_h": 5, "hours": (8, 23)},
    {"id": "books", "name": "Daily books (routine)", "path": "treasury/snapshot.json", "limit_h": 30},
    {"id": "quant", "name": "Engine results", "path": "state/quant.json", "limit_h": 16},
    {"id": "desk", "name": "Decision desk", "path": "state/decisions.json", "limit_h": 16},
    {"id": "screen", "name": "Wide screen results", "path": "state/screen.json", "limit_h": 34},
    {"id": "backcheck", "name": "Back-check results", "path": "state/backcheck.json", "limit_h": 34},
]
LOGS = ("engine", "research", "decide", "brief", "screen", "history")
REMIND_H = 24


def ts(s):
    try:
        t = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    except Exception:
        return None


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def nice(t):
    return t.astimezone(UTC).strftime("%a %d %b %H:%M UTC") if t else "never"


def weekday_hours(a, b):
    # hours between two moments, leaving out Saturdays and Sundays (UTC)
    if not a or not b or b <= a:
        return 0.0
    total, cur = 0.0, a
    while cur < b:
        nxt = min(b, datetime.datetime.combine(cur.date() + datetime.timedelta(days=1), datetime.time(0), tzinfo=UTC))
        if cur.weekday() < 5:
            total += (nxt - cur).total_seconds() / 3600.0
        cur = nxt
    return total


def last_due(times, grace_h, now):
    # the most recent weekday slot whose grace period is already over
    for back in range(0, 9):
        d = (now - datetime.timedelta(days=back)).date()
        if d.weekday() >= 5:
            continue
        for hm in sorted(times, reverse=True):
            slot = datetime.datetime.combine(d, datetime.time(int(hm[:2]), int(hm[3:])), tzinfo=UTC)
            if slot + datetime.timedelta(hours=grace_h) <= now:
                return slot
    return None


def judge_job(job, runs, now):
    # runs: GitHub's list for this job, newest first, each with created_at, status and conclusion
    done = [r for r in runs if r.get("status") == "completed" and r.get("conclusion") in ("success", "failure", "timed_out", "startup_failure")]
    ok = [r for r in done if r["conclusion"] == "success"]
    last, last_ok = (done[0] if done else None), (ok[0] if ok else None)
    ok_at = ts(last_ok["created_at"]) if last_ok else None
    out = {"id": job["id"], "name": job["name"], "last_ok": iso(ok_at), "last_run": last and last.get("created_at"),
           "last_result": last and ("ok" if last["conclusion"] == "success" else "failed"), "late": False, "due": None, "note": None}
    if job.get("times"):
        due = last_due(job["times"], job["grace_h"], now)
        out["due"] = iso(due)
        out["schedule"] = "weekdays at %s UTC" % ", ".join(job["times"])
        if due and (not ok_at or ok_at < due - datetime.timedelta(minutes=5)):
            out["late"] = True
            out["note"] = "did not run when due (%s); last good run %s" % (nice(due), nice(ok_at))
    else:
        out["schedule"] = "every few minutes; counted as late after %d hours without a good run" % job["every_h"]
        if not ok_at or (now - ok_at).total_seconds() > job["every_h"] * 3600:
            out["late"] = True
            out["note"] = "no good run for more than %d hours; last good run %s" % (job["every_h"], nice(ok_at))
    if not out["late"] and out["last_result"] == "failed":
        out["note"] = "the last run failed (%s); the results of the last good run stay in place" % nice(ts(last["created_at"]))
    return out


def judge_data(item, as_of, now):
    t = ts(as_of)
    out = {"id": item["id"], "name": item["name"], "as_of": iso(t), "limit_h": item["limit_h"], "stale": False, "age_h": None, "note": None}
    if not t:
        out["note"] = "no date found in the file"
        return out
    age = weekday_hours(t, now)
    out["age_h"] = round(age, 1)
    hrs = item.get("hours")
    if hrs and not (now.weekday() < 5 and hrs[0] <= now.hour < hrs[1]):
        out["note"] = "only checked on weekdays between %02d:00 and %02d:00 UTC" % hrs
        return out
    if age > item["limit_h"]:
        out["stale"] = True
        out["note"] = "%d weekday hours old; the limit is %d" % (round(age), item["limit_h"])
    return out


def assess(runs_by, dates, logs, price, old, now):
    # everything below is arithmetic on the inputs; reading files and calling GitHub happens in main()
    jobs = [judge_job(j, runs_by.get(j["id"]) or [], now) for j in JOBS]
    data = [judge_data(d, dates.get(d["id"]), now) for d in DATA]
    problems = []
    for j in jobs:
        if j["late"]:
            problems.append({"key": "job:%s:late" % j["id"], "alert": True, "text": "%s %s." % (j["name"], j["note"])})
        elif j["last_result"] == "failed":
            problems.append({"key": "job:%s:failed" % j["id"], "alert": False, "text": "%s: %s." % (j["name"], j["note"])})
    for d in data:
        if d["stale"]:
            problems.append({"key": "data:%s:stale" % d["id"], "alert": True, "text": "%s: %s." % (d["name"], d["note"])})
    held = len((price or {}).get("held") or [])
    if held:
        problems.append({"key": "price:held", "alert": True,
                         "text": "Price check: %d share%s failed the comparison with the second source; %s held back." % (
                             held, "" if held == 1 else "s", "its cards are" if held == 1 else "their cards are")})
    for name, bad in sorted((logs or {}).items()):
        if bad:
            problems.append({"key": "script:%s" % name, "alert": False, "text": "The %s script reported an error in its last run." % name})
    alerts, send = dict((old or {}).get("alerts") or {}), []
    live = set(p["key"] for p in problems if p["alert"])
    fresh = [p for p in problems if p["alert"] and p["key"] not in alerts]
    again = [p for p in problems if p["alert"] and p["key"] in alerts
             and (now - (ts(alerts[p["key"]].get("last_sent")) or now)).total_seconds() >= REMIND_H * 3600]
    if fresh or again:
        both = fresh + again
        send.append({"title": "Market Council: needs attention" if fresh else "Market Council: still not fixed",
                     "message": " ".join(p["text"] for p in both[:3]) + ("" if len(both) <= 3 else " And %d more." % (len(both) - 3)) + " Open SYSTEM in the app.",
                     "tag": "warning", "keys": [p["key"] for p in both]})
    over = sorted(k for k in alerts if k not in live)
    if over:
        send.append({"title": "Market Council: back to normal", "message": "%d earlier problem%s cleared: %s." % (
            len(over), "" if len(over) == 1 else "s", ", ".join(k.replace(":", " ") for k in over[:4])), "tag": "white_check_mark", "keys": []})
    first = dict((p["key"], p.get("since")) for p in ((old or {}).get("problems") or []))
    for p in problems:
        p["since"] = first.get(p["key"]) or iso(now)
    out = {"as_of": iso(now), "ok": not problems, "problems": problems, "jobs": jobs, "data": data,
           "price_check": {k: (price or {}).get(k) for k in ("as_of", "checked", "agree", "held", "one_source", "tolerance", "second_source")} if price else None,
           "alerts": {k: v for k, v in alerts.items() if k in live},
           "method": "A job is late when no good run started at or after its last due time, once the grace period is over. Results are stale when they are "
                     "older than their limit in weekday hours. Each problem is sent to the phone once, then once a day until it clears."}
    return out, send, over


def same(a, b):
    # has anything a reader would care about changed?
    def core(h):
        return json.dumps({"p": [x["key"] for x in (h or {}).get("problems") or []],
                           "j": [[x.get("last_ok"), x.get("last_result"), x.get("late")] for x in (h or {}).get("jobs") or []],
                           "d": [[x.get("as_of"), x.get("stale")] for x in (h or {}).get("data") or []],
                           "a": sorted(((h or {}).get("alerts") or {}).keys())}, sort_keys=True)
    return core(a) == core(b)


def rj(path, default=None):
    try:
        with open(os.path.join(ROOT, path), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def gh_runs(file):
    req = urllib.request.Request("https://api.github.com/repos/%s/actions/workflows/%s/runs?per_page=40" % (REPO, file),
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "market-council-health",
                                          "Authorization": "Bearer " + os.environ.get("GH_TOKEN", "")})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("workflow_runs") or []


def push(m):
    """Phone messages leave through the private records: a file in outbox/queue/ is sent by the
    "Send phone messages" job there, which holds the channel name."""
    try:
        d = os.path.join(ROOT, "outbox", "queue")
        os.makedirs(d, exist_ok=True)
        stamp = datetime.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        n = len([x for x in os.listdir(d) if x.startswith(stamp)])
        with open(os.path.join(d, "%s-health%s.json" % (stamp, "-%d" % n if n else "")), "w", encoding="utf-8") as f:
            json.dump({"title": m["title"], "message": m["message"][:900], "click": APP, "tags": [m["tag"]]}, f, indent=1)
            f.write(NL)
        return "sent"
    except Exception as e:
        return "not sent: %s" % type(e).__name__


def main():
    now = ts(os.environ.get("MC_NOW")) or datetime.datetime.now(UTC)
    old = rj("state/health.json", {}) or {}
    runs_by, api_note = {}, None
    for j in JOBS:
        try:
            runs_by[j["id"]] = gh_runs(j["file"])
        except Exception as e:
            api_note = "GitHub did not answer for %s (%s)" % (j["file"], type(e).__name__)
    if api_note and len(runs_by) < len(JOBS):
        # without the run list a job would wrongly look late, so nothing is judged or sent this time
        print("health: skipped,", api_note)
        return 0
    dates = dict((d["id"], (rj(d["path"], {}) or {}).get("as_of")) for d in DATA)
    logs = {}
    for name in LOGS:
        try:
            with open(os.path.join(ROOT, "state", "logs", name + ".txt"), encoding="utf-8") as f:
                logs[name] = "Traceback" in f.read()
        except Exception:
            logs[name] = False
    price = (rj("state/decisions.json", {}) or {}).get("price_check")
    out, send, over = assess(runs_by, dates, logs, price, old, now)
    # the records token has an expiry date; when it lapses every job stops, so warn ten days ahead
    exp = (os.environ.get("TOKEN_EXPIRES") or "").strip()
    if exp:
        out["token_expires"] = exp
        try:
            left = (datetime.date.fromisoformat(exp[:10]) - now.date()).days
        except ValueError:
            left = None
        if left is not None and left <= 10:
            text = ("The records token (MC_TOKEN) expires on %s, in %d days. Make a new one on GitHub and save it as MC_TOKEN in "
                    "both repositories, or every job stops." % (exp[:10], max(left, 0)))
            out["ok"] = False
            out["problems"].append({"key": "token", "text": text, "since": iso(now)})
            last = ((old.get("alerts") or {}).get("token") or {}).get("last_sent")
            if not last or (now - ts(last)).total_seconds() > 86400:
                send.append({"title": "Market Council: token expires soon", "message": text, "tag": "key", "keys": ["token"]})
    for m in send:
        note = push(m)
        print("phone:", m["title"], "-", note)
        if note == "sent":
            for k in m["keys"]:
                first = (old.get("alerts") or {}).get(k, {}).get("first") or iso(now)
                out["alerts"][k] = {"first": first, "last_sent": iso(now)}
    for k, v in (old.get("alerts") or {}).items():       # alerts that are still live keep their record
        if k in set(p["key"] for p in out["problems"]) and k not in out["alerts"]:
            out["alerts"][k] = v
    last = ts(old.get("as_of"))
    if same(old, out) and last and (now - last).total_seconds() < 3 * 3600:
        print("health: no change since", old.get("as_of"), "-", len(out["problems"]), "problems")
        return 0
    os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
    with open(os.path.join(ROOT, "state", "health.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
        f.write(NL)
    print("health:", "ok" if out["ok"] else "%d problems" % len(out["problems"]), "- written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
