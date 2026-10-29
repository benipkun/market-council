"""Review board: the plain-code half. Standard library only.

Ben, 29 Oct 2026: a standing board of twelve strict peers inspects the real app and its real results on a fixed
schedule, finds flaws, and the app fixes them (safe lane on its own after tests pass; money logic, data sources,
spending, privacy and standing decisions only after his yes), tests the fixes and gets re-judged.

The judging is done by the Review Board routine (ops/BOARD.md in the records). This file does the parts that must
not depend on judgement:
  evidence     gather only real records into state/board/evidence.json (never plans or intentions)
  answers      read Ben's yes/no on approval cards from answers/*.json into state/board/cards.json
  close N      after cycle N's minutes are written: check them (twelve reviews, budget, accepted fixes), rebuild the
               scoreboard, run the reality check (board happy while results get worse = the board is wrong), and
               queue one phone message that names no share and no amount
"""
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.environ.get("MC_ROOT", ".")
BUDGET = {"fixes": 5, "cards": 3, "minutes": 90}   # each cycle stays inside this; the minutes record what it used
PEERS = 12


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


def git_log(grep, days=7):
    try:
        out = subprocess.run(["git", "-C", ROOT, "log", "--since=%d.days" % days, "--format=%cI %s", "--grep", grep],
                             capture_output=True, text=True, timeout=30).stdout
        return [l for l in out.splitlines() if l.strip()]
    except Exception:
        return None


def ci_runs(n=30):
    # the public code repository's last runs: names, results and dates only
    try:
        req = urllib.request.Request("https://api.github.com/repos/benipkun/market-council/actions/runs?per_page=%d" % n, headers={"Accept": "application/vnd.github+json"})
        rows = json.load(urllib.request.urlopen(req, timeout=20)).get("workflow_runs") or []
        return [{"name": r.get("name"), "result": r.get("conclusion") or r.get("status"), "at": r.get("created_at")} for r in rows]
    except Exception as e:
        return {"unreachable": type(e).__name__}


def evidence(now=None):
    now = now or now_iso()
    st = rj("state/partners/statement.json", {}) or {}
    track = rj("state/track.json", {}) or {}
    health = rj("state/health.json", {}) or {}
    msgs = (rj("state/messages.json", {}) or {}).get("messages") or []
    shots = rj("state/board/shots/latest/report.json", None)
    issues = [i for i in (rj("state/board/issues.json", {}) or {}).get("issues") or [] if i.get("status") == "open"]
    runs = ci_runs()
    ev = {
        "as_of": now,
        "track_record": {"verdict": track.get("verdict"), "ideas": track.get("count"), "since": track.get("first"),
                         "to_date": (track.get("all") or {}).get("now"), "by_horizon": dict((k, (track.get("all") or {}).get(k)) for k in ("1m", "3m", "6m", "12m"))},
        "real_money_vs_index": st.get("against_index"), "bottom_line": st.get("bottom_line"),
        "forecasts": st.get("forecasts"),
        "stops_and_targets": [dict((k, r.get(k)) for k in ("id", "name", "cases", "take_profit_first", "stop_first", "time_limit", "with_plan", "without_plan"))
                              for r in (rj("state/plans_backtest.json", {}) or {}).get("rules") or []],
        "jobs": {"health": {"problems": health.get("problems"), "jobs": health.get("jobs"), "data": health.get("data"), "alerts": health.get("alerts"),
                            "token_expires": health.get("token_expires")},
                 "failure_alerts_7d": git_log("Alert: a job failed"), "ci_runs": runs},
        "stale_data": [d for d in health.get("data") or [] if d.get("stale")],
        "tests": {"question_tests": dict((k, (rj("state/questions_eval.json", {}) or {}).get(k)) for k in ("as_of", "passed", "of")),
                  "ci_tests": [r for r in runs if isinstance(runs, list) and r["name"] in ("Tests", "Question tests")][:6] if isinstance(runs, list) else runs},
        "last_answers": [dict((k, m.get(k)) for k in ("at", "kind", "q", "question", "answer", "text", "status") if m.get(k) is not None) for m in msgs[-6:]],
        "costs": {"running": st.get("running_costs"), "questions": (rj("state/questions_eval.json", {}) or {}).get("cost")},
        "self_checks": {"action_list": ((rj("state/actions.json", {}) or {}).get("self_check") or {}).get("removed"),
                        "trades": [dict((k, t.get(k)) for k in ("at", "action", "ticker", "status")) for t in (rj("state/exposure.json", {}) or {}).get("trades") or []][:5]},
        "screenshots": shots or {"missing": "no screenshots yet: the Board screenshots job has not run"},
        "open_issues": issues,
        "honesty": "Only records are listed here. A reviewer who cites anything else must say so.",
    }
    wj("state/board/evidence.json", ev)
    return ev


def answers():
    # Ben's yes or no on approval cards, written by the BOARD page to answers/<stamp>-board-<id>.json
    cards = rj("state/board/cards.json", {"cards": []}) or {"cards": []}
    by = dict((c["id"], c) for c in cards.get("cards") or [])
    for p in sorted(glob.glob(os.path.join(ROOT, "answers", "*.json"))):
        try:
            a = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        if a.get("kind") == "board" and a.get("id") in by and a.get("answer") in ("yes", "no") and by[a["id"]].get("status") == "waiting":
            by[a["id"]].update(status=a["answer"], answered_at=a.get("at"))
    wj("state/board/cards.json", cards)
    return cards


def reality(track, statement):
    # the measures the board must not contradict: results against the index, forecast error, failed jobs
    t = (track.get("all") or {}).get("now") or {}
    f = statement.get("forecasts") or {}
    a = statement.get("against_index") or {}
    return {"ideas_vs_index": t.get("vs_spy"), "ideas_vs_random": t.get("vs_list"), "real_money_vs_index": a.get("ahead_of_index"),
            "forecast_error": f.get("error"), "forecast_error_always_50": f.get("error_always_50"), "forecasts_checked": f.get("checked")}


def worse(a, b):
    # True when reality got worse from cycle a to cycle b on a measure both cycles have
    out = []
    for k, bad_if_up in (("ideas_vs_index", False), ("real_money_vs_index", False), ("forecast_error", True)):
        x, y = (a or {}).get(k), (b or {}).get(k)
        if x is not None and y is not None and ((y > x) if bad_if_up else (y < x)):
            out.append(k)
    return out


MONEY = re.compile(r"\$\s?[\d,.]+|\b\d[\d,.]*\s?(HUF|USD|EUR)\b")


def phone_text(c, prev, issues, cards):
    avg = c["avg"]
    ch = "" if prev is None else (" (%+.1f)" % (avg - prev["avg"]))
    worst = [i for i in sorted([i for i in issues if i.get("status") == "open"], key=lambda i: (-int(i.get("severity") or 0), -len(i.get("raised_by") or [])))][:3]
    fixed = len([f for f in c.get("fixes") or [] if f.get("accepted")])
    waiting = len([k for k in cards if k.get("status") == "waiting"])
    words = "; ".join("%d) %s" % (n + 1, i.get("phone_title") or i.get("title")) for n, i in enumerate(worst))
    msg = "Board cycle %d: average %.1f/10%s. Worst open: %s. Fixed on its own: %d. Waiting for your yes: %d. Minutes: SYSTEM > BOARD." % (
        c["n"], avg, ch, words or "none", fixed, waiting)
    return MONEY.sub("[amount]", msg)


def check_minutes(c):
    # the minutes must hold twelve written reviews, a cross-examination, and stay inside the budget
    probs = []
    peers = c.get("peers") or []
    if len(peers) != PEERS:
        probs.append("%d reviews, not %d" % (len(peers), PEERS))
    for p in peers:
        if not p.get("checked"):
            probs.append("%s does not say what was checked" % p.get("name"))
        if not (p.get("worst") or {}).get("evidence"):
            probs.append("%s gives no evidence for the worst flaw" % p.get("name"))
        if not isinstance(p.get("score"), (int, float)) or not 1 <= p["score"] <= 10:
            probs.append("%s has no score from 1 to 10" % p.get("name"))
    if len(c.get("cross") or []) < PEERS:
        probs.append("cross-examination has %d entries, not %d" % (len(c.get("cross") or []), PEERS))
    used = (c.get("budget") or {}).get("used") or {}
    for k, lim in BUDGET.items():
        if (used.get(k) or 0) > lim:
            probs.append("over budget: %s %s of %s" % (k, used.get(k), lim))
    return probs


def close(n, now=None):
    now = now or now_iso()
    c = rj("state/board/cycles/%d.json" % n)
    if not c:
        raise SystemExit("no minutes for cycle %d" % n)
    probs = check_minutes(c)
    issues = (rj("state/board/issues.json", {}) or {}).get("issues") or []
    cards = (answers().get("cards") or [])
    sb = rj("state/board/scoreboard.json", {"cycles": []}) or {"cycles": []}
    prev = next((x for x in reversed(sb["cycles"]) if x["n"] < n), None)
    # a re-score counts once the fixes are in; the first written score is kept as well
    scores = dict((p["id"], p.get("rescore") if p.get("rescore") is not None else p["score"]) for p in c.get("peers") or [])
    first = dict((p["id"], p["score"]) for p in c.get("peers") or [])
    avg = round(sum(scores.values()) / len(scores), 2) if scores else 0.0
    real = reality(rj("state/track.json", {}) or {}, rj("state/partners/statement.json", {}) or {})
    flag = None
    if prev:
        got_worse = worse(prev.get("reality"), real)
        if avg > prev["avg"] and got_worse:
            flag = "The board's average rose while %s got worse: the board is wrong and must tighten its scores next cycle." % ", ".join(got_worse)
        drops = [k for k, v in scores.items() if k in (prev.get("scores") or {}) and v < prev["scores"][k]]
        c["score_drops"] = drops
    row = {"n": n, "date": c.get("date") or now[:10], "avg": avg, "avg_first": round(sum(first.values()) / len(first), 2) if first else 0.0,
           "scores": scores, "first_scores": first,
           "opened": len([i for i in issues if i.get("first_cycle") == n]), "closed": len([i for i in issues if i.get("closed_cycle") == n]),
           "open_total": len([i for i in issues if i.get("status") == "open"]), "reality": real, "board_wrong": flag, "minutes_problems": probs,
           "budget": c.get("budget")}
    wj("state/board/latest.json", dict(c, closed_at=now))
    sb["cycles"] = [x for x in sb["cycles"] if x["n"] != n] + [row]
    sb["cycles"].sort(key=lambda x: x["n"])
    sb["as_of"] = now
    wj("state/board/scoreboard.json", sb)
    text = phone_text(row, prev, issues, cards)
    if flag:
        text = MONEY.sub("[amount]", text + " Warning: " + flag)
    wj("outbox/queue/%s-board.json" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
       {"title": "Market Council: board cycle %d" % n, "message": text, "click": "https://benipkun.github.io/market-council/#board", "tags": ["clipboard"]})
    return row, text


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "evidence":
        e = evidence()
        print("evidence: %d open issues, screenshots %s" % (len(e["open_issues"]), "yes" if "shots" in (e["screenshots"] or {}) else "no"))
    elif cmd == "answers":
        print("cards: %d" % len(answers().get("cards") or []))
    elif cmd == "close" and len(sys.argv) > 2:
        r, t = close(int(sys.argv[2]))
        print("cycle %d closed: average %.2f, %s" % (r["n"], r["avg"], "minutes OK" if not r["minutes_problems"] else "; ".join(r["minutes_problems"])))
    else:
        print(__doc__)
