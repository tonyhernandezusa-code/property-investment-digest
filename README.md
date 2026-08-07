# Property Investment Digest

## Migration 8.2 — Adjustable / Floating Rate Financing

This package contains the Hotel/Hospitality section plus the balloon-payment fix and now adds adjustable/floating-rate financing.

### Full Property Calculator
Adds:
- Fixed vs Adjustable / Floating loan type
- Initial rate
- Initial fixed period
- Reference index label: SOFR, Prime, U.S. Treasury, or custom
- Index rate assumed at first reset
- Margin / spread
- Monthly / quarterly / semiannual / annual reset frequency
- Index-rate change stress assumption
- Rate floor
- Lifetime rate cap
- Month-by-month payment recalculation when rates change
- Average annual loan rate in amortization and pro forma tables
- Balloon balance under the modeled ARM rate path

### Hotel Analysis
Adds the same adjustable/floating-rate stress model and shows:
- Financing structure
- Year-1 average rate
- First modeled reset rate
- Annual rate in the 10-year pro forma
- ARM-aware debt service
- ARM-aware loan balance and balloon

### Property Manager
Adds fields to record:
- Fixed or adjustable/floating loan
- Index
- Margin / spread
- Next reset date
- Rate floor
- Lifetime rate cap

The calculators DO NOT predict future SOFR, Prime, Treasury or other indexes. All future-index assumptions are entered by the user.

No government-data update is required for this financing enhancement.
