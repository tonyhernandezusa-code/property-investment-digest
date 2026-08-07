#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import requests

OUTPUT = Path(__file__).with_name("stock-fundamentals.json")

SEC_CIKS = {
    "AAPL": 320193,
    "MSFT": 789019,
    "NVDA": 1045810,
    "GOOGL": 1652044,
    "AMZN": 1018724,
    "META": 1326801,
    "TSLA": 1318605,
    "AVGO": 1730168,
    "JPM": 19617,
    "V": 1403161,
    "MA": 1141391,
    "WMT": 104169,
    "LLY": 59478,
    "JNJ": 200406,
    "PG": 80424,
    "KO": 21344,
    "PEP": 77476,
    "ORCL": 1341439,
    "CSCO": 858877,
    "AMD": 2488,
    "INTC": 50863,
    "QCOM": 804328,
    "CAT": 18230,
    "HON": 773840,
    "UNP": 100885,
    "RTX": 101829,
    "LMT": 936468,
    "ABBV": 1551152,
    "MRK": 310158,
    "PLTR": 1321655,
}

TICKERS = list(SEC_CIKS.keys())

USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "PropertyInvestmentDigest/1.0 https://tonyhernandezusa-code.github.io/property-investment-digest/"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json,text/plain,*/*",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_json(url):
    last_error = None
    for attempt in range(6):
        try:
            response = SESSION.get(url, timeout=30)
            if response.status_code in (403, 429, 500, 502, 503, 504):
                last_error = requests.HTTPError(
                    f"{response.status_code} response from {url}",
                    response=response
                )
                time.sleep(min(30, 2 ** attempt))
                continue
            response.raise_for_status()
            time.sleep(0.40)
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(30, 2 ** attempt))
    raise last_error

def pct_change(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current / previous - 1) * 100

def choose_units(fact, preferred):
    units = fact.get("units", {})
    for unit in preferred:
        if unit in units:
            return units[unit], unit
    if units:
        key = next(iter(units))
        return units[key], key
    return [], None

def annual_series(companyfacts, tags, preferred_units=("USD",), limit=5):
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    rows = []
    used = set()
    for tag in tags:
        fact = usgaap.get(tag)
        if not fact:
            continue
        obs, unit = choose_units(fact, preferred_units)
        candidates = [
            x for x in obs
            if x.get("form") in ("10-K", "10-K/A")
            and x.get("fp") == "FY"
            and x.get("val") is not None
            and x.get("end")
        ]
        candidates.sort(key=lambda x: (x.get("fy") or 0, x.get("filed") or "", x.get("end") or ""), reverse=True)
        for x in candidates:
            key = x.get("fy") or x.get("end")
            if key in used:
                continue
            used.add(key)
            rows.append({
                "fy": x.get("fy"),
                "end": x.get("end"),
                "filed": x.get("filed"),
                "value": x.get("val"),
                "unit": unit,
                "tag": tag,
            })
        if rows:
            break
    rows.sort(key=lambda x: (x.get("fy") or 0, x.get("end") or ""), reverse=True)
    return rows[:limit]

def latest_instant(companyfacts, tags, preferred_units=("USD",)):
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        fact = usgaap.get(tag)
        if not fact:
            continue
        obs, unit = choose_units(fact, preferred_units)
        candidates = [
            x for x in obs
            if x.get("form") in ("10-K", "10-K/A", "10-Q", "10-Q/A")
            and x.get("val") is not None
            and x.get("end")
        ]
        candidates.sort(key=lambda x: (x.get("end") or "", x.get("filed") or ""), reverse=True)
        if candidates:
            x = candidates[0]
            return {
                "end": x.get("end"),
                "filed": x.get("filed"),
                "value": x.get("val"),
                "unit": unit,
                "tag": tag,
                "form": x.get("form"),
            }
    return None

def latest_annual_value(companyfacts, tags, preferred_units=("USD",)):
    series = annual_series(companyfacts, tags, preferred_units, limit=5)
    return (series[0] if series else None), (series[1] if len(series) > 1 else None), series

def recent_filings(submission, cik):
    recent = submission.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    allowed = {"10-K", "10-Q", "8-K", "20-F", "6-K"}
    result = []
    for i, form in enumerate(forms):
        if form not in allowed:
            continue
        accession = accessions[i] if i < len(accessions) else ""
        document = primary[i] if i < len(primary) else ""
        if not accession or not document:
            continue
        accession_compact = accession.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_compact}/{document}"
        result.append({
            "form": form,
            "filing_date": filing_dates[i] if i < len(filing_dates) else "",
            "report_date": report_dates[i] if i < len(report_dates) else "",
            "url": url,
        })
        if len(result) >= 12:
            break
    return result

def company_record(ticker, cik):
    cik10 = str(cik).zfill(10)
    facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json")
    sub = get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json")

    revenue, revenue_prev, revenue_hist = latest_annual_value(
        facts, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"], ("USD",)
    )
    net_income, net_income_prev, net_income_hist = latest_annual_value(
        facts, ["NetIncomeLoss", "ProfitLoss"], ("USD",)
    )
    eps, eps_prev, eps_hist = latest_annual_value(
        facts, ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"], ("USD/shares", "USD / shares")
    )
    operating_cf, _, operating_cf_hist = latest_annual_value(
        facts, ["NetCashProvidedByUsedInOperatingActivities"], ("USD",)
    )
    capex, _, capex_hist = latest_annual_value(
        facts, ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"], ("USD",)
    )

    assets = latest_instant(facts, ["Assets"], ("USD",))
    liabilities = latest_instant(facts, ["Liabilities"], ("USD",))
    equity = latest_instant(
        facts, ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], ("USD",)
    )
    cash = latest_instant(
        facts, ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"], ("USD",)
    )
    long_debt = latest_instant(
        facts, ["LongTermDebtAndFinanceLeaseObligations", "LongTermDebt", "LongTermDebtAndCapitalLeaseObligations"], ("USD",)
    )
    shares = latest_instant(facts, ["CommonStockSharesOutstanding"], ("shares",))

    rev = revenue["value"] if revenue else None
    ni = net_income["value"] if net_income else None
    ocf = operating_cf["value"] if operating_cf else None
    cap = capex["value"] if capex else None
    fcf = (ocf - cap) if ocf is not None and cap is not None else None
    asset_val = assets["value"] if assets else None
    liability_val = liabilities["value"] if liabilities else None
    equity_val = equity["value"] if equity else None

    return {
        "ticker": ticker,
        "name": sub.get("name") or facts.get("entityName") or ticker,
        "cik": str(cik),
        "exchanges": sub.get("exchanges") or [],
        "sic": sub.get("sic"),
        "sic_description": sub.get("sicDescription"),
        "fiscal_year_end": sub.get("fiscalYearEnd"),
        "financials": {
            "revenue": revenue,
            "revenue_previous": revenue_prev,
            "revenue_history": revenue_hist,
            "net_income": net_income,
            "net_income_previous": net_income_prev,
            "net_income_history": net_income_hist,
            "eps_diluted": eps,
            "eps_diluted_previous": eps_prev,
            "eps_history": eps_hist,
            "operating_cash_flow": operating_cf,
            "operating_cash_flow_history": operating_cf_hist,
            "capex": capex,
            "capex_history": capex_hist,
            "free_cash_flow": {"value": fcf, "end": (operating_cf or {}).get("end"), "unit": "USD"} if fcf is not None else None,
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "cash": cash,
            "long_term_debt": long_debt,
            "shares_outstanding": shares,
        },
        "ratios": {
            "revenue_growth_yoy_pct": pct_change(rev, revenue_prev["value"] if revenue_prev else None),
            "net_income_growth_yoy_pct": pct_change(ni, net_income_prev["value"] if net_income_prev else None),
            "eps_growth_yoy_pct": pct_change(eps["value"] if eps else None, eps_prev["value"] if eps_prev else None),
            "net_margin_pct": (ni / rev * 100) if ni is not None and rev not in (None, 0) else None,
            "free_cash_flow_margin_pct": (fcf / rev * 100) if fcf is not None and rev not in (None, 0) else None,
            "liabilities_to_assets_pct": (liability_val / asset_val * 100) if liability_val is not None and asset_val not in (None, 0) else None,
            "equity_to_assets_pct": (equity_val / asset_val * 100) if equity_val is not None and asset_val not in (None, 0) else None,
        },
        "recent_filings": recent_filings(sub, cik),
        "sec_company_url": f"https://www.sec.gov/edgar/browse/?CIK={int(cik)}&owner=exclude",
    }

def main():
    # CIKs are embedded for the curated list so the updater can go directly to
    # data.sec.gov. This avoids the separate www.sec.gov company_tickers.json
    # lookup that some GitHub-hosted runners receive a 403 Forbidden response from.
    companies, errors = [], []
    for ticker in TICKERS:
        cik = SEC_CIKS[ticker]
        try:
            companies.append(company_record(ticker, cik))
            print("Updated", ticker)
        except Exception as exc:
            errors.append({"ticker": ticker, "error": str(exc)})
            print("Could not update", ticker, "-", exc)

    payload = {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "U.S. Securities and Exchange Commission EDGAR",
        "source_url": "https://www.sec.gov/edgar",
        "market_price_data_included": False,
        "company_count": len(companies),
        "requested_tickers": TICKERS,
        "companies": companies,
        "errors": errors,
        "notes": [
            "Financial statement values are extracted from issuer-filed XBRL facts.",
            "Definitions and tagging can differ among issuers and across time.",
            "This dataset does not contain live or delayed stock prices.",
            "Price-dependent ratios such as P/E and market capitalization are intentionally omitted until a market-data source with appropriate display rights is configured."
        ]
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("Wrote", OUTPUT, "with", len(companies), "companies and", len(errors), "errors.")

if __name__ == "__main__":
    main()
