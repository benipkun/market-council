"""Delivers the phone messages in outbox/queue/ (24 Nov 2026). It sends every message not yet in outbox/sent.txt, so a
message survives a cancelled or failed job and goes out with the next run. The channel name comes from the secret
NTFY_OUT and is never printed. A first run with no list marks the existing history as sent instead of resending it."""
import glob
import json
import os
import sys
import time
import urllib.request


def pending(names, sent):
    if sent is None:
        return []
    return [n for n in sorted(names) if n not in sent]


def post(name, msg):
    body = json.dumps({"topic": os.environ["NTFY_OUT"], "title": msg.get("title") or "Market Council", "message": msg.get("message") or "",
                       "click": msg.get("click") or "https://benipkun.github.io/market-council/", "tags": msg.get("tags") or []}).encode("utf-8")
    for i in range(5):
        try:
            req = urllib.request.Request("https://ntfy.sh/", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except Exception:
            time.sleep(6)
    return 0


def run(root=".", send=post):
    q = os.path.join(root, "outbox", "queue")
    log = os.path.join(root, "outbox", "sent.txt")
    names = [os.path.basename(p) for p in glob.glob(os.path.join(q, "*.json"))]
    sent = set(open(log, encoding="utf-8").read().split()) if os.path.exists(log) else None
    if sent is None:
        with open(log, "w", encoding="utf-8", newline="") as f:
            f.write("".join(n + "\n" for n in sorted(names)))
        return []
    failed = []
    for n in pending(names, sent):
        try:
            msg = json.load(open(os.path.join(q, n), encoding="utf-8"))
        except Exception:
            failed.append(n)
            continue
        if send(n, msg) == 200:
            with open(log, "a", encoding="utf-8", newline="") as f:
                f.write(n + "\n")
            print("sent one message")
        else:
            failed.append(n)
    return failed


if __name__ == "__main__":
    bad = run(".")
    if bad:
        print("%d messages not delivered; they go out with the next run" % len(bad))
        sys.exit(1)
