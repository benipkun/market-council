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
                       "click": msg.get("click") or "https://benipkun.github.io/market-council/", "tags": msg.get("tags") if isinstance(msg.get("tags"), list) else []}).encode("utf-8")
    for i in range(5):
        try:
            req = urllib.request.Request("https://ntfy.sh/", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except Exception:
            time.sleep(6)
    return 0


def read_sent(log):
    """The names on the list, or None when there is no usable list (missing or emptied): then nothing is resent."""
    if not os.path.exists(log):
        return None
    words = [w for w in open(log, encoding="utf-8").read().split() if w not in ("#", "sent")]
    text = open(log, encoding="utf-8").read()
    if not text.strip():
        return None
    return set(w[4:] if w.startswith("bad:") else w for w in words)


def mark(log, name):
    with open(log, "a", encoding="utf-8", newline="") as f:
        f.write(name + "\n")


def run(root=".", send=post):
    q = os.path.join(root, "outbox", "queue")
    log = os.path.join(root, "outbox", "sent.txt")
    names = [os.path.basename(p) for p in glob.glob(os.path.join(q, "*.json"))]
    sent = read_sent(log)
    if sent is None:
        with open(log, "w", encoding="utf-8", newline="") as f:
            f.write("# sent\n" + "".join(n + "\n" for n in sorted(names)))
        return []
    failed = []
    for n in pending(names, sent):
        try:
            msg = json.load(open(os.path.join(q, n), encoding="utf-8"))
            if not isinstance(msg, dict):
                raise ValueError
        except Exception:
            mark(log, "bad:" + n)          # a file that can never be sent is not retried for ever
            print("one unreadable message skipped")
            continue
        try:
            ok = send(n, msg) == 200
        except Exception:
            ok = False
        if ok:
            mark(log, n)
            print("sent one message")
        else:
            failed.append(n)
    return failed


if __name__ == "__main__":
    if not os.environ.get("NTFY_OUT"):
        sys.exit("The phone channel secret is not set, so nothing was sent.")
    bad = run(".")
    if bad:
        print("%d messages not delivered; they go out with the next run" % len(bad))
        sys.exit(1)
