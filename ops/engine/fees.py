"""The one fee schedule (Ben, 24 Nov 2026): the first 10 trades of a calendar month are free, then 2 cents a trade.
The monthly reset is assumed from how Revolut plans work. The lab's back-tests keep 0.25% as a deliberate stress test."""
FREE_TRADES = 10
AFTER_FREE = 0.02


def trades_in_month(entries, day):
    """Real buys and sells applied in the month of day (YYYY-MM-DD); undone or rejected entries do not count."""
    return len([e for e in entries or [] if e.get("action") in ("buy", "sell") and e.get("status") == "applied"
                and not e.get("undone_by") and str(e.get("at") or "")[:7] == str(day)[:7]])


def fee_now(used):
    return 0.0 if used < FREE_TRADES else AFTER_FREE
