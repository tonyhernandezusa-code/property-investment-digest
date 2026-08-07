# Property Investment Digest

## Migration 8 — Hotel / Hospitality
Adds a dedicated hotel section without changing the Stock Digest repository.

### New pages
- `hotel-market.html`
- `hotel-analysis.html`

### Hotel market data
- U.S. Census County Business Patterns
- NAICS 721110: Hotels (except Casino Hotels) and Motels
- United States, state, and county
- Establishments
- Employment
- Annual payroll
- Employees per establishment
- Payroll per employee
- 2019–2023 growth comparisons

### Hotel analysis
- Occupancy
- ADR
- RevPAR
- TRevPAR
- GOPPAR
- Simplified GOP and NOI
- Cap rate
- Price per key
- DSCR
- Debt yield
- Cash-on-cash
- Illustrative break-even occupancy
- Conservative / base / optimistic scenarios
- 10-year pro forma, exit value, equity multiple, IRR

The existing `CENSUS_API_KEY` and **Update Government Data** workflow are reused.
No new secret is required.

Market occupancy, ADR and RevPAR are not inferred from federal government data. They remain user-entered assumptions unless a future commercial provider grants written publication/subscriber rights.
