# Property Investment Digest

## Migration 8.3 — Buyer Brokerage / Commission & Cash-to-Close

This package contains Migration 8.2 ARM/floating financing and adds optional buyer-broker compensation and seller-credit calculations to the Full Property Calculator.

### New acquisition fields
- Buyer-broker compensation method: percentage or flat dollar amount
- Agreed buyer-broker compensation
- Seller/listing-side payment toward buyer brokerage
- Seller concession / credit toward other closing costs

### New results
- Total buyer-broker compensation
- Seller-paid buyer brokerage
- Buyer-paid brokerage at closing
- Seller credit toward other closing costs
- Net other closing costs
- Estimated cash to close / cash invested

### Financing treatment
The calculator intentionally treats the buyer-paid brokerage amount as cash at closing.
It does **not** automatically add the brokerage amount to the mortgage balance.

Estimated cash to close:
Down payment
+ Net other closing costs
+ Buyer-paid brokerage

Brokerage compensation is negotiable and transaction-specific. Loan-program rules and lender treatment must be verified independently.

No government-data update is required.
