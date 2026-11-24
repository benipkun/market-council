"""Which release does Rollback go to? (24 Nov 2026)
The release before the one that is live, skipping any release already rolled back from (tag bad-<release>).
Prints "<target> <current or ->". Used by .github/workflows/rollback.yml."""
import subprocess
import sys

PATHS = ["index.html", "sw.js", "mc", "ops", "tests"]


def pick(tags, head_sig, sig_of, bad):
    """tags newest first. Returns (release to go to or None, the release that is live or None)."""
    current = next((t for t in tags if sig_of(t) == head_sig), None)
    start = tags.index(current) + 1 if current else 0
    for t in tags[start:]:
        if t not in bad and sig_of(t) != head_sig:
            return t, current
    return None, current


def sig(ref):
    return subprocess.check_output(["git", "ls-tree", ref, "--"] + PATHS, text=True)


if __name__ == "__main__":
    names = subprocess.check_output(["git", "tag", "--list"], text=True).split()
    rel = sorted([n for n in names if n.startswith("release-")], reverse=True)
    bad = set(n[4:] for n in names if n.startswith("bad-"))
    target, cur = pick(rel, sig("HEAD"), sig, bad)
    if not target:
        sys.exit("No earlier release to go back to.")
    print(target, cur or "-")
