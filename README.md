# Property Investment Digest

## Migration 8.1 — Balloon Payment Fix

This package contains the full Migration 8 Hotel/Hospitality section plus the financing correction.

### Corrected Hotel Analysis
- Loan amount
- Interest rate
- Amortization period
- **Loan term / balloon due**
- Interest-only period
- Year-1 debt service
- **Balloon balance due at maturity**
- Estimated balances after Years 5 and 10
- Balloon shown separately in the 10-year pro forma
- If the balloon occurs during the projection, it is modeled as additional equity and no refinance is assumed
- Exit balance recognizes whether the balloon has already been paid

### General Property Calculator
The existing balloon field is retained but relabeled more clearly:
- `Loan term / balloon due (years)`
- `Balloon balance due at loan maturity`

No government-data change is required for this correction.
