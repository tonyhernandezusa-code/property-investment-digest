#!/usr/bin/env python3
"""
Property Investment Digest government-data updater.

Official public sources:
- Census ACS 5-Year state data
- BLS LAUS seasonally adjusted state unemployment rates
- FHFA quarterly purchase-only state House Price Index

The existing GitHub workflow calls this file and commits:
- census_state_data.json
- data-update-status.json
- data-source-register.json

CENSUS_API_KEY is required by the existing workflow.
BLS and FHFA require no additional repository secret.

Offline test fixtures:
- CENSUS_FIXTURE_CURRENT
- CENSUS_FIXTURE_COMPARISON
- BLS_FIXTURE
- FHFA_FIXTURE
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CURRENT_ACS_YEAR = 2024
COMPARISON_ACS_YEAR = 2019
CENSUS_DATASET = "acs/acs5"

CENSUS_VARIABLES = {
    "population": "B01003_001E",
    "median_household_income": "B19013_001E",
    "housing_units": "B25001_001E",
    "vacant_units": "B25002_003E",
    "owner_occupied_units": "B25003_002E",
    "renter_occupied_units": "B25003_003E",
    "median_gross_rent": "B25064_001E",
    "median_home_value": "B25077_001E",
}

STATE_FIPS = {
    "01": ("AL", "Alabama"), "02": ("AK", "Alaska"), "04": ("AZ", "Arizona"),
    "05": ("AR", "Arkansas"), "06": ("CA", "California"), "08": ("CO", "Colorado"),
    "09": ("CT", "Connecticut"), "10": ("DE", "Delaware"),
    "11": ("DC", "District of Columbia"), "12": ("FL", "Florida"),
    "13": ("GA", "Georgia"), "15": ("HI", "Hawaii"), "16": ("ID", "Idaho"),
    "17": ("IL", "Illinois"), "18": ("IN", "Indiana"), "19": ("IA", "Iowa"),
    "20": ("KS", "Kansas"), "21": ("KY", "Kentucky"), "22": ("LA", "Louisiana"),
    "23": ("ME", "Maine"), "24": ("MD", "Maryland"), "25": ("MA", "Massachusetts"),
    "26": ("MI", "Michigan"), "27": ("MN", "Minnesota"), "28": ("MS", "Mississippi"),
    "29": ("MO", "Missouri"), "30": ("MT", "Montana"), "31": ("NE", "Nebraska"),
    "32": ("NV", "Nevada"), "33": ("NH", "New Hampshire"), "34": ("NJ", "New Jersey"),
    "35": ("NM", "New Mexico"), "36": ("NY", "New York"),
    "37": ("NC", "North Carolina"), "38": ("ND", "North Dakota"), "39": ("OH", "Ohio"),
    "40": ("OK", "Oklahoma"), "41": ("OR", "Oregon"), "42": ("PA", "Pennsylvania"),
    "44": ("RI", "Rhode Island"), "45": ("SC", "South Carolina"),
    "46": ("SD", "South Dakota"), "47": ("TN", "Tennessee"), "48": ("TX", "Texas"),
    "49": ("UT", "Utah"), "50": ("VT", "Vermont"), "51": ("VA", "Virginia"),
    "53": ("WA", "Washington"), "54": ("WV", "West Virginia"),
    "55": ("WI", "Wisconsin"), "56": ("WY", "Wyoming"),
}

ABBR_TO_FIPS = {abbr: fips for fips, (abbr, _name) in STATE_FIPS.items()}

CENSUS_NOTICE = (
    "This product uses the Census Bureau Data API but is not endorsed or "
    "certified by the Census Bureau."
)
BLS_ATTRIBUTION = "Source: U.S. Bureau of Labor Statistics, Local Area Unemployment Statistics."
FHFA_ATTRIBUTION = "Source: Federal Housing Finance Agency House Price Index®."

BLS_ENDPOINT = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
FHFA_STATE_HPI_URL = (
    "https://www.fhfa.gov/hpi/download/quarterly_datasets/hpi_po_state.txt"
)


def valid_number(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def float_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct_change(current: float | int | None, prior: float | int | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return round((current - prior) / prior * 100, 2)


def ratio(a: float | int | None, b: float | int | None, multiplier: float = 1.0) -> float | None:
    if a is None or b in (None, 0):
        return None
    return round(a / b * multiplier, 2)


def read_json_url(url: str, *, data: bytes | None = None) -> Any:
    headers = {
        "User-Agent": "Property Investment Digest educational government-data updater",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return json.loads(response.read().decode("utf-8"))


def read_text_url(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Property Investment Digest educational government-data updater",
            "Accept": "text/plain",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return response.read().decode("utf-8-sig")


# ---------------- Census ----------------

def census_url(year: int, api_key: str) -> str:
    params = {
        "get": ",".join(["NAME", *CENSUS_VARIABLES.values()]),
        "for": "state:*",
        "key": api_key,
    }
    return (
        f"https://api.census.gov/data/{year}/{CENSUS_DATASET}?"
        f"{urllib.parse.urlencode(params)}"
    )


def load_census_rows(year: int, api_key: str, fixture_env: str) -> list[dict[str, str]]:
    fixture = os.environ.get(fixture_env, "").strip()
    payload = (
        json.loads(Path(fixture).read_text(encoding="utf-8"))
        if fixture
        else read_json_url(census_url(year, api_key))
    )
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"Unexpected Census response for {year}")
    headers = payload[0]
    return [dict(zip(headers, row)) for row in payload[1:]]


def build_census_records(current_rows, prior_rows) -> list[dict[str, Any]]:
    prior_by_state = {row.get("state", ""): row for row in prior_rows}
    records: list[dict[str, Any]] = []

    for row in current_rows:
        state_fips = row.get("state", "")
        if state_fips not in STATE_FIPS:
            continue
        prior = prior_by_state.get(state_fips, {})
        values = {
            name: valid_number(row.get(variable))
            for name, variable in CENSUS_VARIABLES.items()
        }
        old = {
            name: valid_number(prior.get(variable))
            for name, variable in CENSUS_VARIABLES.items()
        }
        occupied = None
        if (
            values["owner_occupied_units"] is not None
            and values["renter_occupied_units"] is not None
        ):
            occupied = (
                values["owner_occupied_units"] + values["renter_occupied_units"]
            )

        records.append({
            "state_fips": state_fips,
            "abbr": STATE_FIPS[state_fips][0],
            "name": row.get("NAME", STATE_FIPS[state_fips][1]),
            "current_period": "2020–2024 ACS 5-Year",
            "comparison_period": "2015–2019 ACS 5-Year",
            **values,
            "population_change_pct": pct_change(
                values["population"], old["population"]
            ),
            "housing_units_change_pct": pct_change(
                values["housing_units"], old["housing_units"]
            ),
            "vacancy_rate_pct": ratio(
                values["vacant_units"], values["housing_units"], 100
            ),
            "owner_share_occupied_pct": ratio(
                values["owner_occupied_units"], occupied, 100
            ),
            "renter_share_occupied_pct": ratio(
                values["renter_occupied_units"], occupied, 100
            ),
            "home_value_to_income_ratio": ratio(
                values["median_home_value"],
                values["median_household_income"],
            ),
            "annual_rent_to_income_pct": ratio(
                (
                    values["median_gross_rent"] * 12
                    if values["median_gross_rent"] is not None
                    else None
                ),
                values["median_household_income"],
                100,
            ),
        })

    return sorted(records, key=lambda item: item["name"])


def load_existing_records() -> list[dict[str, Any]]:
    path = Path("census_state_data.json")
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", [])
        return records if isinstance(records, list) else []
    except (json.JSONDecodeError, OSError):
        return []


# ---------------- BLS ----------------

def bls_series_id(state_fips: str) -> str:
    return f"LASST{state_fips}0000000000003"


def fetch_bls_payloads() -> list[dict[str, Any]]:
    fixture = os.environ.get("BLS_FIXTURE", "").strip()
    if fixture:
        fixture_payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        return [fixture_payload]

    current_year = dt.datetime.now(dt.timezone.utc).year
    series_ids = [bls_series_id(fips) for fips in STATE_FIPS]
    payloads = []
    for start in range(0, len(series_ids), 25):
        request_body = json.dumps({
            "seriesid": series_ids[start:start + 25],
            "startyear": str(current_year - 1),
            "endyear": str(current_year),
        }).encode("utf-8")
        payloads.append(read_json_url(BLS_ENDPOINT, data=request_body))
    return payloads


def build_bls_records(payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for payload in payloads:
        if payload.get("status") != "REQUEST_SUCCEEDED":
            raise RuntimeError(
                "BLS API request failed: " + "; ".join(payload.get("message", []))
            )
        series_list = payload.get("Results", {}).get("series", [])
        for series in series_list:
            series_id = series.get("seriesID", "")
            if len(series_id) < 7:
                continue
            state_fips = series_id[5:7]
            if state_fips not in STATE_FIPS:
                continue

            observations = []
            for item in series.get("data", []):
                period = item.get("period", "")
                if not re_month(period):
                    continue
                value = float_number(item.get("value"))
                if value is None:
                    continue
                year = int(item.get("year"))
                month = int(period[1:])
                footnotes = " ".join(
                    footnote.get("text", "")
                    for footnote in item.get("footnotes", [])
                    if isinstance(footnote, dict)
                )
                observations.append({
                    "year": year,
                    "month": month,
                    "value": value,
                    "footnotes": footnotes,
                })

            if not observations:
                continue
            observations.sort(key=lambda item: (item["year"], item["month"]))
            latest = observations[-1]
            prior = next(
                (
                    item for item in observations
                    if item["year"] == latest["year"] - 1
                    and item["month"] == latest["month"]
                ),
                None,
            )
            result[state_fips] = {
                "bls_period": f"{latest['year']}-{latest['month']:02d}",
                "unemployment_rate": round(latest["value"], 2),
                "unemployment_rate_prior_year": (
                    round(prior["value"], 2) if prior else None
                ),
                "unemployment_rate_yoy_change": (
                    round(latest["value"] - prior["value"], 2)
                    if prior else None
                ),
                "unemployment_preliminary": (
                    "preliminary" in latest["footnotes"].lower()
                ),
            }

    return result


def re_month(period: str) -> bool:
    return (
        len(period) == 3
        and period.startswith("M")
        and period[1:].isdigit()
        and 1 <= int(period[1:]) <= 12
    )


# ---------------- FHFA ----------------

def load_fhfa_text() -> str:
    fixture = os.environ.get("FHFA_FIXTURE", "").strip()
    return (
        Path(fixture).read_text(encoding="utf-8")
        if fixture
        else read_text_url(FHFA_STATE_HPI_URL)
    )


def build_fhfa_records(text: str) -> dict[str, dict[str, Any]]:
    rows_by_state: dict[str, list[dict[str, Any]]] = {}
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")

    for row in reader:
        state_abbr = (row.get("state") or "").strip()
        state_fips = ABBR_TO_FIPS.get(state_abbr)
        if not state_fips:
            continue
        year = valid_number(row.get("yr"))
        quarter = valid_number(row.get("qtr"))
        index_sa = float_number(row.get("index_sa"))
        if year is None or quarter is None or index_sa is None:
            continue
        rows_by_state.setdefault(state_fips, []).append({
            "year": year,
            "quarter": quarter,
            "index_sa": index_sa,
            "warning": (row.get("Warning") or "").strip().strip('"'),
        })

    result: dict[str, dict[str, Any]] = {}
    for state_fips, rows in rows_by_state.items():
        rows.sort(key=lambda item: (item["year"], item["quarter"]))
        latest = rows[-1]
        lookup = {
            (item["year"], item["quarter"]): item
            for item in rows
        }

        if latest["quarter"] == 1:
            previous_key = (latest["year"] - 1, 4)
        else:
            previous_key = (latest["year"], latest["quarter"] - 1)

        previous = lookup.get(previous_key)
        prior_year = lookup.get((latest["year"] - 1, latest["quarter"]))
        five_year = lookup.get((latest["year"] - 5, latest["quarter"]))

        result[state_fips] = {
            "fhfa_period": f"{latest['year']}Q{latest['quarter']}",
            "fhfa_hpi_index_sa": round(latest["index_sa"], 2),
            "fhfa_quarter_change_pct": pct_change(
                latest["index_sa"],
                previous["index_sa"] if previous else None,
            ),
            "fhfa_year_change_pct": pct_change(
                latest["index_sa"],
                prior_year["index_sa"] if prior_year else None,
            ),
            "fhfa_five_year_change_pct": pct_change(
                latest["index_sa"],
                five_year["index_sa"] if five_year else None,
            ),
            "fhfa_since_1991_pct": round(
                (latest["index_sa"] / 100 - 1) * 100, 2
            ),
            "fhfa_warning": latest["warning"] or None,
        }

    return result


# ---------------- Merge and outputs ----------------

def source_register(now: str, statuses: dict[str, Any]) -> dict[str, Any]:
    return {
        "register_version": 2,
        "last_reviewed_utc": now,
        "sources": [
            {
                "source_id": "census_acs_5year",
                "source_name": (
                    "U.S. Census Bureau — American Community Survey "
                    "5-Year Detailed Tables"
                ),
                "status": statuses["census"]["status"],
                "cost": "Free",
                "data_used": (
                    "Population, housing, tenure, vacancy, household income, "
                    "gross rent, and home value."
                ),
                "publication_basis": "Census Data API Terms of Service",
                "required_notice": CENSUS_NOTICE,
                "official_terms": (
                    "https://www.census.gov/data/developers/about/"
                    "terms-of-service.html"
                ),
                "official_dataset_page": (
                    "https://www.census.gov/data/developers/"
                    "data-sets/acs-5year/2024.html"
                ),
            },
            {
                "source_id": "bls_laus",
                "source_name": (
                    "U.S. Bureau of Labor Statistics — "
                    "Local Area Unemployment Statistics"
                ),
                "status": statuses["bls"]["status"],
                "cost": "Free public API",
                "data_used": (
                    "Seasonally adjusted monthly state unemployment rates "
                    "and 12-month changes."
                ),
                "attribution": BLS_ATTRIBUTION,
                "official_api": "https://www.bls.gov/developers/",
                "official_program": "https://www.bls.gov/lau/",
            },
            {
                "source_id": "fhfa_hpi",
                "source_name": (
                    "Federal Housing Finance Agency — "
                    "Quarterly Purchase-Only State HPI"
                ),
                "status": statuses["fhfa"]["status"],
                "cost": "Publicly available government dataset",
                "data_used": (
                    "Seasonally adjusted state HPI and transparent "
                    "quarter, one-year, five-year, and since-1991 changes."
                ),
                "attribution": FHFA_ATTRIBUTION,
                "official_dataset_page": "https://www.fhfa.gov/house-price-index",
                "official_download": FHFA_STATE_HPI_URL,
            },
            {
                "source_id": "hud",
                "source_name": "U.S. Department of Housing and Urban Development",
                "status": "planned — dataset-by-dataset review required",
            },
            {
                "source_id": "openfema",
                "source_name": "OpenFEMA",
                "status": "planned — dataset-by-dataset review required",
            },
            {
                "source_id": "commercial_vendor",
                "source_name": "Commercial property-data vendor",
                "status": "not selected",
                "publication_rule": (
                    "Do not add vendor data until written permission confirms "
                    "public display, storage, derivative analysis, reports, "
                    "and future paid-subscriber use."
                ),
            },
        ],
    }


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    census_key = os.environ.get("CENSUS_API_KEY", "").strip()
    using_census_fixtures = bool(
        os.environ.get("CENSUS_FIXTURE_CURRENT")
        and os.environ.get("CENSUS_FIXTURE_COMPARISON")
    )

    statuses = {
        "census": {"status": "not attempted", "message": ""},
        "bls": {"status": "not attempted", "message": ""},
        "fhfa": {"status": "not attempted", "message": ""},
    }

    records: list[dict[str, Any]] = []

    try:
        if not census_key and not using_census_fixtures:
            raise RuntimeError("CENSUS_API_KEY is missing.")
        records = build_census_records(
            load_census_rows(
                CURRENT_ACS_YEAR,
                census_key,
                "CENSUS_FIXTURE_CURRENT",
            ),
            load_census_rows(
                COMPARISON_ACS_YEAR,
                census_key,
                "CENSUS_FIXTURE_COMPARISON",
            ),
        )
        statuses["census"] = {
            "status": "success",
            "message": f"{len(records)} state records",
            "current_vintage": CURRENT_ACS_YEAR,
            "comparison_vintage": COMPARISON_ACS_YEAR,
        }
    except Exception as exc:
        records = load_existing_records()
        statuses["census"] = {
            "status": "error — existing Census records retained",
            "message": str(exc),
        }

    if not records:
        print("No Census or existing state records are available.", file=sys.stderr)
        return 2

    try:
        bls_records = build_bls_records(fetch_bls_payloads())
        statuses["bls"] = {
            "status": "success",
            "message": f"{len(bls_records)} state records",
            "latest_period": max(
                (
                    item["bls_period"]
                    for item in bls_records.values()
                    if item.get("bls_period")
                ),
                default=None,
            ),
        }
    except Exception as exc:
        bls_records = {}
        statuses["bls"] = {"status": "error", "message": str(exc)}

    try:
        fhfa_records = build_fhfa_records(load_fhfa_text())
        statuses["fhfa"] = {
            "status": "success",
            "message": f"{len(fhfa_records)} state records",
            "latest_period": max(
                (
                    item["fhfa_period"]
                    for item in fhfa_records.values()
                    if item.get("fhfa_period")
                ),
                default=None,
            ),
        }
    except Exception as exc:
        fhfa_records = {}
        statuses["fhfa"] = {"status": "error", "message": str(exc)}

    for record in records:
        state_fips = record.get("state_fips", "")
        record["abbr"] = record.get("abbr") or STATE_FIPS.get(
            state_fips, ("", "")
        )[0]
        record.update(bls_records.get(state_fips, {}))
        record.update(fhfa_records.get(state_fips, {}))

    successful_sources = sum(
        1 for source in statuses.values()
        if source["status"] == "success"
    )
    overall_status = (
        "success" if successful_sources == 3
        else "partial success" if successful_sources > 0
        else "error"
    )

    output = {
        "schema_version": 2,
        "updated_at_utc": now,
        "source": "Official U.S. government data",
        "dataset": (
            "Census ACS 5-Year, BLS LAUS state unemployment, "
            "and FHFA state House Price Index"
        ),
        "current_vintage": CURRENT_ACS_YEAR,
        "comparison_vintage": COMPARISON_ACS_YEAR,
        "comparison_note": (
            "ACS compares 2020–2024 with the non-overlapping "
            "2015–2019 ACS 5-Year estimates."
        ),
        "attribution_notices": [
            CENSUS_NOTICE,
            BLS_ATTRIBUTION,
            FHFA_ATTRIBUTION,
        ],
        "source_status": statuses,
        "records": sorted(records, key=lambda item: item.get("name", "")),
    }

    Path("census_state_data.json").write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )
    Path("data-update-status.json").write_text(
        json.dumps({
            "updated_at_utc": now,
            "status": overall_status,
            "message": (
                f"Census: {statuses['census']['status']}; "
                f"BLS: {statuses['bls']['status']}; "
                f"FHFA: {statuses['fhfa']['status']}."
            ),
            "sources": statuses,
            "records_written": len(records),
        }, indent=2),
        encoding="utf-8",
    )
    Path("data-source-register.json").write_text(
        json.dumps(source_register(now, statuses), indent=2),
        encoding="utf-8",
    )

    print(
        f"Wrote {len(records)} combined state records. "
        f"Overall status: {overall_status}."
    )
    return 0 if successful_sources > 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
