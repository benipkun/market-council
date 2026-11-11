"""Company statements from the US filings database (SEC EDGAR companyfacts), for our own DCF.

Ben chose this source on 11 Nov 2026, after the earlier free source stopped answering GitHub's servers on 10 Nov.
It returns the annual figures our DCF reads, in the same table layout and units (thousands) as the earlier source,
so the model itself is unchanged. US filers (10-K) only; foreign companies that report in IFRS (20-F) are not covered.
The SEC asks for a contact in each request: the secret SEC_CONTACT (an email) is used when set. Standard library only.
"""
import json
import os
import urllib.request

UA = ("Market Council research " + os.environ["SEC_CONTACT"]) if os.environ.get("SEC_CONTACT") else "Mozilla/5.0 (Market Council research)"
_CIK = {}
TAGS = {
    "inc": [("Total Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax"]),
            ("Operating Income", ["OperatingIncomeLoss", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"])],
    "bal": [("Net Receivables", ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]),
            ("Long-Term Debt", ["LongTermDebtNoncurrent", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"]),
            ("Short-Term Debt / Current Portion of Long-Term Debt", ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"]),
            ("Cash and Cash Equivalents", ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
            ("Short-Term Investments", ["ShortTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecuritiesCurrent"])],
    "cf": [("Capital Expenditures", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
           ("Depreciation", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet", "Depreciation"])],
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8"))


def cik(ticker):
    if not _CIK:
        for v in (get("https://www.sec.gov/files/company_tickers.json") or {}).values():
            _CIK[str(v.get("ticker")).upper()] = int(v.get("cik_str"))
    return _CIK.get(ticker.upper())


def annual(facts, tags, instant):
    """{fiscal year end date: value} from 10-K filings, full-year figures only (or year-end balances)."""
    usgaap = (facts.get("facts") or {}).get("us-gaap") or {}
    for t in tags:
        units = ((usgaap.get(t) or {}).get("units") or {}).get("USD") or []
        out = {}
        for u in units:
            if u.get("form") not in ("10-K", "10-K/A") or u.get("fp") != "FY":
                continue
            if not instant:
                try:
                    from datetime import date
                    days = (date.fromisoformat(u["end"]) - date.fromisoformat(u["start"])).days
                except Exception:
                    continue
                if not 350 <= days <= 380:
                    continue
            out[u["end"]] = u["val"]          # later filings of the same year overwrite earlier ones (restated figures)
        if len(out) >= 2:
            return out, t
    return {}, None


def shares_out(ticker):
    """Shares outstanding in thousands, from the cover page of the latest filing (dei), or None."""
    c = cik(ticker)
    if not c:
        return None
    dei = ((get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % c).get("facts") or {}).get("dei") or {})
    units = ((dei.get("EntityCommonStockSharesOutstanding") or {}).get("units") or {}).get("shares") or []
    last = sorted(units, key=lambda u: u.get("end") or "")[-1:] if units else []
    return float(last[0]["val"]) / 1000.0 if last else None


def financials(ticker):
    """The statements in the earlier source's layout (values in thousands), or None."""
    c = cik(ticker)
    if not c:
        return None
    facts = get("https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json" % c)
    rev, _ = annual(facts, TAGS["inc"][0][1], False)
    ends = sorted(rev, reverse=True)[:4]
    if len(ends) < 3:
        return None
    heads = {"value1": "Period Ending:"}
    for i, e in enumerate(ends):
        y, m, d = e.split("-")
        heads["value%d" % (i + 2)] = "%s/%s/%s" % (m, d, y)
    out, used = {"source": "SEC EDGAR companyfacts (10-K filings)", "cik": c}, {}
    for name, key in (("inc", "incomeStatementTable"), ("bal", "balanceSheetTable"), ("cf", "cashFlowTable")):
        rows = []
        for label, tags in TAGS[name]:
            vals, tag = annual(facts, tags, name == "bal")
            if not vals:
                continue
            used[label] = tag
            row = {"value1": label}
            for i, e in enumerate(ends):
                v = vals.get(e)
                if v is None:                    # balance dates can differ by a day or two from the income statement's
                    near = [k for k in vals if abs(int(k.replace("-", "")) - int(e.replace("-", ""))) <= 5]
                    v = vals.get(near[0]) if near else None
                row["value%d" % (i + 2)] = None if v is None else round(float(v) / 1000.0, 1)
            rows.append(row)
        out[key] = {"headers": heads, "rows": rows}
    out["tags"] = used
    return out
