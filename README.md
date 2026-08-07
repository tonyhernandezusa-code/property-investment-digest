# Property Investment Digest — Migration 8.5

Adds `property-search.html` as an Authorized Professional Property Search.

The page restores the main address-level research presentation from the older site:
- Property characteristics
- Building details
- Lot / area
- Assessment and property tax
- Ownership
- Most recent mortgage
- Sales history
- AVM when available
- Comparable sales when available
- Schools when available
- Neighborhood Census context
- Satellite map
- Recent searches stored only in the browser

Security design:
- No public sign-up button.
- Firebase email/password sign-in.
- Authenticated requests send a Firebase ID token to the existing ATTOM Cloudflare Worker.
- `WORKER_AUTH_PATCH.js` is included so the existing Worker can validate the token and enforce an authorized-email allow-list server-side.

IMPORTANT:
The website package alone does NOT make the old Worker private.
The Worker security patch must be merged and deployed before the ATTOM data endpoint is considered protected.

Foreclosure search remains disabled because the older project identified it as a separate ATTOM premium product.

No government-data update is required.
