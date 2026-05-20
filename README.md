# Homework 2 — Alpha Research

## Setup

Before running the notebook, clone the S&P 500 historical constituents repository:

```git clone https://github.com/fja05680/sp500.git```

## Data

Market data is downloaded automatically via `yfinance` when running the notebook. FRED macroeconomic data requires a free API key from https://fred.stlouisfed.org/docs/api/api_key.html

## Files

- `analysis.ipynb` — main analysis notebook
- `build_prices.py` — script to build price data
- `download_data.py` — data download script
- `scrape_form4.py` — script to scrape Form 4 filings
- `tickers_with_data.csv` — ticker dataset
- `fred_factors.parquet` — FRED macroeconomic factors
```
