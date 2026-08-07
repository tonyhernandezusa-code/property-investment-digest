# Property Investment Digest — Migration 8.7

## Authorized Yahoo Stocks & Markets

Migration 8.7 replaces the non-working SEC stock updater with the same general Yahoo Finance / yfinance approach used by the original Stock Digest, for development/testing.

### Access protection
The market-data payload is encrypted before it is committed to the public GitHub Pages repository.

- Password is stored only in the GitHub Actions repository secret `STOCK_ACCESS_PASSWORD`.
- Password is not placed in HTML, JavaScript, JSON, or Git history.
- Browser derives an AES-256-GCM key from the password and decrypts the market data locally.
- The generated market data cannot be read from the JSON file without the password.

### Included
- Stock watchlist
- Latest daily price
- Daily change
- Six-month change
- 14-day RSI
- 52-week high/low
- Volume and average volume
- Market capitalization, trailing P/E and dividend yield when returned by yfinance
- Major U.S. and international indexes
- Index futures
- Selected commodities
- Price-history chart for the selected stock

### Important licensing limitation
This is authorized development/testing access. Password protection does not create or expand Yahoo Finance/yfinance commercial redistribution rights.

Before paid subscriber launch, market-data licensing must be confirmed or replaced with a properly licensed source.
