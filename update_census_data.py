#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CURRENT_YEAR = 2024
COMPARISON_YEAR = 2019
DATASET = "acs/acs5"
VARIABLES = {
    "population": "B01003_001E",
    "median_household_income": "B19013_001E",
    "housing_units": "B25001_001E",
    "vacant_units": "B25002_003E",
    "owner_occupied_units": "B25003_002E",
    "renter_occupied_units": "B25003_003E",
    "median_gross_rent": "B25064_001E",
    "median_home_value": "B25077_001E",
}
NOTICE = "This product uses the Census Bureau Data API but is not endorsed or certified by the Census Bureau."

def estimate(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None

def pct_change(current: int | None, prior: int | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return round((current - prior) / prior * 100, 2)

def ratio(a: int | None, b: int | None, multiplier: float = 1.0) -> float | None:
    if a is None or b in (None, 0):
        return None
    return round(a / b * multiplier, 2)

def api_url(year: int, key: str) -> str:
    params = {"get": ",".join(["NAME", *VARIABLES.values()]), "for": "state:*", "key": key}
    return f"https://api.census.gov/data/{year}/{DATASET}?{urllib.parse.urlencode(params)}"

def fetch(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "Property Investment Digest educational updater", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Census API returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def load_rows(year: int, key: str, fixture_env: str) -> list[dict[str, str]]:
    fixture = os.environ.get(fixture_env, "").strip()
    payload = json.loads(Path(fixture).read_text(encoding="utf-8")) if fixture else fetch(api_url(year, key))
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(f"Unexpected Census response for {year}")
    headers = payload[0]
    return [dict(zip(headers, row)) for row in payload[1:]]

def build_records(current_rows, prior_rows):
    prior_by_state = {row.get("state", ""): row for row in prior_rows}
    records = []
    for row in current_rows:
        state = row.get("state", "")
        prior = prior_by_state.get(state, {})
        values = {name: estimate(row.get(var)) for name, var in VARIABLES.items()}
        old = {name: estimate(prior.get(var)) for name, var in VARIABLES.items()}
        occupied = None
        if values["owner_occupied_units"] is not None and values["renter_occupied_units"] is not None:
            occupied = values["owner_occupied_units"] + values["renter_occupied_units"]
        records.append({
            "state_fips": state,
            "name": row.get("NAME", state),
            "current_period": "2020–2024 ACS 5-Year",
            "comparison_period": "2015–2019 ACS 5-Year",
            **values,
            "population_change_pct": pct_change(values["population"], old["population"]),
            "housing_units_change_pct": pct_change(values["housing_units"], old["housing_units"]),
            "vacancy_rate_pct": ratio(values["vacant_units"], values["housing_units"], 100),
            "owner_share_occupied_pct": ratio(values["owner_occupied_units"], occupied, 100),
            "renter_share_occupied_pct": ratio(values["renter_occupied_units"], occupied, 100),
            "home_value_to_income_ratio": ratio(values["median_home_value"], values["median_household_income"]),
            "annual_rent_to_income_pct": ratio(
                values["median_gross_rent"] * 12 if values["median_gross_rent"] is not None else None,
                values["median_household_income"], 100
            ),
        })
    return sorted(records, key=lambda item: item["name"])

def write_outputs(records):
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    Path("census_state_data.json").write_text(json.dumps({
        "schema_version": 1,
        "updated_at_utc": now,
        "source": "U.S. Census Bureau Data API",
        "dataset": "American Community Survey 5-Year Detailed Tables",
        "current_vintage": CURRENT_YEAR,
        "comparison_vintage": COMPARISON_YEAR,
        "comparison_note": "The 2020–2024 ACS 5-Year estimates are compared with the non-overlapping 2015–2019 ACS 5-Year estimates.",
        "attribution_notice": NOTICE,
        "records": records,
    }, indent=2), encoding="utf-8")
    Path("data-update-status.json").write_text(json.dumps({
        "updated_at_utc": now,
        "status": "success",
        "source": "Census ACS 5-Year",
        "current_vintage": CURRENT_YEAR,
        "comparison_vintage": COMPARISON_YEAR,
        "records_written": len(records),
    }, indent=2), encoding="utf-8")
    Path("data-source-register.json").write_text(json.dumps({
        "register_version": 1,
        "last_reviewed_utc": now,
        "sources": [
            {
                "source_id": "census_acs_5year",
                "source_name": "U.S. Census Bureau — ACS 5-Year Detailed Tables",
                "status": "active",
                "cost": "Free",
                "publication_basis": "Census Data API Terms of Service",
                "required_notice": NOTICE,
                "official_terms": "https://www.census.gov/data/developers/about/terms-of-service.html",
                "official_dataset_page": "https://www.census.gov/data/developers/data-sets/acs-5year/2024.html",
            },
            {"source_id": "bls", "source_name": "U.S. Bureau of Labor Statistics", "status": "planned — not yet added"},
            {"source_id": "fhfa", "source_name": "Federal Housing Finance Agency", "status": "planned — not yet added"},
            {"source_id": "hud", "source_name": "HUD", "status": "planned — dataset-by-dataset review required"},
            {"source_id": "openfema", "source_name": "OpenFEMA", "status": "planned — dataset-by-dataset review required"},
            {
                "source_id": "commercial_vendor",
                "source_name": "Commercial property-data vendor",
                "status": "not selected",
                "publication_rule": "Do not add vendor data until written publication permission is retained.",
            },
        ],
    }, indent=2), encoding="utf-8")

def main() -> int:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    fixtures = bool(os.environ.get("CENSUS_FIXTURE_CURRENT") and os.environ.get("CENSUS_FIXTURE_COMPARISON"))
    if not key and not fixtures:
        print("CENSUS_API_KEY is missing.", file=sys.stderr)
        return 2
    records = build_records(
        load_rows(CURRENT_YEAR, key, "CENSUS_FIXTURE_CURRENT"),
        load_rows(COMPARISON_YEAR, key, "CENSUS_FIXTURE_COMPARISON"),
    )
    if len(records) < 50:
        raise RuntimeError(f"Only {len(records)} records were returned.")
    write_outputs(records)
    print(f"Wrote {len(records)} Census state records.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
