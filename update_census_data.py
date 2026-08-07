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
import re
import statistics
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
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
HUD_FMR_YEAR = 2026
HUD_FMR_URL = (
    "https://www.huduser.gov/portal/datasets/fmr/fmr2026/"
    "FY26_FMRs_revised.xlsx"
)
OPENFEMA_ENDPOINT = (
    "https://www.fema.gov/api/open/v1/DisasterDeclarationsSummaries"
)
HUD_ATTRIBUTION = (
    "Source: U.S. Department of Housing and Urban Development, "
    "HUD USER, FY 2026 Fair Market Rents."
)
FEMA_ATTRIBUTION = (
    "Source: Federal Emergency Management Agency, "
    "OpenFEMA Disaster Declarations Summaries."
)

HOTEL_CBP_CURRENT_YEAR = 2023
HOTEL_CBP_COMPARISON_YEAR = 2019
HOTEL_NAICS = "721110"
HOTEL_CBP_ATTRIBUTION = (
    "Source: U.S. Census Bureau, County Business Patterns, "
    "NAICS 721110 — Hotels (except Casino Hotels) and Motels."
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


def read_binary_url(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Property Investment Digest educational government-data updater",
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} from {url}")
        return response.read()


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




# ---------------- HUD Fair Market Rents ----------------

def load_hud_fmr_bytes() -> bytes:
    fixture = os.environ.get("HUD_FMR_FIXTURE", "").strip()
    return Path(fixture).read_bytes() if fixture else read_binary_url(HUD_FMR_URL)


def column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + (ord(character) - 64)
    return max(0, result - 1)


def xlsx_rows(workbook_bytes: bytes) -> list[list[Any]]:
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    all_rows: list[list[Any]] = []

    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{namespace}si"):
                text_parts = [
                    node.text or ""
                    for node in item.iter(f"{namespace}t")
                ]
                shared_strings.append("".join(text_parts))

        sheet_files = sorted(
            name for name in workbook.namelist()
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
        )
        for sheet_file in sheet_files:
            root = ET.fromstring(workbook.read(sheet_file))
            for row_node in root.iter(f"{namespace}row"):
                row: list[Any] = []
                for cell in row_node.findall(f"{namespace}c"):
                    index = column_index(cell.get("r", "A1"))
                    while len(row) <= index:
                        row.append(None)
                    cell_type = cell.get("t", "")
                    value_node = cell.find(f"{namespace}v")
                    value: Any = None
                    if cell_type == "inlineStr":
                        value = "".join(
                            node.text or ""
                            for node in cell.iter(f"{namespace}t")
                        )
                    elif value_node is not None:
                        raw_value = value_node.text or ""
                        if cell_type == "s":
                            try:
                                value = shared_strings[int(raw_value)]
                            except (ValueError, IndexError):
                                value = raw_value
                        elif cell_type == "b":
                            value = raw_value == "1"
                        else:
                            value = raw_value
                    row[index] = value
                if any(value not in (None, "") for value in row):
                    all_rows.append(row)

    return all_rows


def normalize_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


HUD_HEADER_ALIASES = {
    "fips": {"fips2010", "fips", "fipscode", "geoid"},
    "fmr_0": {"fmr0", "fmr0bdr", "efficiency", "studio", "0br"},
    "fmr_1": {"fmr1", "fmr1bdr", "onebedroom", "1br"},
    "fmr_2": {"fmr2", "fmr2bdr", "twobedroom", "2br"},
    "fmr_3": {"fmr3", "fmr3bdr", "threebedroom", "3br"},
    "fmr_4": {"fmr4", "fmr4bdr", "fourbedroom", "4br"},
    "state_alpha": {"statealpha", "statecode", "stateabbr", "state"},
    "county_name": {"countyname", "county"},
    "town_name": {"countytownname", "townname", "town"},
    "area_name": {"areaname", "hudareaname", "metroname", "area"},
    "metro_code": {"metrocode", "hudareacode", "areacode"},
    "population": {"population", "pop2017", "pop2020", "pop2021", "pop2022", "pop2023"},
}


def locate_hud_header(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    for row_number, row in enumerate(rows[:80]):
        normalized = {
            normalize_header(value): index
            for index, value in enumerate(row)
            if normalize_header(value)
        }
        mapping: dict[str, int] = {}
        for field, aliases in HUD_HEADER_ALIASES.items():
            for alias in aliases:
                if alias in normalized:
                    mapping[field] = normalized[alias]
                    break
        if {"fips", "fmr_2", "county_name"}.issubset(mapping):
            return row_number, mapping
    raise RuntimeError("HUD FMR workbook header row was not recognized.")


def row_item(row: list[Any], mapping: dict[str, int], field: str) -> Any:
    index = mapping.get(field)
    return row[index] if index is not None and index < len(row) else None


def clean_fips(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        raw = str(int(float(raw)))
    except ValueError:
        raw = "".join(character for character in raw if character.isdigit())
    return raw.zfill(10)


def rent_number(value: Any) -> int | None:
    try:
        number = int(round(float(str(value).replace(",", "").replace("$", ""))))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def build_hud_fmr_records(workbook_bytes: bytes) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = xlsx_rows(workbook_bytes)
    header_row, mapping = locate_hud_header(rows)
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for row in rows[header_row + 1:]:
        fips = clean_fips(row_item(row, mapping, "fips"))
        if len(fips) < 2:
            continue
        state_fips = fips[:2]
        default_abbr = STATE_FIPS.get(state_fips, ("", ""))[0]
        state_value = str(row_item(row, mapping, "state_alpha") or "").strip()
        state_abbr = state_value.upper() if len(state_value) == 2 and state_value.isalpha() else default_abbr
        if state_abbr not in ABBR_TO_FIPS:
            continue
        state_fips = ABBR_TO_FIPS[state_abbr]

        rents = {
            field: rent_number(row_item(row, mapping, field))
            for field in ("fmr_0", "fmr_1", "fmr_2", "fmr_3", "fmr_4")
        }
        if rents["fmr_2"] is None:
            continue

        county_name = str(row_item(row, mapping, "county_name") or "").strip()
        town_name = str(row_item(row, mapping, "town_name") or "").strip()
        area_name = str(row_item(row, mapping, "area_name") or "").strip()
        key = (fips, town_name, area_name)
        if key in seen:
            continue
        seen.add(key)

        records.append({
            "fips": fips,
            "state_fips": state_fips,
            "state_abbr": state_abbr,
            "state_name": STATE_FIPS[state_fips][1],
            "county_name": county_name,
            "town_name": town_name,
            "area_name": area_name,
            "metro_code": str(row_item(row, mapping, "metro_code") or "").strip(),
            "population_reference": valid_number(row_item(row, mapping, "population")),
            "fmr_year": HUD_FMR_YEAR,
            **rents,
        })

    if len(records) < 1000:
        raise RuntimeError(f"Only {len(records)} HUD FMR area records were parsed.")

    summaries: dict[str, dict[str, Any]] = {}
    for state_fips in STATE_FIPS:
        state_rows = [record for record in records if record["state_fips"] == state_fips]
        if not state_rows:
            continue

        def median_rent(field: str) -> int | None:
            values = [record[field] for record in state_rows if record.get(field) is not None]
            return int(round(statistics.median(values))) if values else None

        two_bedroom = [record["fmr_2"] for record in state_rows if record.get("fmr_2") is not None]
        summaries[state_fips] = {
            "hud_fmr_year": HUD_FMR_YEAR,
            "hud_fmr_area_count": len(state_rows),
            "hud_median_fmr_0": median_rent("fmr_0"),
            "hud_median_fmr_1": median_rent("fmr_1"),
            "hud_median_fmr_2": median_rent("fmr_2"),
            "hud_median_fmr_3": median_rent("fmr_3"),
            "hud_median_fmr_4": median_rent("fmr_4"),
            "hud_min_fmr_2": min(two_bedroom) if two_bedroom else None,
            "hud_max_fmr_2": max(two_bedroom) if two_bedroom else None,
        }

    return sorted(
        records,
        key=lambda item: (
            item["state_name"],
            item["county_name"],
            item["town_name"],
            item["area_name"],
        ),
    ), summaries


# ---------------- OpenFEMA Disaster Declarations ----------------

def extract_fema_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in (
        "DisasterDeclarationsSummaries",
        "disasterDeclarationsSummaries",
        "data",
        "records",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    for value in payload.values():
        if isinstance(value, list):
            return value
    return []


def fetch_fema_rows(window_start: str) -> list[dict[str, Any]]:
    fixture = os.environ.get("FEMA_FIXTURE", "").strip()
    if fixture:
        return extract_fema_rows(
            json.loads(Path(fixture).read_text(encoding="utf-8"))
        )

    fields = (
        "disasterNumber,state,declarationDate,declarationType,"
        "incidentType,title,ihProgramDeclared,iaProgramDeclared,"
        "paProgramDeclared"
    )
    all_rows: list[dict[str, Any]] = []
    page_size = 1000

    for skip in range(0, 100000, page_size):
        params = {
            "$select": fields,
            "$filter": (
                "declarationDate ge "
                f"'{window_start}T00:00:00.000z'"
            ),
            "$orderby": "declarationDate desc",
            "$top": str(page_size),
            "$skip": str(skip),
        }
        url = OPENFEMA_ENDPOINT + "?" + urllib.parse.urlencode(params)
        page_rows = extract_fema_rows(read_json_url(url))
        all_rows.extend(page_rows)
        if len(page_rows) < page_size:
            break
    return all_rows


def truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def build_fema_records(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        state_abbr = str(row.get("state") or "").strip().upper()
        state_fips = ABBR_TO_FIPS.get(state_abbr)
        disaster_number = str(row.get("disasterNumber") or "").strip()
        if not state_fips or not disaster_number:
            continue

        key = (state_fips, disaster_number)
        declaration = unique.setdefault(key, {
            "state_fips": state_fips,
            "state_abbr": state_abbr,
            "disaster_number": disaster_number,
            "declaration_date": str(row.get("declarationDate") or "")[:10],
            "declaration_type": str(row.get("declarationType") or "").strip(),
            "incident_type": str(row.get("incidentType") or "").strip(),
            "title": str(row.get("title") or "").strip(),
            "individual_assistance": False,
            "public_assistance": False,
        })
        declaration["individual_assistance"] = (
            declaration["individual_assistance"]
            or truthy(row.get("ihProgramDeclared"))
            or truthy(row.get("iaProgramDeclared"))
        )
        declaration["public_assistance"] = (
            declaration["public_assistance"]
            or truthy(row.get("paProgramDeclared"))
        )

    by_state: dict[str, list[dict[str, Any]]] = {}
    for declaration in unique.values():
        by_state.setdefault(declaration["state_fips"], []).append(declaration)

    summaries: dict[str, dict[str, Any]] = {}
    recent: dict[str, list[dict[str, Any]]] = {}

    for state_fips, declarations in by_state.items():
        declarations.sort(
            key=lambda item: item.get("declaration_date", ""),
            reverse=True,
        )
        incident_counts: dict[str, int] = {}
        for declaration in declarations:
            incident = declaration.get("incident_type") or "Other/Unspecified"
            incident_counts[incident] = incident_counts.get(incident, 0) + 1

        latest = declarations[0]
        top_incident = max(
            incident_counts.items(),
            key=lambda item: (item[1], item[0]),
        )[0] if incident_counts else None

        summaries[state_fips] = {
            "fema_declarations_10yr": len(declarations),
            "fema_major_disasters_10yr": sum(
                item["declaration_type"] == "DR" for item in declarations
            ),
            "fema_emergencies_10yr": sum(
                item["declaration_type"] == "EM" for item in declarations
            ),
            "fema_fire_management_10yr": sum(
                item["declaration_type"] == "FM" for item in declarations
            ),
            "fema_individual_assistance_10yr": sum(
                item["individual_assistance"] for item in declarations
            ),
            "fema_public_assistance_10yr": sum(
                item["public_assistance"] for item in declarations
            ),
            "fema_top_incident_type_10yr": top_incident,
            "fema_latest_declaration_date": latest.get("declaration_date"),
            "fema_latest_disaster_number": latest.get("disaster_number"),
            "fema_latest_declaration_type": latest.get("declaration_type"),
            "fema_latest_incident_type": latest.get("incident_type"),
            "fema_latest_title": latest.get("title"),
        }
        recent[state_fips] = declarations[:10]

    return summaries, recent



# ---------------- Census County Business Patterns: Hotels ----------------

def cbp_url(year: int, geography: str, api_key: str) -> str:
    params = {
        "get": "NAME,ESTAB,EMP,PAYANN",
        "for": geography,
        "NAICS2017": HOTEL_NAICS,
        "LFO": "001",
        "EMPSZES": "001",
        "key": api_key,
    }
    if geography == "county:*":
        params["in"] = "state:*"
    return (
        f"https://api.census.gov/data/{year}/cbp?"
        f"{urllib.parse.urlencode(params)}"
    )


def load_cbp_rows(year: int, api_key: str, fixture_env: str) -> dict[str, list[dict[str, str]]]:
    fixture = os.environ.get(fixture_env, "").strip()
    if fixture:
        payload = json.loads(Path(fixture).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Hotel CBP fixture must contain us, states, and counties arrays.")
        return payload

    result: dict[str, list[dict[str, str]]] = {}
    for key, geography in (
        ("us", "us:*"),
        ("states", "state:*"),
        ("counties", "county:*"),
    ):
        payload = read_json_url(cbp_url(year, geography, api_key))
        if not isinstance(payload, list) or len(payload) < 2:
            raise RuntimeError(f"Unexpected CBP {year} response for {key}.")
        headers = payload[0]
        result[key] = [dict(zip(headers, row)) for row in payload[1:]]
    return result


def cbp_int(value: Any) -> int | None:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def cbp_metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    establishments = cbp_int(row.get("ESTAB"))
    employment = cbp_int(row.get("EMP"))
    payroll_thousands = cbp_int(row.get("PAYANN"))
    payroll_dollars = (
        payroll_thousands * 1000
        if payroll_thousands is not None
        else None
    )
    return {
        "establishments": establishments,
        "employment": employment,
        "annual_payroll": payroll_dollars,
        "employees_per_establishment": ratio(employment, establishments),
        "payroll_per_employee": ratio(payroll_dollars, employment),
    }


def cbp_change(current: int | float | None, prior: int | float | None) -> float | None:
    return pct_change(current, prior)


def build_hotel_cbp(
    current_payload: dict[str, list[dict[str, str]]],
    prior_payload: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:

    def keyed(rows: list[dict[str, str]], geography: str) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for row in rows:
            if geography == "us":
                key = "US"
            elif geography == "state":
                key = str(row.get("state") or "").zfill(2)
            else:
                state = str(row.get("state") or "").zfill(2)
                county = str(row.get("county") or "").zfill(3)
                key = state + county
            result[key] = row
        return result

    current_us = keyed(current_payload.get("us", []), "us")
    prior_us = keyed(prior_payload.get("us", []), "us")
    current_states = keyed(current_payload.get("states", []), "state")
    prior_states = keyed(prior_payload.get("states", []), "state")
    current_counties = keyed(current_payload.get("counties", []), "county")
    prior_counties = keyed(prior_payload.get("counties", []), "county")

    def combine(current_row, prior_row, *, fips=None, state_fips=None):
        current = cbp_metrics(current_row)
        prior = cbp_metrics(prior_row)
        record = {
            "name": (current_row or prior_row or {}).get("NAME", ""),
            "fips": fips,
            "state_fips": state_fips,
            **current,
            "establishments_change_pct": cbp_change(
                current["establishments"], prior["establishments"]
            ),
            "employment_change_pct": cbp_change(
                current["employment"], prior["employment"]
            ),
            "payroll_change_pct": cbp_change(
                current["annual_payroll"], prior["annual_payroll"]
            ),
            "comparison_establishments": prior["establishments"],
            "comparison_employment": prior["employment"],
            "comparison_annual_payroll": prior["annual_payroll"],
        }
        return record

    national = combine(
        current_us.get("US"),
        prior_us.get("US"),
        fips="US",
    )

    states = []
    for fips in sorted(set(current_states) | set(prior_states)):
        if fips not in STATE_FIPS:
            continue
        record = combine(
            current_states.get(fips),
            prior_states.get(fips),
            fips=fips,
            state_fips=fips,
        )
        record["abbr"] = STATE_FIPS[fips][0]
        record["name"] = STATE_FIPS[fips][1]
        states.append(record)

    counties = []
    for county_fips in sorted(set(current_counties) | set(prior_counties)):
        state_fips = county_fips[:2]
        if state_fips not in STATE_FIPS:
            continue
        record = combine(
            current_counties.get(county_fips),
            prior_counties.get(county_fips),
            fips=county_fips,
            state_fips=state_fips,
        )
        record["state_abbr"] = STATE_FIPS[state_fips][0]
        record["state_name"] = STATE_FIPS[state_fips][1]
        counties.append(record)

    return {
        "naics": HOTEL_NAICS,
        "industry": "Hotels (except Casino Hotels) and Motels",
        "current_year": HOTEL_CBP_CURRENT_YEAR,
        "comparison_year": HOTEL_CBP_COMPARISON_YEAR,
        "national": national,
        "states": states,
        "counties": counties,
        "interpretation": (
            "County Business Patterns measures establishments, employment, "
            "and payroll. It does not report hotel room counts, occupancy, "
            "ADR, RevPAR, property values, or individual hotel performance."
        ),
    }


# ---------------- Merge and outputs ----------------

def source_register(now: str, statuses: dict[str, Any]) -> dict[str, Any]:
    return {
        "register_version": 3,
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
                "source_id": "hud_fmr_2026",
                "source_name": (
                    "U.S. Department of Housing and Urban Development — "
                    "FY 2026 Fair Market Rents"
                ),
                "status": statuses["hud"]["status"],
                "cost": "Official downloadable government dataset",
                "data_used": (
                    "County/town FMRs for efficiency through four-bedroom "
                    "units and transparent state summaries."
                ),
                "attribution": HUD_ATTRIBUTION,
                "official_dataset_page": (
                    "https://www.huduser.gov/portal/datasets/fmr.html"
                ),
                "official_download": HUD_FMR_URL,
                "interpretation_note": (
                    "FMR is a gross-rent program benchmark, not an asking-rent "
                    "estimate or a property valuation."
                ),
            },
            {
                "source_id": "openfema_disaster_declarations",
                "source_name": (
                    "Federal Emergency Management Agency — "
                    "OpenFEMA Disaster Declarations Summaries"
                ),
                "status": statuses["fema"]["status"],
                "cost": "Free public API; no registration required",
                "data_used": (
                    "Unique federal disaster declarations by state for a "
                    "rolling ten-year window."
                ),
                "attribution": FEMA_ATTRIBUTION,
                "official_dataset_page": (
                    "https://www.fema.gov/about/openfema/"
                    "disaster-declarations-summaries"
                ),
                "official_api": OPENFEMA_ENDPOINT,
                "interpretation_note": (
                    "Declaration history is not a parcel-level hazard, flood "
                    "zone, insurance, or future-loss determination."
                ),
            },
            {
                "source_id": "census_cbp_hotels",
                "source_name": (
                    "U.S. Census Bureau — County Business Patterns, "
                    "Hotels (except Casino Hotels) and Motels"
                ),
                "status": statuses["hotel_cbp"]["status"],
                "cost": "Free Census Data API",
                "data_used": (
                    "Hotel/motel establishments, employment, and annual payroll "
                    "for the United States, states, and counties."
                ),
                "naics": HOTEL_NAICS,
                "current_year": HOTEL_CBP_CURRENT_YEAR,
                "comparison_year": HOTEL_CBP_COMPARISON_YEAR,
                "attribution": HOTEL_CBP_ATTRIBUTION,
                "required_notice": CENSUS_NOTICE,
                "official_dataset_page": (
                    "https://www.census.gov/data/developers/"
                    "data-sets/cbp-zbp/cbp-api.html"
                ),
                "interpretation_note": (
                    "CBP is a business and employment dataset. It does not "
                    "provide hotel occupancy, ADR, RevPAR, room inventory, or "
                    "property-level operating results."
                ),
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
    now_datetime = dt.datetime.now(dt.timezone.utc)
    now = now_datetime.replace(microsecond=0).isoformat()
    window_start = f"{now_datetime.year - 10}-01-01"
    census_key = os.environ.get("CENSUS_API_KEY", "").strip()
    using_census_fixtures = bool(
        os.environ.get("CENSUS_FIXTURE_CURRENT")
        and os.environ.get("CENSUS_FIXTURE_COMPARISON")
    )

    statuses = {
        "census": {"status": "not attempted", "message": ""},
        "bls": {"status": "not attempted", "message": ""},
        "fhfa": {"status": "not attempted", "message": ""},
        "hud": {"status": "not attempted", "message": ""},
        "fema": {"status": "not attempted", "message": ""},
        "hotel_cbp": {"status": "not attempted", "message": ""},
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

    try:
        hud_areas, hud_summaries = build_hud_fmr_records(load_hud_fmr_bytes())
        statuses["hud"] = {
            "status": "success",
            "message": f"{len(hud_areas)} county/town records",
            "fiscal_year": HUD_FMR_YEAR,
        }
    except Exception as exc:
        hud_areas = []
        hud_summaries = {}
        statuses["hud"] = {"status": "error", "message": str(exc)}

    try:
        fema_summaries, fema_recent = build_fema_records(
            fetch_fema_rows(window_start)
        )
        statuses["fema"] = {
            "status": "success",
            "message": (
                f"{sum(item['fema_declarations_10yr'] for item in fema_summaries.values())} "
                "unique state declarations"
            ),
            "window_start": window_start,
        }
    except Exception as exc:
        fema_summaries = {}
        fema_recent = {}
        statuses["fema"] = {"status": "error", "message": str(exc)}

    try:
        hotel_cbp = build_hotel_cbp(
            load_cbp_rows(
                HOTEL_CBP_CURRENT_YEAR,
                census_key,
                "HOTEL_CBP_FIXTURE_CURRENT",
            ),
            load_cbp_rows(
                HOTEL_CBP_COMPARISON_YEAR,
                census_key,
                "HOTEL_CBP_FIXTURE_COMPARISON",
            ),
        )
        statuses["hotel_cbp"] = {
            "status": "success",
            "message": (
                f"{len(hotel_cbp['states'])} state and "
                f"{len(hotel_cbp['counties'])} county records"
            ),
            "current_year": HOTEL_CBP_CURRENT_YEAR,
            "comparison_year": HOTEL_CBP_COMPARISON_YEAR,
        }
    except Exception as exc:
        hotel_cbp = {
            "naics": HOTEL_NAICS,
            "industry": "Hotels (except Casino Hotels) and Motels",
            "current_year": HOTEL_CBP_CURRENT_YEAR,
            "comparison_year": HOTEL_CBP_COMPARISON_YEAR,
            "national": {},
            "states": [],
            "counties": [],
            "interpretation": (
                "Hotel County Business Patterns data was unavailable during "
                "this update."
            ),
        }
        statuses["hotel_cbp"] = {"status": "error", "message": str(exc)}

    for record in records:
        state_fips = record.get("state_fips", "")
        record["abbr"] = record.get("abbr") or STATE_FIPS.get(
            state_fips, ("", "")
        )[0]
        record.update(bls_records.get(state_fips, {}))
        record.update(fhfa_records.get(state_fips, {}))
        record.update(hud_summaries.get(state_fips, {}))
        record.update(fema_summaries.get(state_fips, {}))

        median_fmr_2 = record.get("hud_median_fmr_2")
        income = record.get("median_household_income")
        record["hud_annual_fmr2_to_income_pct"] = ratio(
            median_fmr_2 * 12 if median_fmr_2 is not None else None,
            income,
            100,
        )

    successful_sources = sum(
        1 for source in statuses.values()
        if source["status"] == "success"
    )
    overall_status = (
        "success" if successful_sources == 6
        else "partial success" if successful_sources > 0
        else "error"
    )

    output = {
        "schema_version": 3,
        "updated_at_utc": now,
        "source": "Official U.S. government data",
        "dataset": (
            "Census ACS, BLS LAUS, FHFA HPI, HUD FY 2026 FMR, "
            "and OpenFEMA Disaster Declarations Summaries"
        ),
        "current_vintage": CURRENT_ACS_YEAR,
        "comparison_vintage": COMPARISON_ACS_YEAR,
        "comparison_note": (
            "ACS compares 2020–2024 with the non-overlapping "
            "2015–2019 ACS 5-Year estimates."
        ),
        "hud_fmr_year": HUD_FMR_YEAR,
        "fema_window_start": window_start,
        "attribution_notices": [
            CENSUS_NOTICE,
            BLS_ATTRIBUTION,
            FHFA_ATTRIBUTION,
            HUD_ATTRIBUTION,
            FEMA_ATTRIBUTION,
        ],
        "source_status": statuses,
        "records": sorted(records, key=lambda item: item.get("name", "")),
        "hud_fmr_areas": hud_areas,
        "fema_recent_declarations": fema_recent,
        "hotel_cbp": hotel_cbp,
    }

    Path("census_state_data.json").write_text(
        json.dumps(output, indent=2),
        encoding="utf-8",
    )
    Path("data-update-status.json").write_text(
        json.dumps({
            "updated_at_utc": now,
            "status": overall_status,
            "message": "; ".join(
                f"{name.upper()}: {details['status']}"
                for name, details in statuses.items()
            ),
            "sources": statuses,
            "records_written": len(records),
            "hud_area_records": len(hud_areas),
            "fema_window_start": window_start,
        }, indent=2),
        encoding="utf-8",
    )
    Path("data-source-register.json").write_text(
        json.dumps(source_register(now, statuses), indent=2),
        encoding="utf-8",
    )

    print(
        f"Wrote {len(records)} combined state records, "
        f"{len(hud_areas)} HUD FMR area records. "
        f"Overall status: {overall_status}."
    )
    return 0 if successful_sources > 0 else 3



if __name__ == "__main__":
    raise SystemExit(main())
