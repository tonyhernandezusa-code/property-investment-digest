# Property Investment Digest — Migration 8.6

Adds `stocks.html` using free public SEC EDGAR data for major U.S. public companies.

Included: company identity, revenue, net income, diluted EPS, operating cash flow, capital expenditures, modeled free cash flow, assets, liabilities, equity, cash, long-term debt when available, shares outstanding, growth rates, margins, balance-sheet ratios, recent SEC filing links, and annual history where comparable facts are available.

Not included: live/delayed stock prices, intraday charts, proprietary index values, futures prices, market-news feeds, P/E or market capitalization dependent on a market quote.

`update_stock_fundamentals.py` uses SEC EDGAR.
`.github/workflows/update-stock-fundamentals.yml` runs manually or weekly.
No paid API key is required.
